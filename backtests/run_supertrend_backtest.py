import os
import sys
import warnings
import pandas as pd
from backtesting import Backtest

warnings.filterwarnings('ignore')
ROOT = 'C:/avax_quant_system'
sys.path.insert(0, ROOT)

from strategies.supertrend_strategy import SupertrendStrategy
from strategies.combined_strategy import CombinedStrategy

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


def run_one(tf, strat_cls, name):
    print(f'\n===== {name} | {tf} =====')
    df = load_data(tf)
    bt = Backtest(df, strat_cls, cash=10000, commission=COMMISSION,
                  exclusive_orders=True, finalize_trades=True)
    s = bt.run()
    print(s[['Return [%]', 'Win Rate [%]', 'Profit Factor',
             'Max. Drawdown [%]', 'Sharpe Ratio', '# Trades']])
    report = f'{REPORTS_DIR}/{name}_{tf}.html'
    bt.plot(filename=report, open_browser=False)
    return s


if __name__ == '__main__':
    summary = {}
    for tf in ['15m', '1h', '4h']:
        for strat_cls, name in [(SupertrendStrategy, 'ST'),
                                 (CombinedStrategy, 'ST_COMB')]:
            key = f'{name}_{tf}'
            try:
                s = run_one(tf, strat_cls, name)
                summary[key] = {
                    'Return [%]': round(s.get('Return [%]', 0), 2),
                    'Win Rate [%]': round(s.get('Win Rate [%]', 0) or 0, 2),
                    'Profit Factor': round(s.get('Profit Factor', 0) or 0, 2),
                    'Max DD [%]': round(s.get('Max. Drawdown [%]', 0), 2),
                    '# Trades': int(s.get('# Trades', 0)),
                }
            except Exception as e:
                print(f'Error on {key}: {e}')
                summary[key] = {'Error': str(e)}

    print('\n\n===== SUPERTREND SUMMARY =====')
    df_sum = pd.DataFrame(summary).T
    print(df_sum)
    df_sum.to_csv(f'{REPORTS_DIR}/supertrend_summary.csv')
