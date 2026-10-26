"""
LIVE ULTIMATE BOT v9.3 (Crisp & Professional)
"""
import os
import sys
import json
import requests
from datetime import datetime, timezone

import ccxt
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'config')
STATE_FILE = os.path.join(CONFIG_DIR, 'live_state.json')
TRADES_FILE = os.path.join(CONFIG_DIR, 'live_trades.json')

SYMBOL = 'AVAX/USDT'
TIMEFRAME = '1d'
TP_PCT = 0.04
MAX_HOLD_H = 336

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
            ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=5)
            print(f'[EXCHANGE] Using: {ex_id}')
            return ex
        except Exception:
            continue
    raise RuntimeError('No exchange')

def get_webhook():
    url = os.environ.get('DISCORD_WEBHOOK', '')
    return url if url and 'PASTE' not in url else None

def send(content):
    url = get_webhook()
    if not url:
        print('[DISCORD] Not set')
        return False
    try:
        r = requests.post(url, json={'content': content}, timeout=10)
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

def run_once():
    state = load_json(STATE_FILE, {'cycle': None, 'history': [], 'last_heartbeat': None})
    ex = get_exchange()
    
    # Fetch data
    raw = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=300)
    df = pd.DataFrame(raw, columns=['ts','open','high','low','close','volume'])
    price = float(df['close'].iloc[-1])
    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    
    # Indicators
    close = df['close']
    ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    above_ema = price > ema200
    macd_bull = macd.iloc[-1] > signal.iloc[-1]
    
    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')
    ts_str = now.strftime('%Y-%m-%d %H:%M UTC')

    print(f'[PRICE] ${price:.4f} | EMA200: {above_ema} | MACD: {macd_bull}')

    cycle = state['cycle']

    if cycle:
        # 1. Check TP
        if high >= cycle['tp']:
            msg = (
                f"**✅ AVAX — TAKE PROFIT HIT**\n"
                f"```\n"
                f"Avg Entry : ${cycle['avg']:.4f}\n"
                f"Exit      : ${cycle['tp']:.4f} (+4.0%)\n"
                f"Time      : {ts_str}\n"
                f"```\n"
                f"**ACTION:** Sell ALL AVAX now."
            )
            send(msg)
            state['history'].append({'profit_pct': 4.0, 'type': 'TP', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(STATE_FILE, state)
            save_json(TRADES_FILE, state['history'])
            return

        # 2. Check DCA
        if cycle['level'] < 3:
            if cycle['level'] == 1 and low <= cycle['start_price'] * 0.98:
                cycle['level'] = 2
                cycle['units'] += (cycle['initial_cost'] * 0.30) / price
                cycle['cost'] += (cycle['initial_cost'] * 0.30)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp'] = cycle['avg'] * (1 + TP_PCT)
                msg = (
                    f"**🟡 AVAX — DCA LEVEL 1 (-2%)**\n"
                    f"```\n"
                    f"Current Price : ${price:.4f}\n"
                    f"New Avg Entry : ${cycle['avg']:.4f}\n"
                    f"New Target    : ${cycle['tp']:.4f} (+4.0%)\n"
                    f"Time          : {ts_str}\n"
                    f"```\n"
                    f"**ACTION:** Buy 30% more AVAX. Update TP to ${cycle['tp']:.4f}."
                )
                send(msg)
            
            elif cycle['level'] == 2 and low <= cycle['start_price'] * 0.96:
                cycle['level'] = 3
                cycle['units'] += (cycle['initial_cost'] * 0.20) / price
                cycle['cost'] += (cycle['initial_cost'] * 0.20)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp'] = cycle['avg'] * (1 + TP_PCT)
                msg = (
                    f"**🔴 AVAX — DCA LEVEL 2 (-4%)**\n"
                    f"```\n"
                    f"Current Price : ${price:.4f}\n"
                    f"New Avg Entry : ${cycle['avg']:.4f}\n"
                    f"New Target    : ${cycle['tp']:.4f} (+4.0%)\n"
                    f"Time          : {ts_str}\n"
                    f"```\n"
                    f"**ACTION:** Buy final 20% AVAX. Update TP to ${cycle['tp']:.4f}."
                )
                send(msg)

        # 3. Force Exit
        hours_held = (now - pd.to_datetime(cycle['start_time'], utc=True)).total_seconds() / 3600
        if hours_held >= MAX_HOLD_H:
            send(f"**⚪ AVAX — TIME EXIT** (14 Days)\n```\nPrice: ${price:.4f}\n```\n**ACTION:** Sell all at market.")
            state['history'].append({'profit_pct': (price/cycle['avg']-1)*100, 'type': 'TIME', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(STATE_FILE, state)
            return

    else:
        # New Entry
        if above_ema and macd_bull:
            cycle = {
                'start_time': now.isoformat(), 'start_price': price, 'level': 1,
                'initial_cost': 50.0, 'cost': 50.0, 'units': 50.0 / price,
                'avg': price, 'tp': price * (1 + TP_PCT)
            }
            state['cycle'] = cycle
            msg = (
                f"**🟢 AVAX — LONG ENTRY SIGNAL**\n"
                f"```\n"
                f"Entry Price : ${price:.4f}\n"
                f"Take Profit : ${cycle['tp']:.4f} (+4.0%)\n"
                f"Time        : {ts_str}\n"
                f"```\n"
                f"**ACTION:** Buy 50% capital at market. Set TP at ${cycle['tp']:.4f}. Keep 50% for DCA."
            )
            send(msg)
        else:
            print('[WAIT] Filters not met.')

    save_json(STATE_FILE, state)

    # Daily heartbeat
    if state.get('last_heartbeat') != today:
        status = f"IN CYCLE (Level {cycle['level']})" if cycle else "WAITING FOR FILTERS"
        msg = (
            f"**AVAX — DAILY REPORT**\n"
            f"```\n"
            f"Price  : ${price:.4f}\n"
            f"MACD   : {'Bullish' if macd_bull else 'Bearish'}\n"
            f"EMA200 : {'Above' if above_ema else 'Below'}\n"
            f"Status : {status}\n"
            f"```"
        )
        send(msg)
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)

if __name__ == '__main__':
    run_once()
