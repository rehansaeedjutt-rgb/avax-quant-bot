"""
BACKTEST — Master Signal Strategy
Tests multiple entry/exit thresholds on 17,520 candles.
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
REPORTS = os.path.join(ROOT, 'reports')
os.makedirs(REPORTS, exist_ok=True)

COMMISSION = 0.0002


def load():
    df = pd.read_csv(f'{DATA_DIR}/avax_master_score.csv')
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    # Load OHLCV to get highs/lows
    ohlcv = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED.csv')
    ohlcv['open_time'] = pd.to_datetime(ohlcv['open_time'], unit='ms')
    ohlcv = ohlcv.set_index('open_time').sort_index()
    ohlcv = ohlcv.rename(columns={'open': 'o', 'high': 'h', 'low': 'l',
                                   'close': 'c', 'volume': 'v'})
    merged = df.join(ohlcv[['o', 'h', 'l']], how='inner')
    return merged


def backtest(df, buy_th, sell_th, tp_pct, sl_pct, max_hold=100):
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

        # Manage open position
        if position:
            entry = position['entry']
            tp_price = entry * (1 + tp_pct)
            sl_price = entry * (1 - sl_pct)
            bars_held = i - position['bar']

            # Check TP
            if high >= tp_price:
                proceeds = position['units'] * tp_price
                profit = proceeds - position['units'] * entry - (proceeds * COMMISSION * 2)
                cash += proceeds
                trades.append({'profit': profit, 'held': bars_held, 'type': 'TP'})
                position = None
            # Check SL
            elif low <= sl_price:
                proceeds = position['units'] * sl_price
                profit = proceeds - position['units'] * entry - (proceeds * COMMISSION * 2)
                cash += proceeds
                trades.append({'profit': profit, 'held': bars_held, 'type': 'SL'})
                position = None
            # Time exit
            elif bars_held >= max_hold:
                proceeds = position['units'] * close
                profit = proceeds - position['units'] * entry - (proceeds * COMMISSION * 2)
                cash += proceeds
                trades.append({'profit': profit, 'held': bars_held, 'type': 'TIME'})
                position = None

        # Entry signal
        elif score >= buy_th and cash > 10:
            units = (cash * 0.95) / close  # Use 95% of cash
            position = {
                'entry': close,
                'units': units,
                'bar': i,
                'entry_time': ts,
            }
            cash -= units * close  # Deduct entry cost

        eq = cash + (position['units'] * close if position else 0)
        equity.append(eq)

    # Close any open position at end
    if position:
        proceeds = position['units'] * df['close'].iloc[-1]
        profit = proceeds - position['units'] * position['entry']
        cash += proceeds
        trades.append({'profit': profit, 'held': len(df) - position['bar'], 'type': 'END'})

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = (eq_arr - peak) / peak
    max_dd = dd.min() * 100

    final = eq_arr[-1] if len(eq_arr) > 0 else capital
    return_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit'] > 0)
    losses = sum(1 for t in trades if t['profit'] < 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gross_win = sum(t['profit'] for t in trades if t['profit'] > 0)
    gross_loss = abs(sum(t['profit'] for t in trades if t['profit'] < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    avg_held = np.mean([t['held'] for t in trades]) if trades else 0

    return {
        'return_pct': return_pct,
        'final': final,
        'trades': total,
        'wins': wins,
        'losses': losses,
        'wr': wr,
        'pf': pf,
        'max_dd': max_dd,
        'avg_held': avg_held,
    }


def main():
    print('=' * 90)
    print('MASTER SIGNAL BACKTEST — 17,520 candles (1h)')
    print('=' * 90)
    df = load()
    print(f'Loaded {len(df):,} candles\n')

    # Grid of parameters
    buy_thresholds = [0.15, 0.20, 0.25, 0.30]
    tp_pcts = [0.02, 0.03, 0.05]
    sl_pcts = [0.02, 0.03]

    results = []
    print(f'{"BuyTh":>6} {"TP%":>5} {"SL%":>5} | {"Ret%":>8} {"Trades":>7} '
          f'{"WR%":>6} {"PF":>5} {"DD%":>7} {"Held":>6}')
    print('-' * 90)

    for buy_th in buy_thresholds:
        for tp in tp_pcts:
            for sl in sl_pcts:
                r = backtest(df, buy_th, -0.3, tp, sl)
                print(f'{buy_th:>6.2f} {tp*100:>5.1f} {sl*100:>5.1f} | '
                      f'{r["return_pct"]:>8.2f} {r["trades"]:>7} '
                      f'{r["wr"]:>6.1f} {r["pf"]:>5.2f} {r["max_dd"]:>7.2f} '
                      f'{r["avg_held"]:>6.1f}')
                results.append({
                    'buy_th': buy_th, 'tp': tp, 'sl': sl, **r
                })

    # Find best
    df_res = pd.DataFrame(results)
    best = df_res.sort_values('return_pct', ascending=False).iloc[0]

    print('\n' + '=' * 90)
    print('BEST PARAMETERS')
    print('=' * 90)
    print(f'Buy threshold: {best["buy_th"]:.2f}')
    print(f'TP: {best["tp"]*100:.1f}%')
    print(f'SL: {best["sl"]*100:.1f}%')
    print(f'Return: {best["return_pct"]:.2f}%')
    print(f'Trades: {int(best["trades"])}')
    print(f'Win Rate: {best["wr"]:.1f}%')
    print(f'Profit Factor: {best["pf"]:.2f}')
    print(f'Max DD: {best["max_dd"]:.2f}%')
    print(f'Avg Hold: {best["avg_held"]:.1f} hours')

    df_res.to_csv(f'{REPORTS}/master_backtest.csv', index=False)
    print(f'\nSaved: {REPORTS}/master_backtest.csv')


if __name__ == '__main__':
    main()
