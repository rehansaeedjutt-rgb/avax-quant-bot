"""
DCA LADDER BACKTEST (2-Year Data)
Rules:
- Buy 50% of capital at market.
- If price drops 2%, buy 30%.
- If price drops 4%, buy 20%.
- Sell ALL when price hits +3% profit.
- NO STOP LOSS. Hold until profit.
- Max Hold: 14 days (for safety).
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
FEE = 0.0005

def load():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df

def dca_backtest(df, capital=1000.0, tp_pct=0.03, max_hold=336): # 336h = 14 days
    cash = capital
    cycle = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        hours = 0
        
        if cycle:
            hours = i - cycle['start_bar']
            # 1. Check Take Profit (Use High price of the candle)
            if high >= cycle['tp']:
                # Sell all
                revenue = cycle['units'] * cycle['tp']
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100, 'type': 'TP', 'held': hours})
                cycle = None
            
            # 2. Check DCA Levels (Use Low price of the candle)
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

            # 3. Max Hold Exit (Breakeven if possible)
            elif hours >= max_hold:
                revenue = cycle['units'] * close
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100, 'type': 'TIME', 'held': hours})
                cycle = None

        # Start a new cycle
        if cycle is None and cash > capital * 0.5:
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

    if cycle:
        cash += cycle['units'] * df['c'].iloc[-1]

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    
    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'dd': dd, 'final': final}

if __name__ == '__main__':
    print('=' * 80)
    print('DCA LADDER BACKTEST (2 Years)')
    print('=' * 80)
    df = load()
    r = dca_backtest(df)
    
    print(f"\nFinal Balance  : ${r['final']:.2f}")
    print(f"Total Return   : {r['ret']:>8.2f}%")
    print(f"Total Cycles   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")
