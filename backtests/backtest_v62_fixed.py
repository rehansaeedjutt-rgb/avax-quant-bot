"""
CORRECTED BACKTEST v6.2 (Cash Bug Fixed)
- Exact match of live bot logic
- TP1: 1.5% (50%), Breakeven SL
- TP2: 3.0%
- SL: 2.0%
- DCA: 1% and 1.5% (Adds 25% each)
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load():
    df = pd.read_csv(f'{DATA_DIR}/avax_master_score.csv')
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    ohlcv = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED.csv')
    ohlcv['open_time'] = pd.to_datetime(ohlcv['open_time'], unit='ms')
    ohlcv = ohlcv.set_index('open_time').sort_index()
    ohlcv = ohlcv.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df.join(ohlcv[['o', 'h', 'l', 'c']], how='inner')

def backtest(df, buy_th=0.15, max_hold=100):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        score = row['master']

        if position:
            hours = i - position['bar']
            is_tp1_hit = position['tp1_hit']
            
            # 1. Update DCA (Only if TP1 not hit yet)
            if not is_tp1_hit:
                if not position['dca1_hit'] and low <= position['entry'] * 0.99:
                    position['dca1_hit'] = True
                    add_cost = position['initial_cost'] * 0.25
                    add_units = add_cost / close
                    cash -= add_cost
                    position['units'] += add_units
                    position['cost'] += add_cost
                    position['avg'] = position['cost'] / position['units']
                    position['tp1'] = position['avg'] * 1.015
                    position['tp2'] = position['avg'] * 1.030
                    position['sl'] = position['avg'] * 0.980
                elif position['dca1_hit'] and not position['dca2_hit'] and low <= position['entry'] * 0.985:
                    position['dca2_hit'] = True
                    add_cost = position['initial_cost'] * 0.25
                    add_units = add_cost / close
                    cash -= add_cost
                    position['units'] += add_units
                    position['cost'] += add_cost
                    position['avg'] = position['cost'] / position['units']
                    position['tp1'] = position['avg'] * 1.015
                    position['tp2'] = position['avg'] * 1.030
                    position['sl'] = position['avg'] * 0.980

            # 2. Check TP1
            if not is_tp1_hit and high >= position['tp1']:
                position['tp1_hit'] = True
                position['sl'] = position['avg'] # Move SL to breakeven
                sell_units = position['units'] * 0.5
                proceeds = sell_units * position['tp1'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                cost_sold = position['cost'] * 0.5
                position['realized_profit'] += (proceeds - fee) - cost_sold
                position['units'] -= sell_units
                position['cost'] -= cost_sold

            # 3. Check TP2 (Remaining 50%)
            elif position['tp1_hit'] and high >= position['tp2']:
                proceeds = position['units'] * position['tp2'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                position['realized_profit'] += (proceeds - fee) - position['cost']
                total_profit = position['realized_profit']
                
                trades.append({'profit_pct': (total_profit / position['initial_cost']) * 100, 'type': 'TP2', 'held': hours})
                position = None

            # 4. Check SL (Initial or Breakeven)
            elif low <= position['sl']:
                proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                position['realized_profit'] += (proceeds - fee) - position['cost']
                total_profit = position['realized_profit']
                
                trades.append({'profit_pct': (total_profit / position['initial_cost']) * 100, 'type': 'BE' if is_tp1_hit else 'SL', 'held': hours})
                position = None
                
            # 5. Time Exit
            elif hours >= max_hold:
                proceeds = position['units'] * close * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                position['realized_profit'] += (proceeds - fee) - position['cost']
                total_profit = position['realized_profit']
                
                trades.append({'profit_pct': (total_profit / position['initial_cost']) * 100, 'type': 'TIME', 'held': hours})
                position = None

        # Entry Signal
        elif score >= buy_th and cash > 50:
            dollars = cash * 0.20
            units = dollars / (close * (1 + SLIPPAGE))
            cash -= dollars
            position = {
                'entry': close, 'avg': close, 'units': units, 'initial_cost': dollars, 'cost': dollars,
                'tp1': close * 1.015, 'tp2': close * 1.030, 'sl': close * 0.980,
                'tp1_hit': False, 'dca1_hit': False, 'dca2_hit': False,
                'bar': i, 'realized_profit': 0
            }

        current_equity = cash + (position['units'] * close if position else 0)
        equity.append(current_equity)

    if position:
        cash += position['units'] * df['c'].iloc[-1]

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gw / gl) if gl > 0 else (99.9 if gw > 0 else 0)

    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'pf': pf, 'dd': dd}

if __name__ == '__main__':
    print('=' * 80)
    print('CORRECTED BACKTEST v6.2 (Cash Fixed)')
    print('=' * 80)
    df = load()
    r = backtest(df)
    
    print(f"\nTotal Return   : {r['ret']:>8.2f}%")
    print(f"Total Trades   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Profit Factor  : {r['pf']:>8.2f}")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")

