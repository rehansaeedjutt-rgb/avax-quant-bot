import os
import sys
import pandas as pd
from backtesting import Backtest

ROOT = 'C:/avax_quant_system'
sys.path.insert(0, ROOT)
from strategies.sr_long_strategy import SRLongStrategy

TIMEFRAMES = ['15m', '1h', '4h', '1d', '1w']
DATA_DIR = f'{ROOT}/data'
REPORTS_DIR = f'{ROOT}/reports'
os.makedirs(REPORTS_DIR, exist_ok=True)
COMMISSION = 0.0002


def load_avax(tf):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}.csv', parse_dates=['timestamp'])
    df = df.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = df[c].astype(float)
    return df


def load_btc_trend(tf):
    try:
        btc = pd.read_csv(f'{DATA_DIR}/BTC_USDT_{tf}.csv', parse_dates=['timestamp'])
    except FileNotFoundError:
        return None
    btc = btc.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    btc['Close'] = btc['Close'].astype(float)
    ema = btc['Close'].ewm(span=50, adjust=False).mean()
    btc['BTC_Up'] = (btc['Close'] > ema).astype(int)
    return btc[['BTC_Up']]


def load_data(tf):
    df = load_avax(tf)
    btc = load_btc_trend(tf)
    if btc is not None:
        df = df.join(btc, how='left')
        df['BTC_Up'] = df['BTC_Up'].fillna(1).astype(int)
    else:
        df['BTC_Up'] = 1
    return df


def run_one(tf):
    print(f'\n===== Backtesting AVAX/USDT {tf} =====')
    df = load_data(tf)
    print(f'Data: {len(df)} bars, {df.index[0]} -> {df.index[-1]}')
    bt = Backtest(df, SRLongStrategy, cash=10000, commission=COMMISSION,
                  exclusive_orders=True, finalize_trades=True)
    stats = bt.run()
    print(stats)
    report_path = f'{REPORTS_DIR}/AVAX_{tf}_backtest.html'
    bt.plot(filename=report_path, open_browser=False)
    return stats


if __name__ == '__main__':
    summary = {}
    for tf in TIMEFRAMES:
        try:
            s = run_one(tf)
            summary[tf] = {
                'Return [%]': round(s.get('Return [%]', 0), 2),
                'Win Rate [%]': round(s.get('Win Rate [%]', 0), 2),
                'Profit Factor': round(s.get('Profit Factor', 0), 2),
                'Max Drawdown [%]': round(s.get('Max. Drawdown [%]', 0), 2),
                'Sharpe Ratio': round(s.get('Sharpe Ratio', 0), 2),
                '# Trades': int(s.get('# Trades', 0)),
            }
        except Exception as e:
            print(f'Error on {tf}: {e}')
            summary[tf] = {'Error': str(e)}
    print('\n\n===== SUMMARY =====')
    summary_df = pd.DataFrame(summary).T
    print(summary_df)
    summary_df.to_csv(f'{REPORTS_DIR}/summary.csv')
