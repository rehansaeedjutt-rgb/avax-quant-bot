"""
REALISTIC BACKTEST v2
- Position sizing: 20% per trade (not 95%)
- Slippage: 0.15% per side
- Fees: 0.05% per side
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
REPORTS = os.path.join(ROOT, 'reports')

SLIPPAGE = 0.0015   # 0.15% per side
FEE = 0.0005        # 0.05% per side


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
                exit_price = tp_price
                reason = 'TP'
            elif low <= sl_price:
                exit_price = sl_price
                reason = 'SL'
            elif bars_held >= max_hold:
                exit_price = close
                reason = 'TIME'

            if exit_price is not None:
                # Apply slippage on exit
                exit_fill = exit_price * (1 - SLIPPAGE)
                proceeds = position['units'] * exit_fill
                cost_basis = position['units'] * position['entry_fill']
                fee_cost = (position['units'] * position['entry_fill'] + proceeds) * FEE
                profit = proceeds - cost_basis - fee_cost
                cash += proceeds
                trades.append({'profit': profit, 'held': bars_held, 'type': reason})
                position = None

        elif score >= buy_th:
            # Entry with slippage
            entry_fill = close * (1 + SLIPPAGE)
            dollars = cash * pos_size
            if dollars >= 10:
                units = dollars / entry_fill
                cash -= dollars
                position = {
                    'entry': close,
                    'entry_fill': entry_fill,
                    'units': units,
                    'bar': i,
                }

        eq = cash + (position['units'] * close if position else 0)
        equity.append(eq)

    # Close at end
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
    avg_held = np.mean([t['held'] for t in trades]) if trades else 0

    return {
        'return_pct': ret_pct, 'final': final, 'trades': total,
        'wins': wins, 'losses': losses, 'wr': wr, 'pf': pf,
        'max_dd': max_dd, 'avg_held': avg_held,
    }


def main():
    print('=' * 90)
    print('REALISTIC BACKTEST (20% position, 0.15% slippage, 0.05% fees)')
    print('=' * 90)
    df = load()
    print(f'Candles: {len(df):,}\n')

    configs = [
        (0.20, 0.02, 0.02),
        (0.25, 0.02, 0.02),
        (0.25, 0.03, 0.03),
        (0.25, 0.03, 0.02),
        (0.25, 0.05, 0.03),
        (0.30, 0.02, 0.02),
        (0.30, 0.03, 0.03),
        (0.30, 0.05, 0.03),
    ]

    print(f'{"BuyTh":>6} {"TP%":>5} {"SL%":>5} | {"Ret%":>8} {"Trades":>7} '
          f'{"WR%":>6} {"PF":>5} {"DD%":>7} {"Held":>6}')
    print('-' * 90)

    results = []
    for buy_th, tp, sl in configs:
        r = backtest(df, buy_th, tp, sl)
        print(f'{buy_th:>6.2f} {tp*100:>5.1f} {sl*100:>5.1f} | '
              f'{r["return_pct"]:>8.2f} {r["trades"]:>7} '
              f'{r["wr"]:>6.1f} {r["pf"]:>5.2f} {r["max_dd"]:>7.2f} '
              f'{r["avg_held"]:>6.1f}')
        results.append({'buy_th': buy_th, 'tp': tp, 'sl': sl, **r})

    df_res = pd.DataFrame(results)
    best = df_res.sort_values('return_pct', ascending=False).iloc[0]

    print('\n' + '=' * 90)
    print('BEST REALISTIC PARAMETERS')
    print('=' * 90)
    print(f'Buy threshold: {best["buy_th"]:.2f}')
    print(f'TP: {best["tp"]*100:.1f}% | SL: {best["sl"]*100:.1f}%')
    print(f'Return: {best["return_pct"]:.2f}%')
    print(f'Final capital: ${best["final"]:.2f}')
    print(f'Trades: {int(best["trades"])} | WR: {best["wr"]:.1f}% | PF: {best["pf"]:.2f}')
    print(f'Max DD: {best["max_dd"]:.2f}% | Avg Hold: {best["avg_held"]:.1f}h')

    df_res.to_csv(f'{REPORTS}/realistic_backtest.csv', index=False)
    print(f'\nSaved: {REPORTS}/realistic_backtest.csv')


if __name__ == '__main__':
    main()
