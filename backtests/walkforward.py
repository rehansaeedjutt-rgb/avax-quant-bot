"""
WALK-FORWARD VALIDATION
Split data: train on first year, test on second year.
If results hold on unseen data → real edge.
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
    return df.join(ohlcv[['o', 'h', 'l']], how='inner')


def backtest(df, buy_th, tp_pct, sl_pct, pos_size=0.20, max_hold=100):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close = row['close']
        high = row['h']
        low = row['l']
        score = row['master']

        if position:
            entry = position['entry']
            tp_price = entry * (1 + tp_pct)
            sl_price = entry * (1 - sl_pct)
            bars_held = i - position['bar']

            exit_price = None
            reason = None
            if high >= tp_price:
                exit_price = tp_price; reason = 'TP'
            elif low <= sl_price:
                exit_price = sl_price; reason = 'SL'
            elif bars_held >= max_hold:
                exit_price = close; reason = 'TIME'

            if exit_price is not None:
                exit_fill = exit_price * (1 - SLIPPAGE)
                proceeds = position['units'] * exit_fill
                cost_basis = position['units'] * position['entry_fill']
                fee_cost = (position['units'] * position['entry_fill'] + proceeds) * FEE
                profit = proceeds - cost_basis - fee_cost
                cash += proceeds
                trades.append({'profit': profit, 'held': bars_held, 'type': reason})
                position = None

        elif score >= buy_th:
            entry_fill = close * (1 + SLIPPAGE)
            dollars = cash * pos_size
            if dollars >= 10:
                units = dollars / entry_fill
                cash -= dollars
                position = {'entry': close, 'entry_fill': entry_fill,
                            'units': units, 'bar': i}

        eq = cash + (position['units'] * close if position else 0)
        equity.append(eq)

    if position:
        proceeds = position['units'] * df['close'].iloc[-1]
        cash += proceeds
        profit = proceeds - position['units'] * position['entry_fill']
        trades.append({'profit': profit, 'held': len(df) - position['bar'], 'type': 'END'})

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = (eq_arr - peak) / peak
    max_dd = dd.min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit'] > 0)
    losses = sum(1 for t in trades if t['profit'] < 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit'] for t in trades if t['profit'] > 0)
    gl = abs(sum(t['profit'] for t in trades if t['profit'] < 0))
    pf = (gw / gl) if gl > 0 else float('inf')

    return {'return_pct': ret_pct, 'final': final, 'trades': total,
            'wr': wr, 'pf': pf, 'max_dd': max_dd}


def main():
    print('=' * 80)
    print('WALK-FORWARD VALIDATION')
    print('=' * 80)
    df = load()
    print(f'Total candles: {len(df):,}')
    print(f'Full period: {df.index[0]} -> {df.index[-1]}\n')

    # Split in half
    mid = len(df) // 2
    df1 = df.iloc[:mid]
    df2 = df.iloc[mid:]

    print(f'Period 1 (train): {df1.index[0]} -> {df1.index[-1]} ({len(df1):,} candles)')
    print(f'Period 2 (test) : {df2.index[0]} -> {df2.index[-1]} ({len(df2):,} candles)')
    print()

    # Best params
    buy_th = 0.25
    tp = 0.03
    sl = 0.03

    print('=' * 80)
    print(f'BEST PARAMS: Buy>={buy_th}, TP={tp*100}%, SL={sl*100}%')
    print('=' * 80)

    print('\n--- Full period ---')
    r = backtest(df, buy_th, tp, sl)
    print(f'  Ret: {r["return_pct"]:>7.2f}% | Trades: {r["trades"]:>4} | '
          f'WR: {r["wr"]:>5.1f}% | PF: {r["pf"]:>5.2f} | DD: {r["max_dd"]:>6.2f}%')

    print('\n--- Period 1 (in-sample) ---')
    r1 = backtest(df1, buy_th, tp, sl)
    print(f'  Ret: {r1["return_pct"]:>7.2f}% | Trades: {r1["trades"]:>4} | '
          f'WR: {r1["wr"]:>5.1f}% | PF: {r1["pf"]:>5.2f} | DD: {r1["max_dd"]:>6.2f}%')

    print('\n--- Period 2 (OUT-OF-SAMPLE) ---')
    r2 = backtest(df2, buy_th, tp, sl)
    print(f'  Ret: {r2["return_pct"]:>7.2f}% | Trades: {r2["trades"]:>4} | '
          f'WR: {r2["wr"]:>5.1f}% | PF: {r2["pf"]:>5.2f} | DD: {r2["max_dd"]:>6.2f}%')

    print('\n' + '=' * 80)
    print('VERDICT')
    print('=' * 80)
    if r2['return_pct'] > 15 and r2['wr'] > 60 and r2['pf'] > 1.3:
        print('✓ PASSED — Strategy has genuine edge on unseen data.')
        print('  Ready for live deployment.')
    elif r2['return_pct'] > 0 and r2['pf'] > 1.0:
        print('⚠ MARGINAL — Positive but weaker on unseen data.')
        print('  Needs further optimization before live.')
    else:
        print('✗ FAILED — Strategy does not generalize.')
        print('  Overfitting detected. Do not deploy.')

    print(f'\nComparison:')
    print(f'  Period 1 return: {r1["return_pct"]:.2f}%')
    print(f'  Period 2 return: {r2["return_pct"]:.2f}%')
    print(f'  Ratio: {r2["return_pct"]/max(abs(r1["return_pct"]),0.01):.2f}x')


if __name__ == '__main__':
    main()
