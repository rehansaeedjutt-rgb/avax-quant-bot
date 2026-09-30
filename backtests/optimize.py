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


def load_data(tf):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}.csv', parse_dates=['timestamp'])
    df = df.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = df[c].astype(float)
    return df


def optimize_tf(tf):
    print(f'\n===== Optimizing {tf} =====')
    df = load_data(tf)
    bt = Backtest(df, SRLongStrategy, cash=10000, commission=COMMISSION,
                  exclusive_orders=True, finalize_trades=True)

    stats, heatmap = bt.optimize(
        tp_pct=[0.004, 0.005, 0.006, 0.007, 0.010],
        sl_pct=[0.010, 0.015, 0.020, 0.025],
        rsi2_max=[5, 10, 15, 20, 25],
        cooldown_bars=[1, 3, 5, 10],
        maximize='Equity Final [$]',
        constraint=lambda p: p.tp_pct < p.sl_pct,
        return_heatmap=True,
    )

    print('BEST PARAMS:', stats._strategy)
    print(stats[['Return [%]', 'Win Rate [%]', 'Profit Factor',
                 'Max. Drawdown [%]', 'Sharpe Ratio', '# Trades']])

    # Save top results
    df_heat = heatmap.reset_index()
    df_heat = df_heat.sort_values('Equity Final [$]', ascending=False)
    out = f'{REPORTS_DIR}/opt_{tf}_top.csv'
    df_heat.head(30).to_csv(out, index=False)
    print(f'Saved top 30 to {out}')
    print(df_heat.head(10).to_string(index=False))


if __name__ == '__main__':
    for tf in ['1h', '4h']:
        try:
            optimize_tf(tf)
        except Exception as e:
            print(f'Error on {tf}: {e}')
