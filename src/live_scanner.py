"""
LIVE ULTIMATE BOT v9.1 (Final Optimized Version)
- Timeframe: 1D (Daily)
- Filters: MACD Bullish AND Price > EMA 200
- DCA: 50% Entry, 30% at -2%, 20% at -4%
- Take Profit: +4.0%
"""
import os
import sys
import json
import requests
from datetime import datetime, timezone

import ccxt
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'config')
STATE_FILE = os.path.join(CONFIG_DIR, 'live_state.json')
TRADES_FILE = os.path.join(CONFIG_DIR, 'live_trades.json')

SYMBOL = 'AVAX/USDT'
TIMEFRAME = '1d'  # Daily Timeframe
TP_PCT = 0.04     # Optimized TP is 4%
MAX_HOLD_H = 336  # 14 days

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
        except Exception as e:
            print(f'[EXCHANGE] {ex_id}: {str(e)[:80]}')
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

def fetch_data(ex):
    raw = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=300)
    df = pd.DataFrame(raw, columns=['ts','open','high','low','close','volume'])
    return df

def check_filters(df):
    close = df['close']
    ema200 = close.ewm(span=200, adjust=False).mean()
    above_ema = close.iloc[-1] > ema200.iloc[-1]
    
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_bull = macd.iloc[-1] > signal.iloc[-1]
    
    return above_ema, macd_bull

def run_once():
    state = load_json(STATE_FILE, {
        'cycle': None, 'history': [], 'last_heartbeat': None
    })

    ex = get_exchange()
    df = fetch_data(ex)
    price = float(df['close'].iloc[-1])
    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    
    above_ema, macd_bull = check_filters(df)
    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')

    print(f'[PRICE] ${price:.4f} | EMA200: {above_ema} | MACD: {macd_bull}')

    cycle = state['cycle']

    if cycle:
        # 1. Check TP (4%)
        if high >= cycle['tp']:
            send(f"**TAKE PROFIT HIT (+4.0%)** | AVAX\n```\nAvg Entry: ${cycle['avg']:.4f}\nExit: ${cycle['tp']:.4f}\n```\n**ACTION: Sell ALL your AVAX now.**")
            state['history'].append({'profit_pct': 4.0, 'type': 'TP', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(STATE_FILE, state)
            save_json(TRADES_FILE, state['history'])
            return

        # 2. Check DCA Levels
        if cycle['level'] < 3:
            if cycle['level'] == 1 and low <= cycle['start_price'] * 0.98:
                cycle['level'] = 2
                cycle['units'] += (cycle['initial_cost'] * 0.30) / price
                cycle['cost'] += (cycle['initial_cost'] * 0.30)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp'] = cycle['avg'] * (1 + TP_PCT)
                send(f"**DCA LEVEL 1 TRIGGERED (-2%)** | AVAX\n```\nPrice: ${price:.4f}\nAvg: ${cycle['avg']:.4f}\nNew TP: ${cycle['tp']:.4f}\n```\n**ACTION: Buy 30% more capital worth of AVAX.**")
            
            elif cycle['level'] == 2 and low <= cycle['start_price'] * 0.96:
                cycle['level'] = 3
                cycle['units'] += (cycle['initial_cost'] * 0.20) / price
                cycle['cost'] += (cycle['initial_cost'] * 0.20)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp'] = cycle['avg'] * (1 + TP_PCT)
                send(f"**DCA LEVEL 2 TRIGGERED (-4%)** | AVAX\n```\nPrice: ${price:.4f}\nAvg: ${cycle['avg']:.4f}\nNew TP: ${cycle['tp']:.4f}\n```\n**ACTION: Buy final 20% more capital worth of AVAX.**")

        # 3. Force Exit (14 days)
        hours_held = (now - pd.to_datetime(cycle['start_time'], utc=True)).total_seconds() / 3600
        if hours_held >= MAX_HOLD_H:
            send(f"**TIME EXIT** (14 Days Passed)\n```\nPrice: ${price:.4f}\nClosing at market.\n```")
            state['history'].append({'profit_pct': (price/cycle['avg']-1)*100, 'type': 'TIME', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(STATE_FILE, state)
            return

    else:
        # Check Filters for New Entry
        if above_ema and macd_bull:
            dollars = 50.0 # Assuming $100 capital
            cycle = {
                'start_time': now.isoformat(),
                'start_price': price,
                'level': 1,
                'initial_cost': 50.0,
                'cost': 50.0,
                'units': 50.0 / price,
                'avg': price,
                'tp': price * (1 + TP_PCT)
            }
            state['cycle'] = cycle
            send(f"**NEW ENTRY SIGNAL** | AVAX\n```\nPrice: ${price:.4f}\nTake Profit: ${cycle['tp']:.4f} (+4.0%)\n```\n**ACTION: Buy 50% of your allocated capital now.**\nIf price drops -2% or -4%, I will tell you to DCA.")
        else:
            print('[WAIT] Filters not met (MACD or EMA200 is false).')

    save_json(STATE_FILE, state)

    # Daily heartbeat
    if state.get('last_heartbeat') != today:
        send(f"**DAILY SUMMARY** | {today}\n```\nPrice: ${price:.4f}\nStatus: {'In Cycle (Level ' + str(cycle['level']) + ')' if cycle else 'Waiting for Filters'}\n```")
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)

if __name__ == '__main__':
    run_once()
