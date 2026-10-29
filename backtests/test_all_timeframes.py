"""
MULTI-TIMEFRAME COMPARISON (5.5 Years)
Testing the MACD + EMA200 + DCA Strategy on 1H, 4H, 1D, 1W
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_1h_data():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED_5Y.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df

def run_backtest(df, tf_name):
    # 1. Calculate Indicators
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['above_ema'] = df['c'] > df['ema200']
    
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    df = df.dropna()

    # 2. Backtest Logic (DCA 50/30/20, TP 4%)
    capital = 1000.0
    cash = capital
    cycle = None
    trades = []
    equity = []
    tp_pct = 0.04
    
    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        
        if cycle:
            # Check TP
            if high >= cycle['tp']:
                revenue = cycle['units'] * cycle['tp']
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100})
                cycle = None
            # Check DCA
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
            # Time Exit (14 Days) - adjusted for timeframe bars
            elif i - cycle['start_bar'] >= cycle['max_bars']:
                revenue = cycle['units'] * close
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100})
                cycle = None

        if cycle is None and cash > capital * 0.5:
            # Only enter if MACD and EMA200 are Bullish
            if row['macd_bull'] and row['above_ema']:
                cost = capital * 0.5
                units = cost / close
                cash -= cost
                
                # Max hold in bars based on timeframe (14 days)
                if tf_name == '1H': max_bars = 14 * 24
                elif tf_name == '4H': max_bars = 14 * 6
                elif tf_name == '1D': max_bars = 14
                else: max_bars = 2 # 1W

                cycle = {
                    'start_bar': i, 'start_price': close, 'units': units, 
                    'cost': cost, 'initial_cost': cost, 'avg': close, 
                    'tp': close * (1 + tp_pct), 'level': 1, 'max_bars': max_bars
                }

        current_equity = cash + (cycle['units'] * close if cycle else 0)
        equity.append(current_equity)

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100 if len(eq_arr) > 0 else 0
    final = eq_arr[-1] if len(eq_arr) > 0 else capital
    ret_pct = (final - capital) / capital * 100
    
    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gross_win = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gross_loss = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] <= 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    
    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'pf': pf, 'dd': dd}

if __name__ == '__main__':
    print("Loading 1H Data...")
    df_1h = load_1h_data()
    
    # Resample data
    print("Resampling to 4H, 1D, 1W...")
    df_4h = df_1h.resample('4h').agg({'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}).dropna()
    df_1d = df_1h.resample('1D').agg({'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}).dropna()
    df_1w = df_1h.resample('1W').agg({'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}).dropna()

    print('\n' + '=' * 85)
    print('MULTI-TIMEFRAME RESULTS (MACD + EMA200 + DCA)')
    print('=' * 85)
    print(f'{"Timeframe":<12} | {"Return":>10} | {"Trades":>7} | {"Win Rate":>9} | {"Profit Factor":>13} | {"Max DD":>8}')
    print('-' * 85)
    
    # Run backtests
    for name, data in [('1-Hour', df_1h), ('4-Hour', df_4h), ('1-Day', df_1d), ('1-Week', df_1w)]:
        r = run_backtest(data, name)
        print(f'{name:<12} | {r["ret"]:>9.2f}% | {r["trades"]:>7} | {r["wr"]:>8.2f}% | {r["pf"]:>13.2f} | {r["dd"]:>7.2f}%')
    
    print('=' * 85)
