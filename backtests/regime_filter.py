"""
REGIME FILTER BACKTEST v2 — fixed column join.
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
    # Join ALL columns including close 'c'
    df = df.join(ohlcv[['o', 'h', 'l', 'c', 'v']], how='inner')

    # BTC filter
    btc = pd.read_csv(f'{DATA_DIR}/BTC_USDT_1h.csv')
    btc['timestamp'] = pd.to_datetime(btc['timestamp'])
    btc = btc.set_index('timestamp').sort_index()
    btc['ema50'] = btc['close'].ewm(span=50, adjust=False).mean()
    btc['btc_up'] = (btc['close'] > btc['ema50']).astype(int)
    df = df.join(btc[['btc_up']], how='left')
    df['btc_up'] = df['btc_up'].fillna(0).astype(int)

    # ATR calculation using correct columns
    prev_c = df['c'].shift(1)
    tr = np.maximum(df['h'] - df['l'],
                    np.maximum(abs(df['h'] - prev_c), abs(df['l'] - prev_c)))
    df['atr14'] = tr.rolling(14).mean()
    df['atr_pct'] = df['atr14'] / df['c']
    df['atr_median'] = df['atr_pct'].rolling(200).median()
    df['vol_ok'] = (df['atr_pct'] < df['atr_median'] * 2).astype(int)

    # Trend filter
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['trend_up'] = (df['c'] > df['ema200']).astype(int)

    # Drop NaN rows from warmup
    df = df.dropna(subset=['atr14', 'ema200', 'atr_median']).copy()
    return df


def backtest(df, buy_th, tp_pct, sl_pct, pos_size=0.20,
             use_btc_filter=True, use_vol_filter=True, use_trend_filter=True,
             max_hold=100):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close = row['c']
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

        elif score >= buy_th and cash > 10:
            filters_ok = True
            if use_btc_filter and row['btc_up'] != 1:
                filters_ok = False
            if use_vol_filter and row['vol_ok'] != 1:
                filters_ok = False
            if use_trend_filter and row['trend_up'] != 1:
                filters_ok = False

            if filters_ok:
                entry_fill = close * (1 + SLIPPAGE)
                dollars = cash * pos_size
                units = dollars / entry_fill
                cash -= dollars
                position = {'entry': close, 'entry_fill': entry_fill,
                            'units': units, 'bar': i}

        eq = cash + (position['units'] * close if position else 0)
        equity.append(eq)

    if position:
        proceeds = position['units'] * df['c'].iloc[-1]
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
    sl_hits = sum(1 for t in trades if t['type'] == 'SL')
    sl_rate = (sl_hits / total * 100) if total else 0

    return {'return_pct': ret_pct, 'final': final, 'trades': total,
            'wr': wr, 'pf': pf, 'max_dd': max_dd, 'sl_rate': sl_rate}


def main():
    print('=' * 100)
    print('REGIME FILTER BACKTEST v2')
    print('=' * 100)
    df = load()
    print(f'Candles after warmup: {len(df):,}')
    print(f'Range: {df.index[0]} -> {df.index[-1]}\n')

    mid = len(df) // 2
    df1 = df.iloc[:mid]
    df2 = df.iloc[mid:]

    configs = [
        ('No filters', False, False, False),
        ('BTC only', True, False, False),
        ('Vol only', False, True, False),
        ('Trend only', False, False, True),
        ('BTC+Vol', True, True, False),
        ('BTC+Trend', True, False, True),
        ('Vol+Trend', False, True, True),
        ('ALL 3', True, True, True),
    ]

    buy_th, tp, sl = 0.25, 0.03, 0.03

    print(f'Using: Buy>={buy_th}, TP={tp*100}%, SL={sl*100}%, PosSize=20%\n')

    header = (f'{"Filter":>12} | {"Full Ret%":>10} {"WR%":>6} {"PF":>5} {"DD%":>7} '
              f'{"SL%":>6} {"Trades":>7} | {"Train Ret%":>10} | {"TEST Ret%":>10} '
              f'{"WR%":>6} {"SL%":>6}')
    print(header)
    print('-' * 130)

    best = None
    for name, b, v, t in configs:
        r = backtest(df, buy_th, tp, sl, use_btc_filter=b, use_vol_filter=v, use_trend_filter=t)
        r1 = backtest(df1, buy_th, tp, sl, use_btc_filter=b, use_vol_filter=v, use_trend_filter=t)
        r2 = backtest(df2, buy_th, tp, sl, use_btc_filter=b, use_vol_filter=v, use_trend_filter=t)

        print(f'{name:>12} | '
              f'{r["return_pct"]:>10.2f} {r["wr"]:>6.1f} {r["pf"]:>5.2f} '
              f'{r["max_dd"]:>7.2f} {r["sl_rate"]:>6.1f} {r["trades"]:>7} | '
              f'{r1["return_pct"]:>10.2f} | '
              f'{r2["return_pct"]:>10.2f} {r2["wr"]:>6.1f} {r2["sl_rate"]:>6.1f}')

        score = r2['return_pct'] * (1 - r2['sl_rate']/100) * (1 + r2['wr']/100)
        if best is None or score > best[1]:
            best = ((name, r, r1, r2), score)

    print('\n' + '=' * 100)
    print('BEST CONFIG')
    print('=' * 100)
    name, r, r1, r2 = best[0]
    print(f'Filter: {name}\n')
    print(f'FULL  : Ret {r["return_pct"]:>7.2f}% | WR {r["wr"]:>5.1f}% | '
          f'PF {r["pf"]:>5.2f} | DD {r["max_dd"]:>6.2f}% | SL {r["sl_rate"]:>5.1f}% | '
          f'Trades {r["trades"]:>4}')
    print(f'TRAIN : Ret {r1["return_pct"]:>7.2f}% | WR {r1["wr"]:>5.1f}% | '
          f'PF {r1["pf"]:>5.2f} | SL {r1["sl_rate"]:>5.1f}%')
    print(f'TEST  : Ret {r2["return_pct"]:>7.2f}% | WR {r2["wr"]:>5.1f}% | '
          f'PF {r2["pf"]:>5.2f} | DD {r2["max_dd"]:>6.2f}% | SL {r2["sl_rate"]:>5.1f}%')


if __name__ == '__main__':
    main()
