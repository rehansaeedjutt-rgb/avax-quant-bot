"""
5-YEAR MASTER BACKTEST (2020 - 2026)
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

def load_5y(tf):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}_MERGED_5Y.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df

def backtest_supertrend(df, allow_short=False, tp_pct=0.05, sl_pct=0.03):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    trend, up, dn = supertrend(df['h'].to_numpy(), df['l'].to_numpy(), df['c'].to_numpy(), period=10, multiplier=3.0)
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        close, high, low = row['c'], row['h'], row['l']
        
        if position:
            # LONG logic
            if position['type'] == 'LONG':
                if high >= position['tp']:
                    proceeds = position['units'] * position['tp'] * (1 - SLIPPAGE)
                    fee = proceeds * FEE
                    cash += (proceeds - fee)
                    profit = (proceeds - fee) - (position['units'] * position['entry'])
                    trades.append({'profit_pct': (profit / (position['units'] * position['entry'])) * 100, 'type': 'LONG_TP'})
                    position = None
                elif low <= position['sl']:
                    proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                    fee = proceeds * FEE
                    cash += (proceeds - fee)
                    profit = (proceeds - fee) - (position['units'] * position['entry'])
                    trades.append({'profit_pct': (profit / (position['units'] * position['entry'])) * 100, 'type': 'LONG_SL'})
                    position = None
            
            # SHORT logic
            elif position['type'] == 'SHORT':
                if low <= position['tp']: # TP is below entry for short
                    proceeds = position['units'] * position['tp'] * (1 + SLIPPAGE)
                    fee = proceeds * FEE
                    cash += (position['units'] * position['entry']) - proceeds - fee
                    profit = (position['units'] * position['entry']) - proceeds - fee
                    trades.append({'profit_pct': (profit / (position['units'] * position['entry'])) * 100, 'type': 'SHORT_TP'})
                    position = None
                elif high >= position['sl']: # SL is above entry for short
                    proceeds = position['units'] * position['sl'] * (1 + SLIPPAGE)
                    fee = proceeds * FEE
                    cash += (position['units'] * position['entry']) - proceeds - fee
                    profit = (position['units'] * position['entry']) - proceeds - fee
                    trades.append({'profit_pct': (profit / (position['units'] * position['entry'])) * 100, 'type': 'SHORT_SL'})
                    position = None

        # Entry Logic
        elif cash > 50:
            # Long Entry (Supertrend flips UP)
            if trend[i] == 1 and trend[i-1] == -1:
                dollars = cash * 0.20
                units = dollars / (close * (1 + SLIPPAGE))
                cash -= dollars
                position = {
                    'type': 'LONG', 'entry': close, 'units': units, 
                    'tp': close * (1 + tp_pct), 'sl': close * (1 - sl_pct)
                }
            # Short Entry (Supertrend flips DOWN)
            elif allow_short and trend[i] == -1 and trend[i-1] == 1:
                dollars = cash * 0.20
                units = dollars / close
                # We don't deduct cash for shorting (margin simulation), but we track profit/loss
                position = {
                    'type': 'SHORT', 'entry': close, 'units': units, 
                    'tp': close * (1 - tp_pct), 'sl': close * (1 + sl_pct)
                }

        current_equity = cash + (position['units'] * close if position and position['type']=='LONG' else 0)
        if position and position['type'] == 'SHORT':
             current_equity = cash + (position['units'] * position['entry']) - (position['units'] * close)
             
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

def backtest_dca(df, capital=1000.0, tp_pct=0.03, max_hold=336):
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
    print('5-YEAR MASTER BACKTEST (Sep 2020 - Oct 2026)')
    print('=' * 80)
    
    df_4h = load_5y('4h')
    df_1h = load_5y('1h')

    print('\n--- 1. Supertrend (Long Only) [4H] ---')
    r = backtest_supertrend(df_4h, allow_short=False)
    print(f"Return: {r['ret']:>7.2f}% | Trades: {r['trades']:>4} | WR: {r['wr']:>5.1f}% | DD: {r['dd']:>6.2f}%")

    print('\n--- 2. Supertrend (Long/Short) [4H] ---')
    r = backtest_supertrend(df_4h, allow_short=True)
    print(f"Return: {r['ret']:>7.2f}% | Trades: {r['trades']:>4} | WR: {r['wr']:>5.1f}% | DD: {r['dd']:>6.2f}%")

    print('\n--- 3. DCA Ladder (No Stop Loss) [1H] ---')
    r = backtest_dca(df_1h)
    print(f"Return: {r['ret']:>7.2f}% | Trades: {r['trades']:>4} | WR: {r['wr']:>5.1f}% | DD: {r['dd']:>6.2f}%")
