import os, sys, warnings
import pandas as pd
from backtesting import Backtest

warnings.filterwarnings('ignore')
ROOT = 'C:/avax_quant_system'
sys.path.insert(0, ROOT)
from strategies.sr_long_strategy import SRLongStrategy

DATA_DIR = f'{ROOT}/data'
REPORTS_DIR = f'{ROOT}/reports'
os.makedirs(REPORTS_DIR, exist_ok=True)
COMMISSION = 0.0002
MIN_TRADES = 30


def load_data(tf):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}.csv', parse_dates=['timestamp'])
    df = df.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = df[c].astype(float)
    try:
        btc = pd.read_csv(f'{DATA_DIR}/BTC_USDT_{tf}.csv', parse_dates=['timestamp'])
        btc = btc.set_index('timestamp').rename(columns={
            'open': 'Open', 'high': 'High', 'low': 'Low',
            'close': 'Close', 'volume': 'Volume'})
        btc['Close'] = btc['Close'].astype(float)
        ema = btc['Close'].ewm(span=50, adjust=False).mean()
        btc['BTC_Up'] = (btc['Close'] > ema).astype(int)
        df = df.join(btc[['BTC_Up']], how='left')
        df['BTC_Up'] = df['BTC_Up'].fillna(1).astype(int)
    except FileNotFoundError:
        df['BTC_Up'] = 1
    return df


def safe_get(stats, key, default=None):
    try:
        v = stats.get(key, default)
        if v is None:
            return default
        if hasattr(v, 'item'):
            return v.item()
        return float(v)
    except Exception:
        return default


def run_grid(tf):
    print(f'\n===== Manual Optimizer {tf} (min trades={MIN_TRADES}) =====')
    df = load_data(tf)
    print(f'Bars: {len(df)}')

    tp_grid = [0.004, 0.005, 0.006, 0.007]
    sl_grid = [0.015, 0.020, 0.025]
    rsi_grid = [5, 8, 12, 20]
    cool_grid = [1, 3, 5]

    results = []
    total = len(tp_grid) * len(sl_grid) * len(rsi_grid) * len(cool_grid)
    i = 0

    for tp in tp_grid:
        for sl in sl_grid:
            if tp >= sl:
                continue
            for rsi_max in rsi_grid:
                for cool in cool_grid:
                    i += 1
                    try:
                        bt = Backtest(df, SRLongStrategy, cash=10000,
                                      commission=COMMISSION,
                                      exclusive_orders=True,
                                      finalize_trades=True)
                        s = bt.run(tp_pct=tp, sl_pct=sl,
                                   rsi2_max=rsi_max, cooldown_bars=cool,
                                   vol_factor=0.7)
                        n_trades = int(s.get('# Trades', 0) or 0)
                        wr = safe_get(s, 'Win Rate [%]', 0.0)
                        pf = safe_get(s, 'Profit Factor', 0.0)
                        ret = safe_get(s, 'Return [%]', 0.0)
                        dd = safe_get(s, 'Max. Drawdown [%]', 0.0)
                        sharpe = safe_get(s, 'Sharpe Ratio', 0.0)
                        print(f'  [{i}/{total}] tp={tp} sl={sl} rsi={rsi_max} cool={cool} '
                              f'| trades={n_trades} wr={wr:.2f} pf={pf:.2f} ret={ret:.2f}')
                        results.append({
                            'tp': tp, 'sl': sl, 'rsi2': rsi_max, 'cool': cool,
                            'trades': n_trades, 'wr': wr, 'pf': pf,
                            'ret': ret, 'dd': dd, 'sharpe': sharpe,
                        })
                    except Exception as e:
                        print(f'  Error tp={tp} sl={sl} rsi={rsi_max} cool={cool}: {e}')

    if not results:
        print('No results.')
        return

    dfr = pd.DataFrame(results)
    out_all = f'{REPORTS_DIR}/wr_opt_{tf}_all.csv'
    dfr.to_csv(out_all, index=False)
    print(f'\nSaved all results -> {out_all}')

    # Filter by min trades and PF > 1
    filtered = dfr[(dfr['trades'] >= MIN_TRADES) & (dfr['pf'] > 1.0)].copy()
    if len(filtered) == 0:
        print(f'\nNo combos with trades >= {MIN_TRADES} and PF > 1.')
        filtered = dfr[dfr['trades'] >= MIN_TRADES].copy()
        if len(filtered) == 0:
            print('Not enough trades anywhere. Lower MIN_TRADES.')
            return

    print(f'\n===== TOP 15 by WR (trades>={MIN_TRADES}, PF>1) =====')
    top_wr = filtered.sort_values('wr', ascending=False).head(15)
    print(top_wr.to_string(index=False))

    print(f'\n===== TOP 10 by Return (trades>={MIN_TRADES}) =====')
    top_ret = filtered.sort_values('ret', ascending=False).head(10)
    print(top_ret.to_string(index=False))

    print(f'\n===== TOP 10 by Sharpe (trades>={MIN_TRADES}) =====')
    top_sh = filtered.sort_values('sharpe', ascending=False).head(10)
    print(top_sh.to_string(index=False))


if __name__ == '__main__':
    tf = sys.argv[1] if len(sys.argv) > 1 else '4h'
    run_grid(tf)
