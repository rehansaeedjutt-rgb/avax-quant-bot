"""
LINK CONFLUENCE STRATEGY BACKTEST (Target: 4 Trades/Month, No DCA)
Tests different combinations of Trend, Momentum, and Volume.
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
    # Trend & Momentum
    df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['above_ema50'] = df['c'] > df['ema50']
    df['above_ema200'] = df['c'] > df['ema200']
    
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    df['rsi_bull'] = df['rsi'] > 50
    df['rsi_oversold'] = df['rsi'] < 40

    # Volume
    df['vol_sma20'] = df['v'].rolling(20).mean()
    df['vol_spike'] = df['v'] > df['vol_sma20'] * 1.5

    # 1. Trend + Momentum (Classic)
    df['combo1'] = df['above_ema50'] & df['macd_bull'] & df['rsi_bull']
    
    # 2. Trend + Volume Spike
    df['combo2'] = df['above_ema50'] & df['vol_spike'] & df['rsi_bull']
    
    # 3. Pullback + Momentum (Buy dip in uptrend)
    df['combo3'] = df['above_ema200'] & df['rsi_oversold'] & df['macd_bull']
    
    # 4. Strong Trend + Momentum (EMA 50 > EMA 200)
    df['combo4'] = df['above_ema50'] & (df['ema50'] > df['ema200']) & df['macd_bull'] & df['rsi_bull']

    return df.dropna()

if __name__ == '__main__':
    print("Loading LINK Data (2019 - 2026)...")
    df = load_data()
    df = generate_indicators(df)
    
    print(f"Total Daily Candles: {len(df)} (Approx 7.5 Years)\n")
    
    combos = [
        ('combo1', 'Trend (EMA50) + MACD + RSI>50'),
        ('combo2', 'Trend (EMA50) + Volume Spike + RSI>50'),
        ('combo3', 'Pullback: EMA200 + RSI<40 + MACD'),
        ('combo4', 'Strong Trend (EMA50>200) + MACD + RSI>50')
    ]
    
    print('=' * 105)
    print('LINK CONFLUENCE STRATEGY (No DCA, TP:5%, SL:3%)')
    print('=' * 105)
    print(f'{"Strategy":<45} | {"Return":>9} | {"Trades":>7} | {"Trades/Mo":>10} | {"Win Rate":>9} | {"Profit Factor":>13} | {"Max DD":>8}')
    print('-' * 105)
    
    for col, name in combos:
        ret, wr, pf, dd, total = run_backtest(df, col)
        trades_per_month = total / (len(df) / 30.44)
        print(f'{name:<45} | {ret:>8.2f}% | {total:>7} | {trades_per_month:>10.1f} | {wr:>8.2f}% | {pf:>13.2f} | {dd:>7.2f}%')
        
    print('=' * 105)
    print("\nNote: Target is ~4 trades/month. High Win Rate > 50% and Profit Factor > 1.5 is ideal.")
