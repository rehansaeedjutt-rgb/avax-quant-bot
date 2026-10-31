# download_new_9_coins.py
# ICP, FIL, ATOM, IMX, INJ, STX, RNDR, GRT, FET

import os
import time
import ccxt
import pandas as pd

DATA_DIR = 'C:/avax_quant_system/data'
os.makedirs(DATA_DIR, exist_ok=True)

COINS = {
    'ICP':  [('ICP/USDT',  ['binance','bybit','okx','kucoin','gate','bitget'])],
    'FIL':  [('FIL/USDT',  ['binance','bybit','okx','kucoin','gate','bitget'])],
    'ATOM': [('ATOM/USDT', ['binance','bybit','okx','kucoin','gate','bitget'])],
    'IMX':  [('IMX/USDT',  ['binance','bybit','okx','kucoin','gate','bitget'])],
    'INJ':  [('INJ/USDT',  ['binance','bybit','okx','kucoin','gate','bitget'])],
    'STX':  [('STX/USDT',  ['binance','bybit','okx','kucoin','gate','bitget'])],
    'RNDR': [('RNDR/USDT', ['binance','bybit','okx','kucoin','gate','bitget'])],
    'GRT':  [('GRT/USDT',  ['binance','bybit','okx','kucoin','gate','bitget'])],
    'FET':  [('FET/USDT',  ['binance','bybit','okx','kucoin','gate','bitget'])],
}

def get_exchange(name):
    try:
        cls = getattr(ccxt, name)
        return cls({'enableRateLimit': True, 'timeout': 30000})
    except Exception as e:
        print(f"  ⚠️ cannot init {name}: {e}")
        return None

def fetch_full(exchange, symbol, since_ms):
    rows = []
    cursor = since_ms
    retries = 0
    while True:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe='1d', since=cursor, limit=1000)
            retries = 0
        except Exception as e:
            retries += 1
            if retries >= 4:
                return []
            time.sleep(2 * retries)
            continue
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        time.sleep(exchange.rateLimit / 1000.0)
        if len(batch) < 1000:
            break
    return rows

def try_fetch(coin, symbol, exchanges):
    for ex_name in exchanges:
        ex = get_exchange(ex_name)
        if ex is None:
            continue
        try:
            ex.load_markets()
            if symbol not in ex.markets:
                print(f"  ⚠️ {ex_name} has no {symbol}")
                continue
            since_ms = int(pd.Timestamp('2000-01-01').timestamp() * 1000)
            rows = fetch_full(ex, symbol, since_ms)
            if rows and len(rows) > 50:
                return rows, ex_name
        except Exception as e:
            print(f"  ❌ {ex_name}: {str(e)[:60]}")
            continue
    return None, None

def main():
    print("="*80)
    print("DOWNLOAD NEW 9 COINS")
    print("="*80)
    summary = []
    for coin, sources in COINS.items():
        print(f"\n[{coin}]")
        all_rows = []
        used = []
        for symbol, exchanges in sources:
            rows, ex = try_fetch(coin, symbol, exchanges)
            if rows:
                all_rows.extend(rows)
                used.append(f"{ex}:{symbol}")
                print(f"  ✅ got {len(rows)} from {ex}")

        if not all_rows:
            print(f"  ❌ FAILED")
            summary.append({'coin':coin,'status':'FAILED','candles':0,'first':'-','last':'-'})
            continue

        df = pd.DataFrame(all_rows, columns=['open_time','open','high','low','close','volume'])
        df = df.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
        path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
        df.to_csv(path, index=False)
        t0 = pd.to_datetime(df['open_time'].iloc[0], unit='ms').date()
        t1 = pd.to_datetime(df['open_time'].iloc[-1], unit='ms').date()
        print(f"  💾 {path} | {len(df)} candles | {t0} → {t1} | {', '.join(used)}")
        summary.append({'coin':coin,'status':'OK','candles':len(df),'first':t0,'last':t1})

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    for s in summary:
        print(f"{s['coin']:6} | {s['status']:8} | {s['candles']:5} candles | {s['first']} → {s['last']}")

if __name__ == '__main__':
    main()
