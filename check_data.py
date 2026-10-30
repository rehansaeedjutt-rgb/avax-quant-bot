import pandas as pd
import os

DATA_DIR = 'C:/avax_quant_system/data'
files = ['BNBUSDT_1d_EXACT.csv', 'ETHUSDT_1d_EXACT.csv', 'HYPEUSDT_1d_EXACT.csv']

print("==================================================")
print("📊 DATA INTEGRITY CHECK")
print("==================================================")

for file in files:
    path = os.path.join(DATA_DIR, file)
    if os.path.exists(path):
        df = pd.read_csv(path)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        start = df['open_time'].iloc[0]
        end = df['open_time'].iloc[-1]
        days = (end - start).days
        print(f"✅ {file}: {len(df)} candles | {start.date()} to {end.date()} ({days} days)")
    else:
        print(f"❌ {file} not found!")
