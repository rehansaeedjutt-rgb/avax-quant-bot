import os
import pandas as pd
from datetime import datetime, timedelta

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Binance public data (no API key, no rate limit)
# Format: https://data.binance.vision/data/spot/monthly/klines/SYMBOL/TF/SYMBOL-TF-YEAR-MONTH.zip

import urllib.request
import zipfile
import io

SYMBOL = 'AVAXUSDT'
INTERVALS = ['15m', '1h', '4h', '1d']
BASE = 'https://data.binance.vision/data/spot/monthly/klines'

def download_month(symbol, interval, year, month):
    month_str = f'{month:02d}'
    url = f'{BASE}/{symbol}/{interval}/{symbol}-{interval}-{year}-{month_str}.zip'
    out_csv = f'{DATA_DIR}/{symbol}_{interval}_{year}_{month_str}.csv'
    if os.path.exists(out_csv):
        return True
    try:
        print(f'  Downloading {symbol} {interval} {year}-{month_str}...')
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                df = pd.read_csv(f, header=None)
        # Binance kline columns
        cols = ['open_time','open','high','low','close','volume',
                'close_time','quote_vol','trades','taker_buy_base',
                'taker_buy_quote','ignore']
        df.columns = cols[:len(df.columns)]
        df.to_csv(out_csv, index=False)
        return True
    except Exception as e:
        print(f'  SKIP {year}-{month_str}: {str(e)[:80]}')
        return False


# Download last 24 months
end = datetime(2026, 9, 1)
start = end - timedelta(days=730)

print('Phase 1: Downloading AVAX/USDT historical data from Binance')
print('=' * 70)

for interval in INTERVALS:
    print(f'\n--- {interval} ---')
    count = 0
    current = start
    while current < end:
        if download_month(SYMBOL, interval, current.year, current.month):
            count += 1
        current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
    print(f'  Downloaded {count} months')

print('\n' + '=' * 70)
print('Phase 1 Complete. Files in:', DATA_DIR)
