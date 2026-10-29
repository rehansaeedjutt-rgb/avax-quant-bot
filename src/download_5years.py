"""
DOWNLOAD 5+ YEARS OF DATA (Sep 2020 - Oct 2026) AND RUN BACKTESTS
"""
import os
import urllib.request
import zipfile
import io
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

SYMBOL = 'AVAXUSDT'
INTERVALS = ['1h', '4h', '1d']
BASE_URL = 'https://data.binance.vision/data/spot/monthly/klines'

# Sep 2020 to Oct 2026 (approx 74 months)
start_date = datetime(2020, 9, 1)
end_date = datetime(2026, 10, 1)

def download_and_merge(interval):
    print(f'\n--- Downloading {interval} data ---')
    all_data = []
    current = start_date
    while current <= end_date:
        year = current.year
        month = current.month
        month_str = f'{month:02d}'
        url = f'{BASE_URL}/{SYMBOL}/{interval}/{SYMBOL}-{interval}-{year}-{month_str}.zip'
        
        try:
            print(f'  Fetching {year}-{month_str}...')
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                csv_name = z.namelist()[0]
                with z.open(csv_name) as f:
                    df = pd.read_csv(f, header=None)
            
            # Binance columns
            cols = ['open_time','open','high','low','close','volume',
                    'close_time','quote_vol','trades','taker_buy_base',
                    'taker_buy_quote','ignore']
            df.columns = cols[:len(df.columns)]
            
            # Handle timestamp units (ms vs us)
            df['open_time'] = df['open_time'].astype(str).apply(
                lambda x: int(x)//1000 if int(x) > 1e15 else int(x)
            )
            all_data.append(df)
        except Exception as e:
            # Skip if month doesn't exist
            pass
        current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)

    if not all_data:
        print(f'  No data found for {interval}')
        return None

    merged = pd.concat(all_data, ignore_index=True)
    merged = merged.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
    
    out_path = f'{DATA_DIR}/AVAX_USDT_{interval}_MERGED_5Y.csv'
    merged.to_csv(out_path, index=False)
    print(f'  Saved {len(merged):,} candles -> {out_path}')
    return out_path

if __name__ == '__main__':
    print('=' * 80)
    print('DOWNLOADING 5+ YEARS OF DATA (Sep 2020 - Oct 2026)')
    print('=' * 80)
    
    for tf in INTERVALS:
        download_and_merge(tf)
