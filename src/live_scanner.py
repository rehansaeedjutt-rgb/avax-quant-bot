"""
LIVE DCA LADDER BOT v8.0 (The Final Winner)
- 1H Timeframe
- Entry: Buy 50% of capital.
- DCA1: Price drops 2% -> Buy 30%.
- DCA2: Price drops 4% -> Buy 20%.
- TP: Sell ALL at +3% profit from average.
- No Stop Loss.
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
TIMEFRAME = '1h'
TP_PCT = 0.03
MAX_HOLD_H = 336 # 14 days

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

def fetch_price(ex):
    raw = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=5)
    df = pd.DataFrame(raw, columns=['ts','o','h','l','c','v'])
    return float(df['c'].iloc[-1]), float(df['h'].iloc[-1]), float(df['l'].iloc[-1])

def run_once():
    state = load_json(STATE_FILE, {
        'cycle': None, 'history': [], 'last_heartbeat': None
    })

    ex = get_exchange()
    price, high, low = fetch_price(ex)
    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')

    print(f'[PRICE] ${price:.4f} | High: ${high:.4f} | Low: ${low:.4f}')

    cycle = state['cycle']

    if cycle:
        # 1. Check TP
        if high >= cycle['tp']:
            profit = (cycle['units'] * cycle['tp']) - cycle['cost']
            send(f"**TAKE PROFIT HIT** | AVAX\n```\nAvg Entry: ${cycle['avg']:.4f}\nExit: ${cycle['tp']:.4f}\nProfit: +3.0%\n```\n**ACTION: Sell ALL your AVAX now.**\nCycle complete. Waiting for next entry.")
            state['history'].append({'profit_pct': 3.0, 'type': 'TP', 'closed_at': now.isoformat()})
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
                send(f"**DCA LEVEL 1 TRIGGERED** (-2%)\n```\nPrice: ${price:.4f}\nAvg: ${cycle['avg']:.4f}\nNew TP: ${cycle['tp']:.4f}\n```\n**ACTION: Buy 30% more capital worth of AVAX.**")
            
            elif cycle['level'] == 2 and low <= cycle['start_price'] * 0.96:
                cycle['level'] = 3
                cycle['units'] += (cycle['initial_cost'] * 0.20) / price
                cycle['cost'] += (cycle['initial_cost'] * 0.20)
                cycle['avg'] = cycle['cost'] / cycle['units']
                cycle['tp'] = cycle['avg'] * (1 + TP_PCT)
                send(f"**DCA LEVEL 2 TRIGGERED** (-4%)\n```\nPrice: ${price:.4f}\nAvg: ${cycle['avg']:.4f}\nNew TP: ${cycle['tp']:.4f}\n```\n**ACTION: Buy final 20% more capital worth of AVAX.**")

        # 3. Force Exit (14 days)
        hours_held = (now - pd.to_datetime(cycle['start_time'], utc=True)).total_seconds() / 3600
        if hours_held >= MAX_HOLD_H:
            send(f"**TIME EXIT** (14 Days Passed)\n```\nPrice: ${price:.4f}\nClosing at market.\n```")
            state['history'].append({'profit_pct': (price/cycle['avg']-1)*100, 'type': 'TIME', 'closed_at': now.isoformat()})
            state['cycle'] = None
            save_json(STATE_FILE, state)
            return

    else:
        # Start new cycle
        dollars = 50.0 # Assuming $100 capital. For larger, adjust.
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
        send(f"**NEW ENTRY SIGNAL** | AVAX\n```\nPrice: ${price:.4f}\nTake Profit: ${cycle['tp']:.4f} (+3.0%)\n```\n**ACTION: Buy 50% of your allocated capital now.**\nIf price drops -2% or -4%, I will tell you to DCA.")

    save_json(STATE_FILE, state)

    # Daily heartbeat
    if state.get('last_heartbeat') != today:
        send(f"**DAILY SUMMARY** | {today}\n```\nPrice: ${price:.4f}\nStatus: {'In Cycle (Level ' + str(cycle['level']) + ')' if cycle else 'Waiting'}\n```")
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)

if __name__ == '__main__':
    run_once()
