"""
SUPERTREND BACKTEST (2 Years)
- Trend following strategy with Hard Stop Loss
- Params: ATR 10, Multiplier 3.5, TP 2.0%, SL 3.0%
"""
import os
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, 'C:/avax_quant_system')
from strategies.supertrend_utils import supertrend

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df

def backtest(df, tp_pct=0.02, sl_pct=0.03):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    # Calculate Supertrend
    trend, up, dn = supertrend(df['h'].to_numpy(), df['l'].to_numpy(), df['c'].to_numpy(), period=10, multiplier=3.5)
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        close, high, low = row['c'], row['h'], row['l']
        
        if position:
            hours = i - position['bar']
            # Check TP
            if high >= position['tp']:
                proceeds = position['units'] * position['tp'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit = (proceeds - fee) - (position['units'] * position['entry'])
                trades.append({'profit_pct': (profit / (position['units'] * position['entry'])) * 100, 'type': 'TP'})
                position = None
            # Check SL
            elif low <= position['sl']:
                proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit = (proceeds - fee) - (position['units'] * position['entry'])
                trades.append({'profit_pct': (profit / (position['units'] * position['entry'])) * 100, 'type': 'SL'})
                position = None

        # Entry (Supertrend flips to UP)
        elif trend[i] == 1 and trend[i-1] == -1 and cash > 50:
            dollars = cash * 0.20 # 20% per trade
            units = dollars / (close * (1 + SLIPPAGE))
            cash -= dollars
            position = {
                'entry': close, 'units': units, 'tp': close * (1 + tp_pct),
                'sl': close * (1 - sl_pct), 'bar': i
            }

        current_equity = cash + (position['units'] * close if position else 0)
        equity.append(current_equity)

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0

    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'dd': dd}

if __name__ == '__main__':
    print('=' * 80)
    print('SUPERTREND BACKTEST (2 Years)')
    print('=' * 80)
    df = load()
    r = backtest(df)
    
    print(f"\nTotal Return   : {r['ret']:>8.2f}%")
    print(f"Total Trades   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")
