import ccxt
import pandas as pd
import time
import os
import sys

# Binance for free historical data
exchange = ccxt.binance({'enableRateLimit': True})

output_dir = 'C:/avax_quant_system/data'
os.makedirs(output_dir, exist_ok=True)

# Start from 2023-01-01
START_DATE = '2023-01-01T00:00:00Z'
LIMIT = 1000


def fetch_all_ohlcv(symbol, timeframe, since, limit=LIMIT):
    all_data = []
    retries = 0
    while True:
        try:
            data = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
        except Exception as e:
            print(f'  Error: {e}. Retrying in 5s...')
            time.sleep(5)
            retries += 1
            if retries > 5:
                print('  Too many errors. Stopping this timeframe.')
                break
            continue
        if not data or len(data) == 0:
            break
        all_data.extend(data)
        last_ts = data[-1][0]
        if last_ts == since:
            break
        since = last_ts + 1
        print(f'  Fetched up to {pd.to_datetime(last_ts, unit="ms")}, total rows: {len(all_data)}')
        time.sleep(exchange.rateLimit / 1000)
    return all_data


def save_ohlcv(symbol, timeframe, start_iso):
    print(f'\n=== Downloading {symbol} {timeframe} ===')
    since = exchange.parse8601(start_iso)
    rows = fetch_all_ohlcv(symbol, timeframe, since)
    if not rows:
        print(f'No data for {symbol} {timeframe}')
        return
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    safe_symbol = symbol.replace('/', '_')
    filepath = f'{output_dir}/{safe_symbol}_{timeframe}.csv'
    df.to_csv(filepath, index=False)
    print(f'Saved {filepath} | rows={len(df)} | from {df["timestamp"].iloc[0]} to {df["timestamp"].iloc[-1]}')


if __name__ == '__main__':
    timeframes = ['15m', '1h', '4h', '1d', '1w']

    # AVAX/USDT on all timeframes
    for tf in timeframes:
        save_ohlcv('AVAX/USDT', tf, START_DATE)

    # BTC/USDT on 1D and 4H for BTC dominance / trend filter
    for tf in ['4h', '1d']:
        save_ohlcv('BTC/USDT', tf, START_DATE)

    print('\nAll downloads complete.')