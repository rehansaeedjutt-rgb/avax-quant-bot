import os
import sys
import json
import time
from datetime import datetime, timezone

import ccxt
import pandas as pd

sys.path.insert(0, 'C:/avax_quant_system')
from discord_bot.notify import send
import src.paper_trader as paper

ROOT = 'C:/avax_quant_system'
STATE_FILE = f'{ROOT}/config/scanner_state.json'
SYMBOL = 'AVAX/USDT'
TIMEFRAME = '1h'
LIMIT = 500

TP_PCT = 0.007
SL_PCT = 0.025
RSI2_MAX = 12
BB_PERIOD = 20
BB_MULT = 2.0
VOL_FACTOR = 0.8


def load_state():
    if not os.path.exists(STATE_FILE):
        return {'last_signal_ts': 0}
    with open(STATE_FILE, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


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


def fetch_avax():
    ex = ccxt.binance({'enableRateLimit': True})
    raw = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.set_index('ts')
    return df


def fetch_btc_up():
    ex = ccxt.binance({'enableRateLimit': True})
    raw = ex.fetch_ohlcv('BTC/USDT', TIMEFRAME, limit=LIMIT)
    df = pd.DataFrame(raw, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['close'] = df['close'].astype(float)
    ema = df['close'].ewm(span=50, adjust=False).mean()
    return bool(df['close'].iloc[-1] > ema.iloc[-1])


def check_signal():
    df = fetch_avax()
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
    btc_up = fetch_btc_up()

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


def run_once(verbose=True):
    state = load_state()
    s = check_signal()
    if verbose:
        print(f"[{datetime.now(timezone.utc).isoformat()}] price={s['price']:.4f} "
              f"rsi2={s['rsi2']} uptrend={s['uptrend']} oversold={s['oversold']} "
              f"bb={s['bb_touch']} green={s['green']} vol={s['volume_ok']} btc={s['btc_up']}")

    # Paper trader always checks open trade for TP/SL
    paper.update(signal_fired=False)

    if s['signal_fired'] and s['ts'] != state.get('last_signal_ts'):
        tp = s['price'] * (1 + TP_PCT)
        sl = s['price'] * (1 - SL_PCT)
        send(f"**BUY SIGNAL** | AVAX/USDT | 1h\nEntry: `{s['price']:.4f}`\n"
             f"TP: `{tp:.4f}` | SL: `{sl:.4f}`\nRSI2: `{s['rsi2']}`")
        state['last_signal_ts'] = s['ts']
        save_state(state)
        paper.update(signal_fired=True)
        print('[SCANNER] BUY signal fired + paper trade opened')
    return s


def run_forever(interval_minutes=60):
    print(f'[SCANNER] Loop every {interval_minutes} min. Ctrl+C to stop.')
    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            print('\n[SCANNER] Stopped')
            break
        except Exception as e:
            print(f'[SCANNER] Error: {e}')
        time.sleep(interval_minutes * 60)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'once'
    if mode == 'loop':
        run_forever()
    else:
        run_once()
