"""
DOWNLOAD HYPE DATA FROM OKX/BYBIT (CCXT)
"""
import ccxt
import pandas as pd
import time
from datetime import datetime

DATA_DIR = 'C:/avax_quant_system/data'

def download_hype():
    exchanges = ['okx', 'bybit', 'kucoin']
    
    for ex_id in exchanges:
        try:
            print(f"Trying {ex_id}...")
            ex = getattr(ccxt, ex_id)({'enableRateLimit': True})
            ex.load_markets()
            
            # Check if HYPE/USDT exists on this exchange
            if 'HYPE/USDT' not in ex.markets and 'HYPE/USDT:USDT' not in ex.markets:
                print(f"  {ex_id} does not have HYPE/USDT. Skipping.")
                continue
                
            symbol = 'HYPE/USDT'
            all_data = []
            since = ex.parse8601('2024-11-01T00:00:00Z') # HYPE launch approx date
            
            while True:
                try:
                    ohlcv = ex.fetch_ohlcv(symbol, '1d', since=since, limit=1000)
                except Exception as e:
                    print(f"  Error fetching from {ex_id}: {e}")
                    break
                    
                if not ohlcv:
                    break
                    
                all_data.extend(ohlcv)
                since = ohlcv[-1][0] + 1
                print(f"  Fetched {len(all_data)} candles so far from {ex_id}...")
                time.sleep(ex.rateLimit / 1000)
                
                if len(ohlcv) < 1000:
                    break

            if all_data:
                df = pd.DataFrame(all_data, columns=['open_time','open','high','low','close','volume'])
                df = df.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
                out = f'{DATA_DIR}/HYPEUSDT_1d_EXACT.csv'
                df.to_csv(out, index=False)
                print(f"✅ Saved {len(df)} candles from {ex_id} → {out}")
                return
                
        except Exception as e:
            print(f"Failed on {ex_id}: {e}")
            
    print("❌ Could not download HYPE data from any exchange.")

if __name__ == '__main__':
    download_hype()
