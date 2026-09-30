import ccxt, pandas as pd, time, os

exchange = ccxt.binance({'enableRateLimit': True})
OUT = 'C:/avax_quant_system/data'
START = '2023-01-01T00:00:00Z'
LIMIT = 1000


def fetch_all(symbol, tf, since):
    all_data = []
    while True:
        try:
            data = exchange.fetch_ohlcv(symbol, tf, since=since, limit=LIMIT)
        except Exception as e:
            print(f'  Error: {e}, retrying in 5s')
            time.sleep(5)
            continue
        if not data:
            break
        all_data.extend(data)
        last_ts = data[-1][0]
        if last_ts == since:
            break
        since = last_ts + 1
        print(f'  {symbol} {tf}: {len(all_data)} rows up to {pd.to_datetime(last_ts, unit="ms")}')
        time.sleep(exchange.rateLimit / 1000)
    return all_data


def save(symbol, tf):
    print(f'\n=== {symbol} {tf} ===')
    since = exchange.parse8601(START)
    rows = fetch_all(symbol, tf, since)
    if not rows:
        print('No data')
        return
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    path = f'{OUT}/{symbol.replace("/", "_")}_{tf}.csv'
    df.to_csv(path, index=False)
    print(f'Saved {path} | rows={len(df)}')


if __name__ == '__main__':
    save('BTC/USDT', '1h')
    save('BTC/USDT', '15m')
    print('\nDone.')
