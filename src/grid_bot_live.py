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

# === LOCKED PARAMETERS ===
SPACING_PCT = 0.010        # Buy every 1% drop
SELL_GAIN_PCT = 0.010      # Sell at +1% above buy
PER_GRID_DOLLARS = 20      # $20 per grid
MAX_GRIDS = 30             # Max 30 parallel positions
MAX_HOLD_HOURS = 168       # 7 days
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
        print(f'[DISCORD] Failed: {r.status_code}')
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


def process_grid(state, current_high, current_low, current_close, current_time):
    """Process grid: sell fills, buy fills, force exits."""
    cash = state['cash']
    positions = state['positions']
    closed = state['history']

    # 1. SELL FILLS (use high)
    for pos in list(positions):
        target = pos['buy_price'] * (1 + SELL_GAIN_PCT)
        if current_high >= target:
            proceeds = pos['units'] * target
            profit = proceeds - pos['units'] * pos['buy_price']
            cash += proceeds
            closed.append({
                'type': 'SELL',
                'buy_price': pos['buy_price'],
                'sell_price': target,
                'units': pos['units'],
                'profit': round(profit, 4),
                'buy_time': pos['buy_time'],
                'sell_time': current_time.isoformat(),
                'held_hours': (current_time - pd.to_datetime(pos['buy_time'], utc=True)).total_seconds() / 3600,
            })
            positions.remove(pos)
            print(f'[GRID] SELL @ {target:.4f} | profit=${profit:.2f}')

    # 2. FORCE EXITS (breakeven after max hold)
    for pos in list(positions):
        held_h = (current_time - pd.to_datetime(pos['buy_time'], utc=True)).total_seconds() / 3600
        if held_h >= MAX_HOLD_HOURS and current_high >= pos['buy_price']:
            proceeds = pos['units'] * pos['buy_price']
            cash += proceeds
            closed.append({
                'type': 'FORCE_EXIT',
                'buy_price': pos['buy_price'],
                'sell_price': pos['buy_price'],
                'units': pos['units'],
                'profit': 0,
                'buy_time': pos['buy_time'],
                'sell_time': current_time.isoformat(),
                'held_hours': held_h,
            })
            positions.remove(pos)
            print(f'[GRID] FORCE EXIT @ {pos["buy_price"]:.4f} | breakeven')

    # 3. GRID ANCHOR
    if state.get('anchor') is None:
        state['anchor'] = current_close
    elif not positions and current_high > state['anchor']:
        state['anchor'] = max(state['anchor'], current_close)

    # 4. BUY FILLS (use low)
    if len(positions) < MAX_GRIDS and cash >= PER_GRID_DOLLARS:
        if not positions:
            next_level = state['anchor'] * (1 - SPACING_PCT)
        else:
            lowest_buy = min(p['buy_price'] for p in positions)
            next_level = lowest_buy * (1 - SPACING_PCT)

        if current_low <= next_level:
            units = PER_GRID_DOLLARS / next_level
            cash -= PER_GRID_DOLLARS
            positions.append({
                'buy_price': round(next_level, 4),
                'units': round(units, 6),
                'buy_time': current_time.isoformat(),
            })
            print(f'[GRID] BUY @ {next_level:.4f} | ${PER_GRID_DOLLARS}')

    state['cash'] = round(cash, 2)
    state['positions'] = positions
    state['history'] = closed[-500:]  # keep last 500


def run_once():
    state = load_json(STATE_FILE, {
        'cash': START_BALANCE, 'positions': [], 'history': [], 'anchor': None,
        'last_run': None,
    })

    ex = get_exchange()
    df = fetch_ohlcv(SYMBOL, ex)

    current_high = float(df['high'].iloc[-1])
    current_low = float(df['low'].iloc[-1])
    current_close = float(df['close'].iloc[-1])
    current_time = datetime.now(timezone.utc)

    print(f"[PRICE] high={current_high:.4f} low={current_low:.4f} close={current_close:.4f}")
    print(f"[STATE] cash=${state['cash']:.2f} | positions={len(state['positions'])} | anchor={state.get('anchor')}")

    process_grid(state, current_high, current_low, current_close, current_time)

    state['last_run'] = current_time.isoformat()
    save_json(STATE_FILE, state)
    save_json(TRADES_FILE, state['history'])

    # Summary
    equity = state['cash'] + sum(p['units'] * current_close for p in state['positions'])
    total_profit = sum(h['profit'] for h in state['history'])
    sells = [h for h in state['history'] if h['type'] == 'SELL']
    wins = sum(1 for h in sells if h['profit'] > 0)
    wr = (wins / len(sells) * 100) if sells else 0

    print(f"[EQUITY] ${equity:.2f} | Total profit: ${total_profit:.2f} | "
          f"Sells: {len(sells)} | WR: {wr:.1f}%")

    # Daily heartbeat check
    last_hb = state.get('last_heartbeat', '')
    today = current_time.strftime('%Y-%m-%d')
    if last_hb != today:
        positions_val = sum(p['units'] * current_close for p in state['positions'])
        send(
            f"**DAILY GRID SUMMARY** | {today}\n"
            f"Equity: `${equity:.2f}` | Cash: `${state['cash']:.2f}`\n"
            f"Open grids: `{len(state['positions'])}` (${positions_val:.2f})\n"
            f"Total profit: `${total_profit:.2f}`\n"
            f"Sells today: `{len(sells)}` | WR: `{wr:.1f}%`"
        )
        state['last_heartbeat'] = today
        save_json(STATE_FILE, state)


if __name__ == '__main__':
    run_once()
