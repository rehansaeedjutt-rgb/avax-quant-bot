import os
import sys
import warnings
import pandas as pd
from backtesting import Backtest

warnings.filterwarnings('ignore')
ROOT = 'C:/avax_quant_system'
sys.path.insert(0, ROOT)
from strategies.supertrend_strategy import SupertrendStrategy

DATA_DIR = f'{ROOT}/data'
REPORTS_DIR = f'{ROOT}/reports'
os.makedirs(REPORTS_DIR, exist_ok=True)
COMMISSION = 0.0002


def load_data(tf):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}.csv', parse_dates=['timestamp'])
    df = df.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = df[c].astype(float)
    return df


def safe(stats, key, default=0):
    v = stats.get(key, default)
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


def optimize(tf):
    print(f'\n===== Optimizing Supertrend {tf} =====')
    df = load_data(tf)
    print(f'Bars: {len(df)}')

    atr_periods = [7, 10, 14]
    multipliers = [2.0, 2.5, 3.0, 3.5]
    tp_pcts = [0.010, 0.020, 0.030, 0.050]
    sl_pcts = [0.010, 0.020, 0.030]

    results = []
    total = len(atr_periods) * len(multipliers) * len(tp_pcts) * len(sl_pcts)
    i = 0

    for atr_p in atr_periods:
        for mult in multipliers:
            for tp in tp_pcts:
                for sl in sl_pcts:
                    i += 1
                    try:
                        bt = Backtest(df, SupertrendStrategy, cash=10000,
                                      commission=COMMISSION,
                                      exclusive_orders=True,
                                      finalize_trades=True)
                        s = bt.run(atr_period=atr_p, atr_multiplier=mult,
                                   tp_pct=tp, sl_pct=sl,
                                   use_ema_filter=True, ema_len=200)
                        r = {
                            'atr_p': atr_p, 'mult': mult,
                            'tp': tp, 'sl': sl,
                            'ret': safe(s, 'Return [%]'),
                            'wr': safe(s, 'Win Rate [%]'),
                            'pf': safe(s, 'Profit Factor'),
                            'dd': safe(s, 'Max. Drawdown [%]'),
                            'sharpe': safe(s, 'Sharpe Ratio'),
                            'trades': int(s.get('# Trades', 0) or 0),
                        }
                        if i % 20 == 0:
                            print(f'  [{i}/{total}] atr={atr_p} mult={mult} tp={tp} sl={sl} | '
                                  f'ret={r["ret"]:.1f}% wr={r["wr"]:.1f}% pf={r["pf"]:.2f} '
                                  f'trades={r["trades"]}')
                        results.append(r)
                    except Exception as e:
                        print(f'  Error atr={atr_p} mult={mult} tp={tp} sl={sl}: {e}')

    if not results:
        print('No results')
        return

    dfr = pd.DataFrame(results)
    out = f'{REPORTS_DIR}/st_opt_{tf}_all.csv'
    dfr.to_csv(out, index=False)
    print(f'\nSaved all -> {out}')

    # Filter 1: WR > 55, PF > 1.2, Trades > 100, DD > -25
    good = dfr[(dfr['wr'] > 55) & (dfr['pf'] > 1.2) &
               (dfr['trades'] > 100) & (dfr['dd'] > -25)].copy()

    if len(good) > 0:
        print(f'\n===== QUALITY COMBOS (WR>55, PF>1.2, Trades>100, DD>-25%) =====')
        good = good.sort_values('ret', ascending=False)
        print(good.head(15).to_string(index=False))
    else:
        print('\nNo combos pass strict filter. Relaxing to WR > 50...')
        good = dfr[(dfr['wr'] > 50) & (dfr['pf'] > 1.15) &
                   (dfr['trades'] > 80)].copy()
        if len(good) > 0:
            good = good.sort_values('ret', ascending=False)
            print(good.head(15).to_string(index=False))
        else:
            print('Still nothing. Top by Return:')
            print(dfr.sort_values('ret', ascending=False).head(15).to_string(index=False))


if __name__ == '__main__':
    tf = sys.argv[1] if len(sys.argv) > 1 else '1h'
    optimize(tf)
