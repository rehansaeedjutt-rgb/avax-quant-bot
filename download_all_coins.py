# download_all_coins.py
# 21 coins ka inception-to-now 1D data download karta hai
# Binance -> Bybit -> OKX fallback (CCXT)
# Saves to data/ folder in same format as existing CSVs

import os
import time
import ccxt
import pandas as pd

DATA_DIR = 'C:/avax_quant_system/data'
os.makedirs(DATA_DIR, exist_ok=True)

# Coin -> (symbol, exchange_preference, start_date_override)
# symbol format: BTC/USDT. Some coins may need different pairs.
COINS = {
    'BTC':   {'symbol': 'BTC/USDT',  'start': '2017-08-17'},
    'ETH':   {'symbol': 'ETH/USDT',  'start': '2017-08-17'},
    'BNB':   {'symbol': 'BNB/USDT',  'start': '2017-11-06'},
    'XRP':   {'symbol': 'XRP/USDT',  'start': '2018-05-04'},
    'DOGE':  {'symbol': 'DOGE/USDT', 'start': '2019-07-05'},
    'LTC':   {'symbol': 'LTC/USDT',  'start': '2017-12-13'},
    'BCH':   {'symbol': 'BCH/USDT',  'start': '2019-11-15'},
    'LINK':  {'symbol': 'LINK/USDT', 'start': '2019-01-16'},
    'AVAX':  {'symbol': 'AVAX/USDT', 'start': '2020-09-22'},
    'SOL':   {'symbol': 'SOL/USDT',  'start': '2020-08-11'},
    'ADA':   {'symbol': 'ADA/USDT',  'start': '2018-04-17'},
    'DOT':   {'symbol': 'DOT/USDT',  'start': '2020-08-18'},
    'SUI':   {'symbol': 'SUI/USDT',  'start': '2023-05-03'},
    'HYPE':  {'symbol': 'HYPE/USDT', 'start': '2025-07-11', 'exchanges': ['bybit']},
    'MATIC': {'symbol': 'MATIC/USDT','start': '2019-04-28', 'exchanges': ['binance','bybit','okx']},
    'TON':   {'symbol': 'TON/USDT',  'start': '2024-08-08', 'exchanges': ['binance','bybit','okx']},
    'SHIB':  {'symbol': 'SHIB/USDT', 'start': '2021-05-10'},
    'NEAR':  {'symbol': 'NEAR/USDT', 'start': '2020-10-14'},
    'APT':   {'symbol': 'APT/USDT',  'start': '2022-10-19'},
    'ARB':   {'symbol': 'ARB/USDT',  'start': '2023-03-23'},
    'OP':    {'symbol': 'OP/USDT',   'start': '2022-06-01'},
}

def get_exchange(name):
    cls = getattr(ccxt, name)
    return cls({'enableRateLimit': True, 'timeout': 30000})

def fetch_ohlcv_full(exchange, symbol, since_ms):
    all_rows = []
    limit = 1000
    cursor = since_ms
    retries = 0
    while True:
        try:
            rows = exchange.fetch_ohlcv(symbol, timeframe='1d', since=cursor, limit=limit)
            retries = 0
        except Exception as e:
            retries += 1
            print(f"    retry {retries}: {str(e)[:80]}")
            if retries >= 5:
                print(f"    FAILED after 5 retries for {symbol}")
                break
            time.sleep(2 * retries)
            continue
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = rows[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        print(f"    fetched {len(rows)} rows, total={len(all_rows)}")
        time.sleep(exchange.rateLimit / 1000.0)
        if len(rows) < limit:
            break
    return all_rows

def save_csv(coin, rows):
    df = pd.DataFrame(rows, columns=['open_time','open','high','low','close','volume'])
    df = df.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
    path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
    df.to_csv(path, index=False)
    return path, len(df), df['open_time'].iloc[0], df['open_time'].iloc[-1]

def try_download(coin, cfg):
    symbol = cfg['symbol']
    exchanges = cfg.get('exchanges', ['binance','bybit','okx'])
    start_ts = int(pd.Timestamp(cfg['start']).timestamp() * 1000)

    for ex_name in exchanges:
        print(f"\n[{coin}] trying {ex_name} for {symbol}")
        try:
            ex = get_exchange(ex_name)
            ex.load_markets()
            if symbol not in ex.markets:
                print(f"    {symbol} not listed on {ex_name}")
                continue
            rows = fetch_ohlcv_full(ex, symbol, start_ts)
            if not rows:
                print(f"    no data from {ex_name}")
                continue
            path, n, t0, t1 = save_csv(coin, rows)
            print(f"    SUCCESS: {path} | {n} candles | {pd.to_datetime(t0, unit='ms')} -> {pd.to_datetime(t1, unit='ms')}")
            return True
        except Exception as e:
            print(f"    {ex_name} error: {str(e)[:100]}")
            continue
    print(f"[{coin}] FAILED on all exchanges")
    return False

if __name__ == '__main__':
    print("="*70)
    print("DOWNLOADING 21 COINS — INCEPTION TO NOW")
    print("="*70)
    ok, fail = [], []
    for coin, cfg in COINS.items():
        try:
            if try_download(coin, cfg):
                ok.append(coin)
            else:
                fail.append(coin)
        except Exception as e:
            print(f"[{coin}] UNEXPECTED ERROR: {e}")
            fail.append(coin)

    print("\n" + "="*70)
    print("DOWNLOAD SUMMARY")
    print("="*70)
    print(f"SUCCESS ({len(ok)}): {', '.join(ok)}")
    print(f"FAILED ({len(fail)}): {', '.join(fail) if fail else 'none'}")
