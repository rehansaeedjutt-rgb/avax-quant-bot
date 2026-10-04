import os
import pandas as pd
import glob

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')

SYMBOL = 'AVAXUSDT'
INTERVALS = ['15m', '1h', '4h', '1d']


def normalize_timestamp(ts):
    """Binance uses ms before 2025, us after. Auto-detect by magnitude."""
    ts = int(ts)
    if ts > 1e15:
        # microseconds
        return ts // 1000
    return ts


print('=' * 70)
print('DATA AUDIT + MERGE (fixed)')
print('=' * 70)
print()

summary = {}

for interval in INTERVALS:
    files = sorted(glob.glob(f'{DATA_DIR}/{SYMBOL}_{interval}_*.csv'))
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f)
            dfs.append(df)
        except Exception as e:
            print(f'  SKIP {os.path.basename(f)}: {e}')

    if not dfs:
        continue

    merged = pd.concat(dfs, ignore_index=True)
    merged['open_time'] = merged['open_time'].apply(normalize_timestamp)
    merged = merged.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)

    out_path = f'{DATA_DIR}/AVAX_USDT_{interval}_MERGED.csv'
    merged.to_csv(out_path, index=False)

    first_ts = pd.to_datetime(merged['open_time'].iloc[0], unit='ms')
    last_ts = pd.to_datetime(merged['open_time'].iloc[-1], unit='ms')

    summary[interval] = {'candles': len(merged), 'first': first_ts, 'last': last_ts}
    print(f'{interval:>4}: {len(merged):>8,} candles | {first_ts} -> {last_ts}')

print()
print('=' * 70)
total = sum(v["candles"] for v in summary.values())
print(f'TOTAL CANDLES: {total:,}')
print('=' * 70)
