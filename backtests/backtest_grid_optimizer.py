"""
ADVANCED GRID SEARCH — Finding the absolute BEST combination
"""
import os
import numpy as np
import pandas as pd
import itertools

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_data():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1d_MERGED_5Y.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    
    # Base Filters
    ema200 = df['c'].ewm(span=200, adjust=False).mean()
    df['above_ema'] = df['c'] > ema200
    
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    # RSI
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    
    # AVAX/BTC Ratio (Fetching BTC 1d data)
    try:
        btc = pd.read_csv(f'{DATA_DIR}/BTC_USDT_1d.csv')
        btc['timestamp'] = pd.to_datetime(btc['timestamp'])
        btc = btc.set_index('timestamp').sort_index()
        merged = df[['c']].join(btc[['close']], how='inner')
        merged['ratio'] = merged['c'] / merged['close']
        merged['ratio_ema20'] = merged['ratio'].ewm(span=20, adjust=False).mean()
        df['ratio_up'] = merged['ratio'] > merged['ratio_ema20']
    except Exception:
        df['ratio_up'] = True # If BTC data missing, default to true
        
    return df.dropna()

def backtest(df, tp_pct, dca_drops, dca_weights, use_rsi, use_ratio):
    capital = 1000.0
    cash = capital
    cycle = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        
        if cycle:
            hours = i - cycle['start_bar']
            if high >= cycle['tp']:
                revenue = cycle['units'] * cycle['tp']
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100})
                cycle = None
            elif cycle['level'] < 3:
                if cycle['level'] == 1 and low <= cycle['start_price'] * (1 - dca_drops[0]):
                    add_cost = cycle['initial_cost'] * dca_weights[1]
                    if cash >= add_cost:
                        add_units = add_cost / close
                        cycle['units'] += add_units
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 2
                        cash -= add_cost
                elif cycle['level'] == 2 and low <= cycle['start_price'] * (1 - dca_drops[1]):
                    add_cost = cycle['initial_cost'] * dca_weights[2]
                    if cash >= add_cost:
                        add_units = add_cost / close
                        cycle['units'] += add_units
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 3
                        cash -= add_cost
            elif hours >= 14: # 14 days max hold
                revenue = cycle['units'] * close
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100})
                cycle = None

        if cycle is None and cash > capital * dca_weights[0]:
            filter_ok = row['macd_bull'] and row['above_ema']
            if use_rsi: filter_ok = filter_ok and (row['rsi'] < 70)
            if use_ratio: filter_ok = filter_ok and (row['ratio_up'])
            
            if filter_ok:
                cost = capital * dca_weights[0]
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
    gross_win = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gross_loss = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] <= 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    
    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'dd': dd, 'pf': pf}

if __name__ == '__main__':
    print("Loading and calculating indicators...")
    df = load_data()
    
    # Parameters to test
    tps = [0.025, 0.030, 0.035, 0.040]
    dca_plans = [
        ("A: 50/30/20 (-2/-4)", [0.02, 0.04], [0.50, 0.30, 0.20]),
        ("B: 33/33/33 (-1.5/-3)", [0.015, 0.03], [0.33, 0.33, 0.34]),
        ("C: 40/30/30 (-2.5/-5)", [0.025, 0.05], [0.40, 0.30, 0.30])
    ]
    filters = [
        ("Base", False, False),
        ("+ RSI", True, False),
        ("+ Ratio", False, True),
        ("+ RSI + Ratio", True, True)
    ]
    
    results = []
    
    for tp in tps:
        for plan_name, drops, weights in dca_plans:
            for f_name, use_rsi, use_ratio in filters:
                r = backtest(df, tp, drops, weights, use_rsi, use_ratio)
                name = f"TP:{tp*100}% | {plan_name} | {f_name}"
                results.append((name, r))
                
    # Sort by Return descending, but only keep those with PF > 1.5
    results = [x for x in results if x[1]['pf'] > 1.5]
    results.sort(key=lambda x: x[1]['ret'], reverse=True)
    
    print('\n' + '=' * 105)
    print(f'{"Configuration":<48} | {"Return":>10} | {"Trades":>6} | {"WR%":>6} | {"PF":>5} | {"DD%":>7}')
    print('=' * 105)
    
    for name, r in results[:10]:
        print(f'{name:<48} | {r["ret"]:>9.2f}% | {r["trades"]:>6} | {r["wr"]:>6.2f} | {r["pf"]:>5.2f} | {r["dd"]:>7.2f}%')
    
    print('=' * 105)
