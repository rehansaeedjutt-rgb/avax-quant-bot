# fix_matic_ton.py
# Sirf MATIC aur TON ke liye — saare exchanges try karega
# Bugs fixed: ccxt.gate (not gateio), proper fallback

import os
import time
import ccxt
import pandas as pd

DATA_DIR = 'C:/avax_quant_system/data'
os.makedirs(DATA_DIR, exist_ok=True)

# coin: [(symbol, [exchanges])]
TARGETS = {
    'MATIC': [
        ('MATIC/USDT', ['kucoin', 'gate', 'bitget', 'bybit', 'okx', 'binance']),
        ('POL/USDT',   ['binance', 'bybit', 'okx', 'kucoin', 'gate', 'bitget']),
    ],
    'TON': [
        ('TON/USDT', ['bybit', 'okx', 'kucoin', 'gate', 'bitget', 'binance']),
    ],
}

def get_exchange(name):
    try:
        cls = getattr(ccxt, name)
        return cls({'enableRateLimit': True, 'timeout': 30000})
    except Exception as e:
        print(f"    ⚠️ cannot init {name}: {e}")
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

def try_fetch_one(coin, symbol, ex_name):
    """Try ONE exchange. Returns rows or None."""
    ex = get_exchange(ex_name)
    if ex is None:
        return None
    try:
        ex.load_markets()
        if symbol not in ex.markets:
            print(f"    ⚠️ {ex_name} has no {symbol}")
            return None
        since_ms = int(pd.Timestamp('2000-01-01').timestamp() * 1000)
        rows = fetch_full(ex, symbol, since_ms)
        if rows and len(rows) > 50:
            t0 = pd.to_datetime(rows[0][0], unit='ms').date()
            t1 = pd.to_datetime(rows[-1][0], unit='ms').date()
            print(f"    ✅ {ex_name} {symbol}: {len(rows)} candles ({t0} → {t1})")
            return rows
        else:
            print(f"    ⚠️ {ex_name} {symbol}: only {len(rows) if rows else 0} candles")
            return None
    except Exception as e:
        print(f"    ❌ {ex_name} {symbol}: {str(e)[:80]}")
        return None

def main():
    print("="*80)
    print("FIX MATIC + TON — All Exchanges")
    print("="*80)

    for coin, sources in TARGETS.items():
        print(f"\n[{coin}] — current data:")
        current_path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
        if os.path.exists(current_path):
            cur = pd.read_csv(current_path)
            cur_t0 = pd.to_datetime(cur['open_time'].iloc[0], unit='ms').date()
            cur_t1 = pd.to_datetime(cur['open_time'].iloc[-1], unit='ms').date()
            print(f"    {len(cur)} candles ({cur_t0} → {cur_t1})")

        all_rows = []
        used = []
        for symbol, exchanges in sources:
            for ex_name in exchanges:
                rows = try_fetch_one(coin, symbol, ex_name)
                if rows:
                    all_rows.extend(rows)
                    used.append(f"{ex_name}:{symbol}")
                    # If we got enough, break
                    if len(all_rows) >= 1500:
                        break
            if len(all_rows) >= 1500:
                break

        if not all_rows:
            print(f"    ❌ {coin} FAILED — no data from any source")
            continue

        # Merge with existing if present (so we don't lose old data)
        if os.path.exists(current_path):
            old = pd.read_csv(current_path)
            old_rows = old[['open_time','open','high','low','close','volume']].values.tolist()
            all_rows = old_rows + all_rows

        df = pd.DataFrame(all_rows, columns=['open_time','open','high','low','close','volume'])
        df = df.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
        df.to_csv(current_path, index=False)
        t0 = pd.to_datetime(df['open_time'].iloc[0], unit='ms').date()
        t1 = pd.to_datetime(df['open_time'].iloc[-1], unit='ms').date()
        print(f"    💾 SAVED: {current_path} | {len(df)} candles ({t0} → {t1})")
        print(f"    Sources: {', '.join(used)}")

if __name__ == '__main__':
    main()
