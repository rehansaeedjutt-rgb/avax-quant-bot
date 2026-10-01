import os
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, 'C:/avax_quant_system')
from backtests.dca_backtest import load_data, run_dca


def main():
    for tf in ['15m', '5m' if os.path.exists('C:/avax_quant_system/data/AVAX_USDT_5m.csv') else '15m']:
        if tf == '15m' and not os.path.exists(f'C:/avax_quant_system/data/AVAX_USDT_15m.csv'):
            continue
        try:
            df = load_data(tf)
        except FileNotFoundError:
            print(f'\n{tf} data missing, skipping')
            continue

        print(f'\n===== DCA {tf} =====')
        print(f'Data: {len(df)} bars | {df.index[0]} -> {df.index[-1]}')

        combos = [
            (0.005, 0.003),
            (0.005, 0.005),
            (0.008, 0.005),
            (0.010, 0.005),
            (0.010, 0.010),
            (0.015, 0.010),
            (0.020, 0.010),
            (0.020, 0.015),
            (0.025, 0.015),
            (0.030, 0.020),
        ]

        print(f"{'Buy%':>6} {'Sell%':>6} {'Ret%':>8} {'Buys':>6} {'Sells':>6} "
              f"{'WR%':>6} {'MaxDD%':>8} {'Trades/Mo':>10} {'Open$':>8} {'Cash$':>8}")
        print('-' * 100)
        best = None
        for bd, sg in combos:
            r = run_dca(df, bd, sg)
            print(f"{bd*100:>5.2f}% {sg*100:>5.2f}% "
                  f"{r['return_pct']:>8.2f} {r['total_buys']:>6} {r['total_sells']:>6} "
                  f"{r['win_rate']:>6.1f} {r['max_dd']:>8.2f} {r['trades_per_month']:>10.2f} "
                  f"{r['open_value']:>8.2f} {r['cash_left']:>8.2f}")
            if best is None or r['return_pct'] > best[1]['return_pct']:
                best = ((bd, sg), r)

        print(f"\nBest: Buy drop {best[0][0]*100}% / Sell gain {best[0][1]*100}%")
        print(f"Return {best[1]['return_pct']:.2f}% | WR {best[1]['win_rate']:.1f}% | "
              f"Trades/mo {best[1]['trades_per_month']:.2f} | DD {best[1]['max_dd']:.2f}%")


if __name__ == '__main__':
    main()
