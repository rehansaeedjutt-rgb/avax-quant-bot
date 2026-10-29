"""
DOOMSDAY PROTECTION BACKTEST (Macro Stop Loss)
Tests DCA with a hard -15% circuit breaker to prevent account wipeout.
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_data(symbol):
    if symbol == 'AVAX':
        df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1d_MERGED_5Y.csv')
    else:
        df = pd.read_csv(f'{DATA_DIR}/LINK_USDT_1d_EXACT.csv')
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

def backtest(df, tp_pct, dca1_drop, dca2_drop, macro_sl_pct=None):
    capital = 1000.0
    cash = capital
    cycle = None
    trades = []
    equity = []
    max_drawdown = 0

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        
        if cycle:
            # 1. Check Macro Stop Loss (Circuit Breaker)
            if macro_sl_pct and low <= cycle['start_price'] * (1 - macro_sl_pct):
                revenue = cycle['units'] * (cycle['start_price'] * (1 - macro_sl_pct))
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = (revenue - fee) - cycle['cost']
                trades.append(profit)
                cycle = None
                continue # Skip to next candle

            # 2. Check Take Profit
            elif high >= cycle['tp']:
                revenue = cycle['units'] * cycle['tp']
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = (revenue - fee) - cycle['cost']
                trades.append(profit)
                cycle = None
                continue

            # 3. Check DCA
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

        # New Entry
        elif cash > capital * 0.5 and row['macd_bull'] and row['above_ema']:
            cost = capital * 0.50
            units = cost / close
            cash -= cost
            cycle = {
                'start_price': close, 'units': units, 'cost': cost,
                'initial_cost': cost, 'avg': close,
                'tp': close * (1 + tp_pct), 'level': 1
            }

        current_equity = cash + (cycle['units'] * close if cycle else 0)
        equity.append(current_equity)
        
        # Track drawdown
        peak = max(equity)
        dd = (current_equity - peak) / peak * 100
        if dd < max_drawdown:
            max_drawdown = dd

    final = equity[-1]
    ret_pct = (final - capital) / capital * 100
    wins = sum(1 for p in trades if p > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    return ret_pct, wr, max_drawdown, total

if __name__ == '__main__':
    print("Testing Doomsday Protection Scenarios...")
    
    for symbol in ['AVAX', 'LINK']:
        print(f"\n{'='*60}")
        print(f"SYMBOL: {symbol}")
        print(f"{'='*60}")
        print(f"{'Scenario':<35} | {'Return':>9} | {'Max DD':>8} | {'Win Rate':>8} | {'Trades':>6}")
        print('-' * 75)
        
        df = load_data(symbol)
        tp = 0.04 if symbol == 'AVAX' else 0.06
        d1 = 0.02 if symbol == 'AVAX' else 0.03
        d2 = 0.04 if symbol == 'AVAX' else 0.06

        # 1. No Macro SL (Current Live Strategy)
        ret, wr, dd, total = backtest(df, tp, d1, d2, macro_sl_pct=None)
        print(f"{'1. No Circuit Breaker (Current)':<35} | {ret:>8.1f}% | {dd:>7.1f}% | {wr:>7.1f}% | {total:>6}")

        # 2. Macro SL at -15% (Saved 85% of account)
        ret, wr, dd, total = backtest(df, tp, d1, d2, macro_sl_pct=0.15)
        print(f"{'2. Circuit Breaker at -15%':<35} | {ret:>8.1f}% | {dd:>7.1f}% | {wr:>7.1f}% | {total:>6}")

        # 3. Macro SL at -20%
        ret, wr, dd, total = backtest(df, tp, d1, d2, macro_sl_pct=0.20)
        print(f"{'3. Circuit Breaker at -20%':<35} | {ret:>8.1f}% | {dd:>7.1f}% | {wr:>7.1f}% | {total:>6}")

        # 4. Macro SL at -25%
        ret, wr, dd, total = backtest(df, tp, d1, d2, macro_sl_pct=0.25)
        print(f"{'4. Circuit Breaker at -25%':<35} | {ret:>8.1f}% | {dd:>7.1f}% | {wr:>7.1f}% | {total:>6}")
