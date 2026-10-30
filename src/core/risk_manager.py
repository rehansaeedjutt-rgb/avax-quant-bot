import os
import json
import logging
from datetime import datetime, timezone
import pandas as pd
import math
from src.core.alerts import send_discord
from src.core.indicators import check_filters

logger = logging.getLogger(__name__)

# FIX: Dynamic Path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT_DIR, 'config')

def load_json(path, default):
    if not os.path.exists(path): return default
    with open(path, 'r', encoding='utf-8-sig') as f:
        try: return json.load(f)
        except: return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def process_coin(ex, name: str, cfg: dict):
    state_file = os.path.join(CONFIG_DIR, cfg['state_file'])
    state = load_json(state_file, {'cycle': None, 'history': [], 'last_heartbeat': None})
    
    # Fetch Data
    try:
        raw = ex.fetch_ohlcv(cfg['symbol'], cfg['timeframe'], limit=300)
        df = pd.DataFrame(raw, columns=['ts','open','high','low','close','volume'])
    except Exception as e:
        logger.error(f"[{name}] Failed to fetch data: {e}")
        return

    # ==========================================
    # SANITY CHECKS (Prevent Fake Data / Zero Values)
    # ==========================================
    price = float(df['close'].iloc[-1])
    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    
    if math.isnan(price) or price <= 0:
        logger.error(f"[{name}] Invalid price data (NaN or Zero). Skipping.")
        return
        
    if len(df) < 250:
        logger.error(f"[{name}] Not enough historical data. Skipping.")
        return

    now = datetime.now(timezone.utc)
    ts_str = now.strftime('%Y-%m-%d %H:%M UTC')
    today = now.strftime('%Y-%m-%d')
    cycle = state['cycle']

    # ==========================================
    # ACTIVE TRADE MANAGEMENT
    # ==========================================
    if cycle:
        # 1. Circuit Breaker (Account Protection)
        if low <= cycle['start_price'] * (1 - cfg['macro_sl_pct']):
            msg = f"**🚨 [{name}] CIRCUIT BREAKER (15%) 🚨**\n```\nEntry: ${cycle['start_price']:.4f}\nExit: ${low:.4f}\n```\n**ACTION:** SELL ALL. Capital protected."
            send_discord(msg)
            state['cycle'] = None
            state['history'].append({'profit_pct': -cfg['macro_sl_pct']*100, 'type': 'CB'})
            save_json(state_file, state)
            return

        # 2. Partial Take Profit (TP1)
        if not cycle['tp1_hit'] and high >= cycle['tp1_price']:
            cycle['tp1_hit'] = True
            cycle['sl'] = cycle['avg'] # Move SL to Breakeven
            cycle['highest_price'] = high # Start trailing
            msg = f"**🟢 [{name}] PARTIAL TP (50%)**\n```\nEntry: ${cycle['avg']:.4f}\nTP1: ${cycle['tp1_price']:.4f}\n```\n**ACTION:** Sell 50%. Move SL to Breakeven."
            send_discord(msg)

        # 3. Trailing Stop & Final TP (TP2)
        elif cycle['tp1_hit']:
            if high > cycle.get('highest_price', 0):
                cycle['highest_price'] = high
                
            trail_sl = cycle['highest_price'] * (1 - cfg['trail_pct'])
            if trail_sl > cycle['sl']:
                cycle['sl'] = trail_sl
                
            if high >= cycle['tp2_price']:
                msg = f"**✅ [{name}] FINAL TP HIT**\n```\nExit: ${cycle['tp2_price']:.4f}\n```\n**ACTION:** Sell remaining 50%."
                send_discord(msg)
                state['cycle'] = None
                state['history'].append({'profit_pct': cfg['tp2_pct']*100, 'type': 'TP2'})
                save_json(state_file, state)
                return
            elif low <= cycle['sl']:
                msg = f"**⚪ [{name}] TRAILING STOP HIT**\n```\nExit: ${cycle['sl']:.4f}\nP&L: Breakeven or Positive\n```\n**ACTION:** Sell remaining position."
                send_discord(msg)
                state['cycle'] = None
                state['history'].append({'profit_pct': ((cycle['sl']/cycle['avg'])-1)*100, 'type': 'TRAIL'})
                save_json(state_file, state)
                return

        # 4. DCA Logic
        elif cycle['level'] < 3:
            dca1_price = cycle['start_price'] * (1 - cfg['dca1_drop'])
            dca2_price = cycle['start_price'] * (1 - cfg['dca2_drop'])
            
            if cycle['level'] == 1 and low <= dca1_price:
                cycle['level'] = 2
                cycle['units'] += (cycle['initial_cost'] * 0.30) / price
                cycle['cost'] += (cycle['initial_cost'] * 0.30)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp1_price'] = cycle['avg'] * (1 + cfg['tp1_pct'])
                cycle['tp2_price'] = cycle['avg'] * (1 + cfg['tp2_pct'])
                send_discord(f"**🟡 [{name}] DCA 1 (-{cfg['dca1_drop']*100}%)**\n```\nNew Avg: ${cycle['avg']:.4f}\n```\n**ACTION:** Buy 30% more.")
            elif cycle['level'] == 2 and low <= dca2_price:
                cycle['level'] = 3
                cycle['units'] += (cycle['initial_cost'] * 0.20) / price
                cycle['cost'] += (cycle['initial_cost'] * 0.20)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp1_price'] = cycle['avg'] * (1 + cfg['tp1_pct'])
                cycle['tp2_price'] = cycle['avg'] * (1 + cfg['tp2_pct'])
                send_discord(f"**🔴 [{name}] DCA 2 (-{cfg['dca2_drop']*100}%)**\n```\nNew Avg: ${cycle['avg']:.4f}\n```\n**ACTION:** Buy final 20%.")

    # ==========================================
    # NEW ENTRY & SLIPPAGE PROTECTION
    # ==========================================
    else:
        signal_close = float(df['close'].iloc[-2])
        slippage_pct = abs(price - signal_close) / signal_close
        if slippage_pct > 0.015: # Relaxed to 1.5%
            logger.info(f"[{name}] Slippage too high ({slippage_pct*100:.2f}%). Skipping.")
            return
            
        above_ema, macd_bull, smc_bull = check_filters(df)
        
        if above_ema and macd_bull and smc_bull:
            cycle = {
                'start_time': now.isoformat(), 'start_price': price, 'level': 1,
                'initial_cost': 50.0, 'cost': 50.0, 'units': 50.0 / price,
                'avg': price, 'tp1_price': price * (1 + cfg['tp1_pct']),
                'tp2_price': price * (1 + cfg['tp2_pct']), 'tp1_hit': False,
                'sl': price * (1 - cfg['macro_sl_pct']), 'highest_price': price
            }
            state['cycle'] = cycle
            msg = f"**🟢 [{name}] LONG ENTRY**\n```\nPrice: ${price:.4f}\nTP1: ${cycle['tp1_price']:.4f}\nTP2: ${cycle['tp2_price']:.4f}\n```\n**ACTION:** Buy 50%. Keep 50% for DCA."
            send_discord(msg)
        else:
            logger.info(f"[{name}] Filters not met.")

    # Daily Heartbeat
    if state.get('last_heartbeat') != today:
        status = f"IN CYCLE (Level {cycle['level']})" if cycle else "WAITING"
        send_discord(f"**[{name}] DAILY REPORT**\n```\nPrice: ${price:.4f}\nStatus: {status}\n```")
        state['last_heartbeat'] = today
        
    save_json(state_file, state)
