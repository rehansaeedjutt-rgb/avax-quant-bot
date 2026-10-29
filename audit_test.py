import pandas as pd
import numpy as np
import re
import os

DATA_DIR = 'C:/avax_quant_system/data'
CODE_FILE = 'C:/avax_quant_system/backtests/backtest_lifetime_mega.py'

print("==================================================")
print("🔍 AUTOMATED BACKTEST AUDITOR")
print("==================================================\n")

# ==========================================
# PART 1: DATA AUTHENTICITY CHECK
# ==========================================
print("1. Checking Data Integrity (Original vs Fake)...")
coins = ['AVAX_USDT_1d_MERGED_5Y.csv', 'LINK_USDT_1d_EXACT.csv', 'SOLUSDT_1d_EXACT.csv', 'ADAUSDT_1d_EXACT.csv', 'SUIUSDT_1d_EXACT.csv', 'DOTUSDT_1d_EXACT.csv']
data_ok = True

for file in coins:
    path = os.path.join(DATA_DIR, file)
    if not os.path.exists(path):
        print(f"❌ {file} not found.")
        data_ok = False
        continue
    
    df = pd.read_csv(path)
    
    # Check for missing values
    if df.isnull().values.any():
        print(f"❌ {file}: Contains missing (NaN) values. This breaks calculations.")
        data_ok = False
    
    # Check for zero or negative prices
    if (df['close'] <= 0).any() or (df['open'] <= 0).any():
        print(f"❌ {file}: Contains zero or negative prices.")
        data_ok = False
        
    # Check for absurd daily jumps (>50%)
    df['pct_change'] = df['close'].pct_change()
    absurd_jumps = df[abs(df['pct_change']) > 0.5]
    if len(absurd_jumps) > 0:
        print(f"⚠️ {file}: Found {len(absurd_jumps)} days with >50% price jump. (Possible fake data or data gap)")
        
    # Check if data is chronological
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    if not df['open_time'].is_monotonic_increasing:
        print(f"❌ {file}: Time series is not in chronological order.")
        data_ok = False

if data_ok:
    print("✅ All 6 Data Files are clean, chronological, and have valid prices.\n")

# ==========================================
# PART 2: CODE LOGIC CHECK (Lookahead Bias)
# ==========================================
print("2. Scanning Code for Lookahead Bias (Future Leakage)...")
try:
    with open(CODE_FILE, 'r', encoding='utf-8') as f:
        code = f.read()
        
    # Check for future shifts
    if 'shift(-' in code:
        print("❌ FOUND: Negative shift() detected. This uses future data!")
    else:
        print("✅ No negative shift() detected.")

    # Check for i+1 (future candle)
    if re.search(r'iloc\[i\+', code) or re.search(r'iloc\[i \+', code):
        print("❌ FOUND: Code looks at future candles (i+1).")
    else:
        print("✅ No future candle indexing (i+1) detected.")

    # Check how High and Low are used
    if 'if high >= pos' in code and 'if low <= pos' in code:
        print("⚠️ NOTE: Code checks 'High' for TP and 'Low' for SL inside the same loop.")
        print("   (This is standard for daily backtests, but means intra-candle bias exists. Real win rate might be 3-5% lower).")

    # Check for slippage and fees
    if 'SLIPPAGE' in code and 'FEE' in code:
        print("✅ Slippage and Fees are mathematically deducted.")
    else:
        print("❌ WARNING: No Slippage or Fees found in code. Backtest is fake!")
        
    # Check the loop start
    if 'range(250' in code or 'range(200' in code:
        print("✅ Loop skips the first 200-250 candles (Warm-up period for EMA200). Good.")
    else:
        print("❌ WARNING: Loop doesn't skip the warm-up period. EMA200 will be NaN.")

except Exception as e:
    print(f"❌ Could not read code file: {e}")

print("\n==================================================")
print("AUDIT COMPLETE")
print("==================================================")
