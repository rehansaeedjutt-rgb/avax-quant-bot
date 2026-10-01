import os
import sys
import warnings
import pandas as pd
from backtesting import Backtest

warnings.filterwarnings('ignore')
ROOT = 'C:/avax_quant_system'
sys.path.insert(0, ROOT)
from strategies.sr_bounce_strategy import SRBounceStrategy

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


def run_one(tf):
    print(f'\n===== SR Bounce {tf} =====')
    df = load_data(tf)
    print(f'Bars: {len(df)} | {df.index[0]} -> {df.index[-1]}')
    bt = Backtest(df, SRBounceStrategy, cash=10000, commission=COMMISSION,
                  exclusive_orders=True, finalize_trades=True)
    stats = bt.run()
    print(stats[['Return [%]', 'Win Rate [%]', 'Profit Factor',
                 'Max. Drawdown [%]', 'Sharpe Ratio', '# Trades']])
    report = f'{REPORTS_DIR}/SR_{tf}.html'
    bt.plot(filename=report, open_browser=False)
    print(f'Saved chart -> {report}')
    return stats


if __name__ == '__main__':
    summary = {}
    for tf in ['15m', '1h', '4h']:
        try:
            s = run_one(tf)
            summary[tf] = {
                'Return [%]': round(s.get('Return [%]', 0), 2),
                'Win Rate [%]': round(s.get('Win Rate [%]', 0) or 0, 2),
                'Profit Factor': round(s.get('Profit Factor', 0) or 0, 2),
                'Max DD [%]': round(s.get('Max. Drawdown [%]', 0), 2),
                '# Trades': int(s.get('# Trades', 0)),
            }
        except Exception as e:
            print(f'Error on {tf}: {e}')
            summary[tf] = {'Error': str(e)}

    print('\n\n===== SR BOUNCE SUMMARY =====')
    df_sum = pd.DataFrame(summary).T
    print(df_sum)
    df_sum.to_csv(f'{REPORTS_DIR}/sr_summary.csv')
