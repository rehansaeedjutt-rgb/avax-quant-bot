import os, urllib.request, zipfile, io
import pandas as pd
from datetime import datetime, timedelta

DATA_DIR = 'C:/avax_quant_system/data'
os.makedirs(DATA_DIR, exist_ok=True)

COINS = ['DOTUSDT', 'HYPEUSDT', 'XRPUSDT', 'SUIUSDT', 'ADAUSDT']
BASE_URL = 'https://data.binance.vision/data/spot/monthly/klines'

start_date = datetime(2020, 1, 1)
end_date = datetime(2026, 10, 1)

def download_and_merge(symbol):
    interval = '1d'
    all_data = []
    current = start_date
    while current <= end_date:
        year, month = current.year, current.month
        url = f'{BASE_URL}/{symbol}/{interval}/{symbol}-{interval}-{year}-{month:02d}.zip'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                csv_name = z.namelist()[0]
                with z.open(csv_name) as f:
                    df = pd.read_csv(f, header=None)
            cols = ['open_time','open','high','low','close','volume','close_time','quote_vol','trades','taker_buy_base','taker_buy_quote','ignore']
            df.columns = cols[:len(df.columns)]
            df['open_time'] = df['open_time'].astype(str).apply(lambda x: int(x)//1000 if int(x) > 1e15 else int(x))
            all_data.append(df)
        except Exception:
            pass
        current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)

    if not all_data:
        print(f'No data for {symbol}')
        return

    merged = pd.concat(all_data, ignore_index=True)
    merged = merged.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
    out = f'{DATA_DIR}/{symbol}_1d_EXACT.csv'
    merged.to_csv(out, index=False)
    print(f'Saved {len(merged):,} candles → {out}')

if __name__ == '__main__':
    for coin in COINS:
        print(f"Downloading {coin}...")
        download_and_merge(coin)
