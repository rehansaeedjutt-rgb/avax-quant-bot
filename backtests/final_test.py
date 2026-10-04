"""
FINAL TEST — Option B: High WR shape
Buy >= 0.30, TP 2%, SL 3%
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
REPORTS = os.path.join(ROOT, 'reports')
SLIPPAGE = 0.0015
FEE = 0.0005


def load():
    df = pd.read_csv(f'{DATA_DIR}/avax_master_score.csv')
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    ohlcv = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED.csv')
    ohlcv['open_time'] = pd.to_datetime(ohlcv['open_time'], unit='ms')
    ohlcv = ohlcv.set_index('open_time').sort_index()
    ohlcv = ohlcv.rename(columns={'open': 'o', 'high': 'h', 'low': 'l',
                                   'close': 'c', 'volume': 'v'})
    return df.join(ohlcv[['o', 'h', 'l', 'c']], how='inner')


def backtest(df, buy_th, tp_pct, sl_pct, pos_size=0.20, max_hold=100):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        score = row['master']

        if position:
            entry = position['entry']
            tp_price = entry * (1 + tp_pct)
            sl_price = entry * (1 - sl_pct)
            bars_held = i - position['bar']
            exit_price, reason = None, None

            if high >= tp_price:
                exit_price, reason = tp_price, 'TP'
            elif low <= sl_price:
                exit_price, reason = sl_price, 'SL'
            elif bars_held >= max_hold:
                exit_price, reason = close, 'TIME'

            if exit_price is not None:
                exit_fill = exit_price * (1 - SLIPPAGE)
                proceeds = position['units'] * exit_fill
                cost_basis = position['units'] * position['entry_fill']
                fee_cost = (position['units'] * position['entry_fill'] + proceeds) * FEE
                profit = proceeds - cost_basis - fee_cost
                cash += proceeds
                trades.append({'profit': profit, 'held': bars_held, 'type': reason})
                position = None

        elif score >= buy_th and cash > 10:
            entry_fill = close * (1 + SLIPPAGE)
            dollars = cash * pos_size
            units = dollars / entry_fill
            cash -= dollars
            position = {'entry': close, 'entry_fill': entry_fill, 'units': units, 'bar': i}

        eq = cash + (position['units'] * close if position else 0)
        equity.append(eq)

    if position:
        proceeds = position['units'] * df['c'].iloc[-1]
        cash += proceeds
        profit = proceeds - position['units'] * position['entry_fill']
        trades.append({'profit': profit, 'held': len(df) - position['bar'], 'type': 'END'})

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit'] for t in trades if t['profit'] > 0)
    gl = abs(sum(t['profit'] for t in trades if t['profit'] < 0))
    pf = (gw / gl) if gl > 0 else float('inf')
    sl_hits = sum(1 for t in trades if t['type'] == 'SL')
    sl_rate = (sl_hits / total * 100) if total else 0

    return {'return_pct': ret_pct, 'final': final, 'trades': total,
            'wr': wr, 'pf': pf, 'max_dd': dd, 'sl_rate': sl_rate}


def main():
    print('=' * 90)
    print('OPTION B FINAL TEST — High WR Shape')
    print('=' * 90)
    df = load()

    mid = len(df) // 2
    df1, df2 = df.iloc[:mid], df.iloc[mid:]

    configs = [
        ('A: 0.25/3%/3%', 0.25, 0.03, 0.03),
        ('B1: 0.30/2%/3%', 0.30, 0.02, 0.03),
        ('B2: 0.30/2%/4%', 0.30, 0.02, 0.04),
        ('B3: 0.28/2%/3%', 0.28, 0.02, 0.03),
        ('B4: 0.30/1.5%/3%', 0.30, 0.015, 0.03),
        ('C: 0.32/2%/3%', 0.32, 0.02, 0.03),
    ]

    print(f'\n{"Config":>16} | {"FULL Ret%":>9} {"WR%":>6} {"PF":>5} '
          f'{"DD%":>7} {"SL%":>6} {"Trd":>5} | {"TEST Ret%":>9} {"WR%":>6} {"SL%":>6}')
    print('-' * 90)

    best = None
    for name, bt, tp, sl in configs:
        r = backtest(df, bt, tp, sl)
        r2 = backtest(df2, bt, tp, sl)
        print(f'{name:>16} | {r["return_pct"]:>9.2f} {r["wr"]:>6.1f} '
              f'{r["pf"]:>5.2f} {r["max_dd"]:>7.2f} {r["sl_rate"]:>6.1f} {r["trades"]:>5} | '
              f'{r2["return_pct"]:>9.2f} {r2["wr"]:>6.1f} {r2["sl_rate"]:>6.1f}')

        # Score: prefer high WR, low SL, positive OOS
        if r2['return_pct'] > 5 and r2['wr'] > 70:
            score = r2['return_pct'] * (r2['wr']/100) * (1 - r2['sl_rate']/100)
            if best is None or score > best[1]:
                best = ((name, bt, tp, sl, r, r2), score)

    if best:
        name, bt, tp, sl, r, r2 = best[0]
        print('\n' + '=' * 90)
        print(f'BEST HIGH-WR CONFIG: {name}')
        print('=' * 90)
        print(f'Buy >= {bt}, TP {tp*100}%, SL {sl*100}%')
        print(f'\nFULL: Ret {r["return_pct"]:.2f}% | WR {r["wr"]:.1f}% | '
              f'PF {r["pf"]:.2f} | DD {r["max_dd"]:.2f}% | SL {r["sl_rate"]:.1f}%')
        print(f'TEST: Ret {r2["return_pct"]:.2f}% | WR {r2["wr"]:.1f}% | '
              f'PF {r2["pf"]:.2f} | SL {r2["sl_rate"]:.1f}% | Trades {r2["trades"]}')
    else:
        print('\nNo config met criteria (OOS>5%, WR>70%)')


if __name__ == '__main__':
    main()
