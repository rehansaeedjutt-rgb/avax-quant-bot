import os
import sys
import json
from datetime import datetime, timezone

import ccxt
import pandas as pd
import requests

# Auto-detect project root — works on Windows AND Linux
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT, 'config', 'scanner_state.json')
PAPER_STATE = os.path.join(ROOT, 'config', 'paper_state.json')
TRADES_FILE = os.path.join(ROOT, 'config', 'paper_trades.json')

SYMBOL = 'AVAX/USDT'
TIMEFRAME = '1h'
LIMIT = 500

TP_PCT = 0.007
SL_PCT = 0.025
RSI2_MAX = 12
BB_PERIOD = 20
BB_MULT = 2.0
VOL_FACTOR = 0.8
START_BALANCE = 1000.0
RISK_PER_TRADE = 0.02

EXCHANGE_CHAIN = [
    ('okx', {'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    ('kucoin', {'enableRateLimit': True}),
    ('bitget', {'enableRateLimit': True}),
    ('mexc', {'enableRateLimit': True}),
    ('htx', {'enableRateLimit': True}),
    ('gateio', {'enableRateLimit': True}),
]


def get_working_exchange():
    errors = []
    for ex_id, config in EXCHANGE_CHAIN:
        try:
            ex = getattr(ccxt, ex_id)(config)
            ex.load_markets()
            ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=1)
            print(f'[EXCHANGE] Using: {ex_id}')
            return ex
        except Exception as e:
            err = f'{ex_id}: {type(e).__name__}: {str(e)[:120]}'
            print(f'[EXCHANGE] {err}')
            errors.append(err)
            continue
    print('[EXCHANGE] All exchanges failed:')
    for e in errors:
        print(f'  - {e}')
    raise RuntimeError('No working exchange found')


def get_webhook():
    url = os.environ.get('DISCORD_WEBHOOK', '')
    if not url or 'PASTE' in url:
        return None
    return url


def send(content):
    url = get_webhook()
    if not url:
        print('[DISCORD] Webhook not set in environment')
        return False
    try:
        r = requests.post(url, json={'content': content}, timeout=10)
        if r.status_code in (200, 204):
            print('[DISCORD] Sent OK')
            return True
        print(f'[DISCORD] Failed: {r.status_code} {r.text[:200]}')
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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f'[STATE] Saved: {path}')


def rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def bb_lower(series, period, mult):
    ma = series.rolling(period).mean()
    sd = series.rolling(period).std()
    return ma - mult * sd


