"""
MEGA-FILTERED DCA BACKTEST (5 Years)
Filters used: RSI (14), EMA 200, MACD, (Funding/OI skipping for static data limit)
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1d_MERGED_5Y.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    
    # 1. EMA 200
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['above_ema'] = df['c'] > df['ema200']
    
    # 2. RSI (14)
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 3. MACD (12, 26, 9)
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bullish'] = macd > signal
    
    df = df.dropna()
    return df

def backtest(df, capital=1000.0, tp_pct=0.03, max_hold=14):
    cash = capital
    cycle = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        hours = 0
        
        if cycle:
            hours = i - cycle['start_bar']
            if high >= cycle['tp']:
                revenue = cycle['units'] * cycle['tp']
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100, 'type': 'TP'})
                cycle = None
            elif cycle['level'] < 3:
                if cycle['level'] == 1 and low <= cycle['start_price'] * 0.98:
                    add_cost = cycle['initial_cost'] * 0.30
                    if cash >= add_cost:
                        add_units = add_cost / close
                        cycle['units'] += add_units
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 2
                        cash -= add_cost
                elif cycle['level'] == 2 and low <= cycle['start_price'] * 0.96:
                    add_cost = cycle['initial_cost'] * 0.20
                    if cash >= add_cost:
                        add_units = add_cost / close
                        cycle['units'] += add_units
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 3
                        cash -= add_cost
            elif hours >= max_hold:
                revenue = cycle['units'] * close
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100, 'type': 'TIME'})
                cycle = None

        # MEGA FILTERS: Only Enter if Price > EMA200 AND RSI < 70 AND MACD is Bullish
        if cycle is None and cash > capital * 0.5:
            filter_ok = row['above_ema'] and (row['rsi'] < 70) and row['macd_bullish']
            
            if filter_ok:
                cost = capital * 0.5
                units = cost / close
                cash -= cost
                cycle = {
                    'start_bar': i, 'start_price': close, 'units': units, 
                    'cost': cost, 'initial_cost': cost, 'avg': close, 
                    'tp': close * (1 + tp_pct), 'level': 1
                }

        current_equity = cash + (cycle['units'] * close if cycle else 0)
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
    print('MEGA-FILTERED DCA BACKTEST (5 Years Daily)')
    print('=' * 80)
    df = load()
    r = backtest(df)
    
    print(f"\nTotal Return   : {r['ret']:>8.2f}%")
    print(f"Total Trades   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")
