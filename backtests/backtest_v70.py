"""
BACKTEST v7.0 — No DCA + EMA200 Trend Filter + Better R:R
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
    
    # ADD EMA200 TREND FILTER
    ohlcv['ema200'] = ohlcv['c'].ewm(span=200, adjust=False).mean()
    ohlcv['trend_up'] = ohlcv['c'] > ohlcv['ema200']
    
    return df.join(ohlcv[['o', 'h', 'l', 'c', 'trend_up']], how='inner')

def backtest(df, buy_th=0.15, max_hold=100):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        score = row['master']
        trend_up = row['trend_up']

        if position:
            hours = i - position['bar']
            
            # Check TP1
            if not position['tp1_hit'] and high >= position['tp1']:
                position['tp1_hit'] = True
                position['sl'] = position['entry'] # Move SL to breakeven
                sell_units = position['units'] * 0.5
                proceeds = sell_units * position['tp1'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                cost_sold = position['cost'] * 0.5
                position['realized_profit'] += (proceeds - fee) - cost_sold
                position['units'] -= sell_units
                position['cost'] -= cost_sold

            # Check TP2 (Remaining 50%)
            elif position['tp1_hit'] and high >= position['tp2']:
                proceeds = position['units'] * position['tp2'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                position['realized_profit'] += (proceeds - fee) - position['cost']
                total_profit = position['realized_profit']
                
                trades.append({'profit_pct': (total_profit / position['initial_cost']) * 100, 'type': 'TP2', 'held': hours})
                position = None

            # Check SL (Initial or Breakeven)
            elif low <= position['sl']:
                proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                position['realized_profit'] += (proceeds - fee) - position['cost']
                total_profit = position['realized_profit']
                
                trades.append({'profit_pct': (total_profit / position['initial_cost']) * 100, 'type': 'BE' if position['tp1_hit'] else 'SL', 'held': hours})
                position = None
                
            # Time Exit
            elif hours >= max_hold:
                proceeds = position['units'] * close * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                position['realized_profit'] += (proceeds - fee) - position['cost']
                total_profit = position['realized_profit']
                
                trades.append({'profit_pct': (total_profit / position['initial_cost']) * 100, 'type': 'TIME', 'held': hours})
                position = None

        # Entry Signal (NOW REQUIRES TREND UP)
        elif score >= buy_th and cash > 50 and trend_up:
            dollars = cash * 0.20
            units = dollars / (close * (1 + SLIPPAGE))
            cash -= dollars
            position = {
                'entry': close, 'units': units, 'initial_cost': dollars, 'cost': dollars,
                'tp1': close * 1.02,   # TP1 at +2.0%
                'tp2': close * 1.04,   # TP2 at +4.0%
                'sl': close * 0.98,    # SL at -2.0%
                'tp1_hit': False, 'bar': i, 'realized_profit': 0
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
    print('BACKTEST v7.0 (No DCA, Trend Filter, 2% TP1, 4% TP2)')
    print('=' * 80)
    df = load()
    r = backtest(df)
    
    print(f"\nTotal Return   : {r['ret']:>8.2f}%")
    print(f"Total Trades   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Profit Factor  : {r['pf']:>8.2f}")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")