def fetch_ohlcv(symbol, ex):
    raw = ex.fetch_ohlcv(symbol, TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.set_index('ts')
    return df


def fetch_btc_up(ex):
    df = fetch_ohlcv('BTC/USDT', ex)
    df['close'] = df['close'].astype(float)
    ema = df['close'].ewm(span=50, adjust=False).mean()
    return bool(df['close'].iloc[-1] > ema.iloc[-1])


def check_signal(ex):
    df = fetch_ohlcv(SYMBOL, ex)
    close = df['close']
    open_p = df['open']
    low = df['low']
    vol = df['volume']

    ema_m = close.ewm(span=50, adjust=False).mean()
    ema_s = close.ewm(span=200, adjust=False).mean()
    rsi2 = rsi(close, 2)
    bbl = bb_lower(close, BB_PERIOD, BB_MULT)
    vol_ma = vol.rolling(20).mean()

    price = float(close.iloc[-1])
    r2 = float(rsi2.iloc[-1])
    uptrend = (price > float(ema_m.iloc[-1])) and (float(ema_m.iloc[-1]) > float(ema_s.iloc[-1]))
    oversold = r2 < RSI2_MAX
    bb_touch = float(low.iloc[-1]) <= float(bbl.iloc[-1]) * 1.005
    green = price > float(open_p.iloc[-1])
    volume_ok = float(vol.iloc[-1]) > float(vol_ma.iloc[-1]) * VOL_FACTOR
    btc_up = fetch_btc_up(ex)

    fired = uptrend and oversold and bb_touch and green and volume_ok and btc_up
    return {
        'ts': df.index[-1].isoformat(),
        'price': price,
        'rsi2': round(r2, 2),
        'uptrend': uptrend,
        'oversold': oversold,
        'bb_touch': bb_touch,
        'green': green,
        'volume_ok': volume_ok,
        'btc_up': btc_up,
        'signal_fired': fired,
    }


def open_paper_trade(entry_price, balance):
    sl_price = entry_price * (1 - SL_PCT)
    tp_price = entry_price * (1 + TP_PCT)
    risk_amount = balance * RISK_PER_TRADE
    risk_per_unit = entry_price - sl_price
    size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
    return {
        'entry': entry_price,
        'tp': tp_price,
        'sl': sl_price,
        'size': round(size, 4),
        'opened_at': datetime.now(timezone.utc).isoformat(),
    }


def close_trade(trade, exit_price, reason, state):
    pnl = (exit_price - trade['entry']) * trade['size']
    state['balance'] += pnl
    state['history'].append({
        **trade,
        'exit': exit_price,
        'reason': reason,
        'closed_at': datetime.now(timezone.utc).isoformat(),
        'pnl': round(pnl, 4),
    })
    return pnl


def run_once():
    state = load_json(STATE_FILE, {'last_signal_ts': 0, 'active_trade': None})
    paper = load_json(PAPER_STATE, {'balance': START_BALANCE, 'open_trade': None, 'history': []})

    try:
        ex = get_working_exchange()
    except RuntimeError as e:
        msg = f"**EXCHANGE ERROR** | All exchanges failed at {datetime.now(timezone.utc).isoformat()}"
        print(msg)
        send(msg)
        return

    s = check_signal(ex)
    print(f"[{datetime.now(timezone.utc).isoformat()}] price={s['price']:.4f} "
          f"rsi2={s['rsi2']} uptrend={s['uptrend']} oversold={s['oversold']} "
          f"bb={s['bb_touch']} green={s['green']} vol={s['volume_ok']} btc={s['btc_up']}")

    price = s['price']
    t = paper.get('open_trade')
    if t:
        if price >= t['tp']:
            pnl = close_trade(t, t['tp'], 'TP', paper)
            send(f"**PAPER TP HIT** | AVAX entry `{t['entry']:.4f}` -> `{t['tp']:.4f}` | P&L `+${pnl:.2f}` | Balance `${paper['balance']:.2f}`")
            paper['open_trade'] = None
        elif price <= t['sl']:
            pnl = close_trade(t, t['sl'], 'SL', paper)
            send(f"**PAPER SL HIT** | AVAX entry `{t['entry']:.4f}` -> `{t['sl']:.4f}` | P&L `${pnl:.2f}` | Balance `${paper['balance']:.2f}`")
            paper['open_trade'] = None

    if s['signal_fired'] and s['ts'] != state.get('last_signal_ts'):
        tp = s['price'] * (1 + TP_PCT)
        sl = s['price'] * (1 - SL_PCT)
        send(f"**BUY SIGNAL** | AVAX/USDT | 1h\nEntry: `{s['price']:.4f}`\nTP: `{tp:.4f}` | SL: `{sl:.4f}`\nRSI2: `{s['rsi2']}`")
        state['last_signal_ts'] = s['ts']
        trade = open_paper_trade(s['price'], paper['balance'])
        paper['open_trade'] = trade
        send(f"**PAPER BUY** | AVAX entry `{trade['entry']:.4f}` | TP `{trade['tp']:.4f}` | SL `{trade['sl']:.4f}` | Size `{trade['size']}` | Balance `${paper['balance']:.2f}`")

    save_json(STATE_FILE, state)
    save_json(PAPER_STATE, paper)
    save_json(TRADES_FILE, paper.get('history', []))


if __name__ == '__main__':
    run_once()
