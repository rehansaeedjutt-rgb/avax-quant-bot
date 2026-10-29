"""
LINK EXACT BACKTEST (2019 - 2026)
"""
import os, numpy as np, pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load(tf='1d'):
    df = pd.read_csv(f'{DATA_DIR}/LINK_USDT_{tf}_EXACT.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['above_ema'] = df['c'] > df['ema200']
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    return df.dropna()

def backtest(df, tp_pct, dca1_drop, dca2_drop):
    capital = 1000.0
    cash = capital
    cycle = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        if cycle:
            if high >= cycle['tp']:
                revenue = cycle['units'] * cycle['tp']
                fee = revenue * FEE
                cash += (revenue - fee)
                trades.append({'profit_pct': tp_pct*100})
                cycle = None
            elif cycle['level'] < 3:
                if cycle['level'] == 1 and low <= cycle['start_price'] * (1 - dca1_drop):
                    add_cost = cycle['initial_cost'] * 0.30
                    if cash >= add_cost:
                        cycle['units'] += add_cost / close
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 2
                        cash -= add_cost
                elif cycle['level'] == 2 and low <= cycle['start_price'] * (1 - dca2_drop):
                    add_cost = cycle['initial_cost'] * 0.20
                    if cash >= add_cost:
                        cycle['units'] += add_cost / close
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 3
                        cash -= add_cost
        elif cash > capital * 0.5 and row['macd_bull'] and row['above_ema']:
            cost = capital * 0.5
            units = cost / close
            cash -= cost
            cycle = {
                'start_price': close, 'units': units, 'cost': cost,
                'initial_cost': cost, 'avg': close,
                'tp': close * (1 + tp_pct), 'level': 1
            }
        equity.append(cash + (cycle['units'] * close if cycle else 0))

    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = ((eq - peak) / peak).min() * 100
    final = eq[-1]
    ret = (final - capital) / capital * 100
    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    wr = (wins / len(trades) * 100) if trades else 0
    return ret, wr, dd, len(trades)

if __name__ == '__main__':
    df = load('1d')
    print(f"Date Range: {df.index[0]} to {df.index[-1]}")
    print(f"Total Daily Candles: {len(df)}\n")
    
    print(f'{"TP":>4} {"DCA1":>6} {"DCA2":>6} | {"Return":>9} {"WR%":>6} {"DD%":>7} {"Trades":>7}')
    print('-' * 60)
    
    for tp in [0.04, 0.05, 0.06, 0.08]:
        for d1, d2 in [(0.02, 0.04), (0.03, 0.06), (0.04, 0.08)]:
            ret, wr, dd, total = backtest(df, tp, d1, d2)
            print(f'{tp*100:>3.1f}% {d1*100:>5.1f}% {d2*100:>5.1f}% | {ret:>8.2f}% {wr:>5.1f}% {dd:>6.2f}% {total:>7}')
