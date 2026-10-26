"""
MULTI-ASSET LIVE SCANNER (SMC + DCA + Circuit Breaker)
"""
import os
import sys
import json
import requests
from datetime import datetime, timezone

import ccxt
import pandas as pd
import numpy as np
import pyvsmc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'config')
SYMBOLS_FILE = os.path.join(CONFIG_DIR, 'symbols.json')

EXCHANGE_CHAIN = [
    ('okx', {'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    ('kucoin', {'enableRateLimit': True}),
    ('mexc', {'enableRateLimit': True}),
]

def get_exchange():
    for ex_id, cfg in EXCHANGE_CHAIN:
        try:
            ex = getattr(ccxt, ex_id)(cfg)
            ex.load_markets()
            ex.fetch_ohlcv('AVAX/USDT', '1d', limit=5)
            return ex
        except Exception:
            continue
    raise RuntimeError('No exchange')

def send(webhook, content):
    if not webhook:
        print('[DISCORD] Not set')
        return False
    try:
        r = requests.post(webhook, json={'content': content}, timeout=10)
        return r.status_code in (200, 204)
    except Exception:
        return False

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8-sig') as f:
        try:
            return json.load(f)
        except:
            return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def check_filters(df):
    close = df['close']
    ema200 = close.ewm(span=200, adjust=False).mean()
    above_ema = close.iloc[-1] > ema200.iloc[-1]
    
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_bull = macd.iloc[-1] > signal.iloc[-1]
    
    # SMC Filter (Last 5 candles for recent signal)
    try:
        fvg = pyvsmc.detect_fvg(high=df['high'].to_numpy(), low=df['low'].to_numpy(), close=df['close'].to_numpy())
        ob = pyvsmc.detect_order_blocks(open_=df['open'].to_numpy(), high=df['high'].to_numpy(), low=df['low'].to_numpy(), close=df['close'].to_numpy())
        
        # Check if there was a bullish OB or FVG in the last 5 candles
        recent_bull_fvg = any(fvg.bullish[-5:] & ~fvg.mitigated[-5:])
        recent_bull_ob = any(ob.bullish_ob[-5:])
        smc_bull = recent_bull_fvg or recent_bull_ob
    except Exception:
        smc_bull = True # Fallback if pyvsmc fails
        
    return above_ema, macd_bull, smc_bull

def process_dca_symbol(ex, webhook, name, cfg):
    symbol = cfg['symbol']
    tf = cfg['timeframe']
    tp_pct = cfg['tp_pct']
    dca1_drop = cfg['dca1_drop']
    dca2_drop = cfg['dca2_drop']
    dca1_w = cfg['dca1_weight']
    dca2_w = cfg['dca2_weight']
    macro_sl_pct = cfg.get('macro_sl_pct', 0.15)
    max_hold = cfg['max_hold_hours']
    state_file = os.path.join(CONFIG_DIR, cfg['state_file'])
    trades_file = os.path.join(CONFIG_DIR, cfg['trades_file'])

    state = load_json(state_file, {'cycle': None, 'history': [], 'last_heartbeat': None})
    raw = ex.fetch_ohlcv(symbol, tf, limit=300)
    df = pd.DataFrame(raw, columns=['ts','open','high','low','close','volume'])
    price = float(df['close'].iloc[-1])
    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    
    above_ema, macd_bull, smc_bull = check_filters(df)

    now = datetime.now(timezone.utc)
    ts_str = now.strftime('%Y-%m-%d %H:%M UTC')
    today = now.strftime('%Y-%m-%d')

    print(f'[{name}] Price ${price:.4f} | EMA200: {above_ema} | MACD: {macd_bull} | SMC: {smc_bull}')

    cycle = state['cycle']

    if cycle:
        # 1. Check Circuit Breaker (15%)
        if low <= cycle['start_price'] * (1 - macro_sl_pct):
            msg = (
                f"**🚨 [{name}] CIRCUIT BREAKER TRIGGERED 🚨**\n"
                f"```\nPrice dropped 15% from entry.\n"
                f"Entry Price : ${cycle['start_price']:.4f}\n"
                f"Current Low : ${low:.4f}\n"
                f"Time        : {ts_str}\n```\n"
                f"**ACTION:** Sell ALL {name} immediately. Capital protected."
            )
            send(webhook, msg)
            state['history'].append({'profit_pct': -macro_sl_pct*100, 'type': 'CIRCUIT_BREAKER', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(state_file, state)
            save_json(trades_file, state['history'])
            return

        # 2. Check TP
        elif high >= cycle['tp']:
            msg = (
                f"**✅ [{name}] TAKE PROFIT HIT**\n"
                f"```\nAvg Entry : ${cycle['avg']:.4f}\n"
                f"Exit      : ${cycle['tp']:.4f} (+{tp_pct*100:.1f}%)\n"
                f"Time      : {ts_str}\n```\n"
                f"**ACTION:** Sell ALL {name} now."
            )
            send(webhook, msg)
            state['history'].append({'profit_pct': tp_pct*100, 'type': 'TP', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(state_file, state)
            save_json(trades_file, state['history'])
            return

        # 3. Check DCA
        elif cycle['level'] < 3:
            if cycle['level'] == 1 and low <= cycle['start_price'] * (1 - dca1_drop):
                cycle['level'] = 2
                cycle['units'] += (cycle['initial_cost'] * dca1_w) / price
                cycle['cost'] += (cycle['initial_cost'] * dca1_w)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                msg = (
                    f"**🟡 [{name}] DCA LEVEL 1 (-{dca1_drop*100:.1f}%)**\n"
                    f"```\nCurrent Price : ${price:.4f}\n"
                    f"New Avg Entry : ${cycle['avg']:.4f}\n"
                    f"New Target    : ${cycle['tp']:.4f} (+{tp_pct*100:.1f}%)\n```\n"
                    f"**ACTION:** Buy {dca1_w*100:.0f}% more {name}. Update TP."
                )
                send(webhook, msg)
            
            elif cycle['level'] == 2 and low <= cycle['start_price'] * (1 - dca2_drop):
                cycle['level'] = 3
                cycle['units'] += (cycle['initial_cost'] * dca2_w) / price
                cycle['cost'] += (cycle['initial_cost'] * dca2_w)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                msg = (
                    f"**🔴 [{name}] DCA LEVEL 2 (-{dca2_drop*100:.1f}%)**\n"
                    f"```\nCurrent Price : ${price:.4f}\n"
                    f"New Avg Entry : ${cycle['avg']:.4f}\n"
                    f"New Target    : ${cycle['tp']:.4f} (+{tp_pct*100:.1f}%)\n```\n"
                    f"**ACTION:** Buy final {dca2_w*100:.0f}% {name}. Update TP."
                )
                send(webhook, msg)

        # 4. Time Exit
        hours_held = (now - pd.to_datetime(cycle['start_time'], utc=True)).total_seconds() / 3600
        if hours_held >= max_hold:
            send(webhook, f"**⚪ [{name}] TIME EXIT** (14 Days)\n```\nPrice: ${price:.4f}\n```\n**ACTION:** Sell all at market.")
            state['history'].append({'profit_pct': (price/cycle['avg']-1)*100, 'type': 'TIME', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(state_file, state)
            return

    else:
        # New Entry (Requires MACD + EMA200 + SMC)
        if above_ema and macd_bull and smc_bull:
            cycle = {
                'start_time': now.isoformat(), 'start_price': price, 'level': 1,
                'initial_cost': 50.0, 'cost': 50.0, 'units': 50.0 / price,
                'avg': price, 'tp': price * (1 + tp_pct)
            }
            state['cycle'] = cycle
            msg = (
                f"**🟢 [{name}] LONG ENTRY SIGNAL (SMC Confirmed)**\n"
                f"```\nEntry Price : ${price:.4f}\n"
                f"Take Profit : ${cycle['tp']:.4f} (+{tp_pct*100:.1f}%)\n"
                f"Hard Stop   : ${price * (1 - macro_sl_pct):.4f} (-{macro_sl_pct*100:.1f}%)\n"
                f"Time        : {ts_str}\n```\n"
                f"**ACTION:** Buy 50% capital at market. Set TP at ${cycle['tp']:.4f}. Keep 50% for DCA."
            )
            send(webhook, msg)
        else:
            print(f'[{name}] Filters not met (Wait for SMC + Trend).')

    save_json(state_file, state)

    # Daily Heartbeat
    if state.get('last_heartbeat') != today:
        status = f"IN CYCLE (Level {cycle['level']})" if cycle else "WAITING FOR FILTERS"
        msg = (
            f"**[{name}] DAILY REPORT**\n"
            f"```\nPrice  : ${price:.4f}\n"
            f"MACD   : {'Bullish' if macd_bull else 'Bearish'}\n"
            f"EMA200 : {'Above' if above_ema else 'Below'}\n"
            f"SMC    : {'Bullish' if smc_bull else 'No Setup'}\n"
            f"Status : {status}\n```"
        )
        send(webhook, msg)
        state['last_heartbeat'] = today
        save_json(state_file, state)

def run():
    webhook = os.environ.get('DISCORD_WEBHOOK', '')
    if not webhook or 'PASTE' in webhook:
        print('[DISCORD] Webhook not set')
        return

    with open(SYMBOLS_FILE, 'r') as f:
        symbols = json.load(f)

    ex = get_exchange()
    for name, cfg in symbols.items():
        try:
            process_dca_symbol(ex, webhook, name, cfg)
        except Exception as e:
            print(f'[{name}] Error: {e}')

if __name__ == '__main__':
    run()
