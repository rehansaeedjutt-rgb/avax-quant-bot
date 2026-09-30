import os, sys, warnings, json
import pandas as pd
from backtesting import Backtest

warnings.filterwarnings('ignore')
ROOT = 'C:/avax_quant_system'
sys.path.insert(0, ROOT)
from strategies.sr_long_strategy import SRLongStrategy

DATA_DIR = f'{ROOT}/data'
CONFIG_DIR = f'{ROOT}/config'
os.makedirs(CONFIG_DIR, exist_ok=True)
COMMISSION = 0.0002


def load_data(tf):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}.csv', parse_dates=['timestamp'])
    df = df.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = df[c].astype(float)
    btc = pd.read_csv(f'{DATA_DIR}/BTC_USDT_{tf}.csv', parse_dates=['timestamp'])
    btc = btc.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    btc['Close'] = btc['Close'].astype(float)
    ema = btc['Close'].ewm(span=50, adjust=False).mean()
    btc['BTC_Up'] = (btc['Close'] > ema).astype(int)
    df = df.join(btc[['BTC_Up']], how='left')
    df['BTC_Up'] = df['BTC_Up'].fillna(1).astype(int)
    return df


def run_final(tf):
    print(f'\n===== FINAL: AVAX/USDT {tf} =====')
    df = load_data(tf)
    bt = Backtest(df, SRLongStrategy, cash=10000, commission=COMMISSION,
                  exclusive_orders=True, finalize_trades=True)
    s = bt.run()
    result = {
        'timeframe': tf,
        'Return [%]': float(s.get('Return [%]', 0)),
        'Win Rate [%]': float(s.get('Win Rate [%]', 0) or 0),
        'Profit Factor': float(s.get('Profit Factor', 0) or 0),
        'Max Drawdown [%]': float(s.get('Max. Drawdown [%]', 0)),
        'Sharpe Ratio': float(s.get('Sharpe Ratio', 0) or 0),
        '# Trades': int(s.get('# Trades', 0)),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    final = {}
    for tf in ['1h', '15m']:
        final[tf] = run_final(tf)
    out = f'{CONFIG_DIR}/locked_strategy.json'
    with open(out, 'w') as f:
        json.dump(final, f, indent=2)
    print(f'\nLocked strategy config saved -> {out}')
