import os
import sys
import json
import requests
from datetime import datetime, timezone

import ccxt
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)

STATE_FILE = os.path.join(CONFIG_DIR, 'grid_state.json')
TRADES_FILE = os.path.join(CONFIG_DIR, 'grid_trades.json')

SYMBOL = 'AVAX/USDT'
TIMEFRAME = '15m'

SPACING_PCT = 0.010
SELL_GAIN_PCT = 0.010
PER_GRID_DOLLARS = 20
MAX_GRIDS = 30
MAX_HOLD_HOURS = 168
START_BALANCE = 1000.0

EXCHANGE_CHAIN = [
    ('okx', {'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    ('kucoin', {'enableRateLimit': True}),
    ('bitget', {'enableRateLimit': True}),
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
            print(f'[EXCHANGE] {ex_id} failed: {str(e)[:100]}')
            continue
    raise RuntimeError('No working exchange')


def get_webhook():
    url = os.environ.get('DISCORD_WEBHOOK', '')
    if not url or 'PASTE' in url:
        return None
    return url


def send(content):
    url = get_webhook()
    if not url:
        print('[DISCORD] Webhook not set')
        return False
    try:
        r = requests.post(url, json={'content': content}, timeout=10)
        if r.status_code in (200, 204):
            print('[DISCORD] Sent OK')
            return True
        print(f'[DISCORD] Failed: {r.status_code} {r.text[:150]}')
        return False
    except Exception as e:
        print(f'[DISCORD] Error: {e}')
        return False


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def fetch_ohlcv(symbol, ex):
    raw = ex.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
    df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.set_index('ts')
    return df


def process_grid(state, high, low, close, now):
    cash = state['cash']
    positions = state['positions']
    closed = state['history']
    events = []

    # 1. SELL FILLS
    for pos in list(positions):
        target = pos['buy_price'] * (1 + SELL_GAIN_PCT)
        if high >= target:
            proceeds = pos['units'] * target
            profit = proceeds - pos['units'] * pos['buy_price']
            cash += proceeds
            held_h = (now - pd.to_datetime(pos['buy_time'], utc=True)).total_seconds() / 3600
            closed.append({
                'type': 'SELL', 'buy_price': pos['buy_price'],
                'sell_price': round(target, 4), 'units': pos['units'],
                'profit': round(profit, 4), 'buy_time': pos['buy_time'],
                'sell_time': now.isoformat(), 'held_hours': round(held_h, 2),
            })
            positions.remove(pos)
            events.append(('SELL', pos['buy_price'], target, profit, held_h))

    # 2. FORCE EXITS
    for pos in list(positions):
        held_h = (now - pd.to_datetime(pos['buy_time'], utc=True)).total_seconds() / 3600
        if held_h >= MAX_HOLD_HOURS and high >= pos['buy_price']:
            cash += pos['units'] * pos['buy_price']
            closed.append({
                'type': 'FORCE_EXIT', 'buy_price': pos['buy_price'],
                'sell_price': pos['buy_price'], 'units': pos['units'],
                'profit': 0, 'buy_time': pos['buy_time'],
                'sell_time': now.isoformat(), 'held_hours': round(held_h, 2),
            })
            positions.remove(pos)
            events.append(('FORCE', pos['buy_price'], pos['buy_price'], 0, held_h))

    # 3. ANCHOR
    if state.get('anchor') is None:
        state['anchor'] = close
    elif not positions and high > state['anchor']:
        state['anchor'] = max(state['anchor'], close)

    # 4. BUY FILLS
    if len(positions) < MAX_GRIDS and cash >= PER_GRID_DOLLARS:
        if not positions:
            next_level = state['anchor'] * (1 - SPACING_PCT)
        else:
            lowest = min(p['buy_price'] for p in positions)
            next_level = lowest * (1 - SPACING_PCT)
        if low <= next_level:
            units = PER_GRID_DOLLARS / next_level
            cash -= PER_GRID_DOLLARS
            positions.append({
                'buy_price': round(next_level, 4),
                'units': round(units, 6),
                'buy_time': now.isoformat(),
            })
            events.append(('BUY', next_level, None, None, None))

    state['cash'] = round(cash, 2)
    state['positions'] = positions
    state['history'] = closed[-500:]
    return events


def run_once():
    state = load_json(STATE_FILE, {
        'cash': START_BALANCE, 'positions': [], 'history': [],
        'anchor': None, 'last_heartbeat': None, 'last_run': None,
    })

    ex = get_exchange()
    df = fetch_ohlcv(SYMBOL, ex)

    high = float(df['high'].iloc[-1])
    low = float(df['low'].iloc[-1])
    close = float(df['close'].iloc[-1])
    now = datetime.now(timezone.utc)

    print(f"[PRICE] high={high:.4f} low={low:.4f} close={close:.4f}")
    print(f"[STATE] cash=${state['cash']:.2f} positions={len(state['positions'])} "
          f"anchor={state.get('anchor')}")

    events = process_grid(state, high, low, close, now)

    # Send Discord message per event (BUY and SELL only — not FORCE)
    for ev in events:
        kind, buy_p, sell_p, profit, held_h = ev
        if kind == 'BUY':
            send(f"**GRID BUY** | AVAX @ `{buy_p:.4f}`\n"
                 f"Amount: `${PER_GRID_DOLLARS}` | Target sell: `{buy_p*(1+SELL_GAIN_PCT):.4f}`\n"
                 f"Open grids: `{len(state['positions'])}` | Cash: `${state['cash']:.2f}`")
        elif kind == 'SELL':
            send(f"**GRID SELL** ✅ | AVAX `{buy_p:.4f}` → `{sell_p:.4f}`\n"
                 f"Profit: `+${profit:.2f}` | Held: `{held_h:.1f}h`\n"
                 f"Open grids: `{len(state['positions'])}` | Cash: `${state['cash']:.2f}`")
        elif kind == 'FORCE':
            send(f"**GRID FORCE EXIT** | AVAX `{buy_p:.4f}` (breakeven)\n"
                 f"Held: `{held_h:.1f}h` | Cash: `${state['cash']:.2f}`")

    state['last_run'] = now.isoformat()
    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state['history'])

    # Equity summary
    equity = state['cash'] + sum(p['units'] * close for p in state['positions'])
    total_profit = sum(h['profit'] for h in state['history'])
    sells = [h for h in state['history'] if h['type'] == 'SELL']
    wins = sum(1 for h in sells if h['profit'] > 0)
    wr = (wins / len(sells) * 100) if sells else 0

    print(f"[EQUITY] ${equity:.2f} | Profit: ${total_profit:.2f} | "
          f"Sells: {len(sells)} | WR: {wr:.1f}%")

    # Daily heartbeat
    today = now.strftime('%Y-%m-%d')
    if state.get('last_heartbeat') != today:
        open_val = sum(p['units'] * close for p in state['positions'])
        send(
            f"**DAILY GRID SUMMARY** | {today}\n"
            f"Equity: `${equity:.2f}` | Cash: `${state['cash']:.2f}`\n"
            f"Open grids: `{len(state['positions'])}` (${open_val:.2f})\n"
            f"Total profit: `${total_profit:.2f}`\n"
            f"Total sells: `{len(sells)}` | WR: `{wr:.1f}%`"
        )
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)


if __name__ == '__main__':
    run_once()
