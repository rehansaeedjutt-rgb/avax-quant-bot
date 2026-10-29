"""
LINK COMBO 2 OPTIMIZER (Target: ~4 trades/mo, Best Profit Factor)
Optimizing: Volume Multiplier & RSI Threshold
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_data():
    df = pd.read_csv(f'{DATA_DIR}/LINK_USDT_1d_EXACT.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df.dropna()

def run_backtest(df, signal_col, tp_pct=0.05, sl_pct=0.03):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        
        if position:
            if high >= position['tp']:
                proceeds = position['units'] * position['tp'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                trades.append(((proceeds - fee) / position['cost'] - 1) * 100)
                position = None
            elif low <= position['sl']:
                proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                trades.append(((proceeds - fee) / position['cost'] - 1) * 100)
                position = None

        elif row[signal_col] and cash > 10:
            cost = cash * 0.95 
            units = cost / (close * (1 + SLIPPAGE))
            cash -= cost
            position = {
                'entry': close, 'units': units, 'cost': cost,
                'tp': close * (1 + tp_pct), 'sl': close * (1 - sl_pct)
            }

        equity.append(cash + (position['units'] * close if position else 0))

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100
    wins = sum(1 for t in trades if t > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gross_win = sum(t for t in trades if t > 0)
    gross_loss = abs(sum(t for t in trades if t <= 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    return ret_pct, wr, pf, dd, total

def generate_indicators(df):
    df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['above_ema50'] = df['c'] > df['ema50']
    
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    df['vol_sma20'] = df['v'].rolling(20).mean()
    return df.dropna()

if __name__ == '__main__':
    print("Loading LINK Data (2019 - 2026)...")
    df = load_data()
    df = generate_indicators(df)
    
    print(f"Total Daily Candles: {len(df)}\n")
    
    vol_mults = [1.1, 1.2, 1.3, 1.5]
    rsi_thresholds = [45, 50, 55]
    
    print('=' * 105)
    print('LINK COMBO 2 OPTIMIZER (Trend + Volume + RSI + MACD)')
    print('=' * 105)
    print(f'{"Vol Mult":>8} | {"RSI Thresh":>10} | {"Return":>9} | {"Trades":>7} | {"Trades/Mo":>10} | {"Win Rate":>9} | {"Profit Factor":>13} | {"Max DD":>8}')
    print('-' * 105)
    
    results = []
    
    for vol_mult in vol_mults:
        for rsi_thresh in rsi_thresholds:
            df['signal'] = df['above_ema50'] & (df['v'] > df['vol_sma20'] * vol_mult) & (df['rsi'] > rsi_thresh) & df['macd_bull']
            
            ret, wr, pf, dd, total = run_backtest(df, 'signal')
            trades_per_month = total / (len(df) / 30.44)
            
            print(f'{vol_mult:>8.1f} | {rsi_thresh:>10} | {ret:>8.2f}% | {total:>7} | {trades_per_month:>10.1f} | {wr:>8.2f}% | {pf:>13.2f} | {dd:>7.2f}%')
            
            results.append((vol_mult, rsi_thresh, ret, trades_per_month, wr, pf, dd))
            
    print('=' * 105)
    
    # Find best combo (Highest Return with PF > 1.4 and Trades/Mo > 2.5)
    best = None
    for r in results:
        vol_mult, rsi_thresh, ret, tpm, wr, pf, dd = r
        if pf > 1.4 and tpm >= 2.5:
            if best is None or ret > best[2]:
                best = r
                
    if best:
        print(f"\nRECOMMENDED COMBO: Volume Mult = {best[0]}x, RSI > {best[1]}")
        print(f"Return: {best[2]:.2f}% | Trades/Mo: {best[3]:.1f} | Win Rate: {best[4]:.2f}% | PF: {best[5]:.2f} | DD: {best[6]:.2f}%")
    else:
        print("\nNo combo met the strict criteria. Default to 1.5x Vol & RSI>50.")
