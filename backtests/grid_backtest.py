import os
import pandas as pd
import numpy as np

ROOT = 'C:/avax_quant_system'
DATA_DIR = f'{ROOT}/data'


def load_data(tf):
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_{tf}.csv', parse_dates=['timestamp'])
    df = df.set_index('timestamp').rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low',
        'close': 'Close', 'volume': 'Volume'})
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[c] = df[c].astype(float)
    return df


def run_grid(df, spacing_pct, sell_gain_pct, capital=1000,
             per_grid_dollars=20, max_grids=20,
             max_hold_hours=168):  # 7 days = 168 hours
    """
    Grid bot backtest.
    - Grid levels every spacing_pct below the highest price seen
    - Each grid buys per_grid_dollars worth
    - Sell when price >= buy_price * (1 + sell_gain_pct)
    - Force exit at breakeven after max_hold_hours (no loss, no gain)
    """
    cash = capital
    positions = []  # each: {'buy_price', 'units', 'buy_time', 'buy_idx'}
    closed = []
    forced_exits = 0
    grid_anchor = None
    equity_curve = []

    closes = df['Close'].to_numpy()
    highs = df['High'].to_numpy()
    lows = df['Low'].to_numpy()
    index = df.index

    for i in range(len(df)):
        high = highs[i]
        low = lows[i]
        close = closes[i]
        ts = index[i]

        # 1. SELL CHECK (use high)
        for pos in list(positions):
            if high >= pos['buy_price'] * (1 + sell_gain_pct):
                sell_price = pos['buy_price'] * (1 + sell_gain_pct)
                proceeds = pos['units'] * sell_price
                cash += proceeds
                closed.append({
                    'profit': proceeds - pos['units'] * pos['buy_price'],
                    'hold_hours': (ts - pos['buy_time']).total_seconds() / 3600,
                    'forced': False,
                })
                positions.remove(pos)

        # 2. FORCED EXIT CHECK (breakeven, after max hold)
        for pos in list(positions):
            held_hours = (ts - pos['buy_time']).total_seconds() / 3600
            if held_hours >= max_hold_hours and high >= pos['buy_price']:
                sell_price = pos['buy_price']  # breakeven
                proceeds = pos['units'] * sell_price
                cash += proceeds
                closed.append({
                    'profit': 0,
                    'hold_hours': held_hours,
                    'forced': True,
                })
                positions.remove(pos)
                forced_exits += 1

        # 3. GRID ANCHOR RESET
        if grid_anchor is None:
            grid_anchor = close
        elif not positions and high > grid_anchor:
            grid_anchor = max(grid_anchor, close)

        # 4. BUY CHECK (use low)
        if len(positions) < max_grids and cash >= per_grid_dollars:
            # Find next unfilled grid level
            if not positions:
                next_level_price = grid_anchor * (1 - spacing_pct)
            else:
                lowest_buy = min(p['buy_price'] for p in positions)
                next_level_price = lowest_buy * (1 - spacing_pct)

            if low <= next_level_price:
                units = per_grid_dollars / next_level_price
                cash -= per_grid_dollars
                positions.append({
                    'buy_price': next_level_price,
                    'units': units,
                    'buy_time': ts,
                    'buy_idx': i,
                })

        equity_curve.append(cash + sum(p['units'] * close for p in positions))

    # Final metrics
    final_equity = equity_curve[-1]
    return_pct = (final_equity - capital) / capital * 100

    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = dd.min() * 100

    total_closed = len(closed)
    wins = sum(1 for c in closed if c['profit'] > 0)
    wr = wins / total_closed * 100 if total_closed else 0

    holds = [c['hold_hours'] for c in closed if not c['forced']]
    avg_hold = np.mean(holds) if holds else 0
    median_hold = np.median(holds) if holds else 0
    within_7d = sum(1 for h in holds if h <= 168) / len(holds) * 100 if holds else 0
    within_3d = sum(1 for h in holds if h <= 72) / len(holds) * 100 if holds else 0
    within_1d = sum(1 for h in holds if h <= 24) / len(holds) * 100 if holds else 0

    days = (df.index[-1] - df.index[0]).days
    years = days / 365.25
    trades_per_month = total_closed / years / 12 if years else 0
    trades_per_week = trades_per_month * 12 / 52

    open_units_value = sum(p['units'] * closes[-1] for p in positions)

    return {
        'return_pct': return_pct,
        'final_equity': final_equity,
        'total_closed': total_closed,
        'win_rate': wr,
        'max_dd': max_dd,
        'avg_hold_hours': avg_hold,
        'median_hold_hours': median_hold,
        'within_24h_pct': within_1d,
        'within_3d_pct': within_3d,
        'within_7d_pct': within_7d,
        'trades_per_month': trades_per_month,
        'trades_per_week': trades_per_week,
        'open_positions': len(positions),
        'open_value': open_units_value,
        'cash_left': cash,
        'forced_exits': forced_exits,
    }


def main():
    tf = '15m'
    df = load_data(tf)
    print(f"\nData: {len(df)} bars | {df.index[0]} -> {df.index[-1]}")
    print(f"Timeframe: {tf}\n")

    combos = [
        # (spacing, sell_gain, per_grid, max_grids)
        (0.005, 0.005, 20, 30),
        (0.008, 0.008, 20, 30),
        (0.010, 0.010, 20, 30),
        (0.010, 0.015, 20, 30),
        (0.015, 0.010, 20, 30),
        (0.015, 0.015, 20, 30),
        (0.020, 0.015, 20, 30),
        (0.020, 0.020, 20, 30),
        (0.025, 0.020, 20, 30),
        (0.030, 0.020, 20, 30),
    ]

    print(f"{'Spc%':>5} {'Sell%':>6} {'Ret%':>8} {'Sells':>6} {'WR%':>5} "
          f"{'DD%':>7} {'AvgHld':>7} {'<1d%':>6} {'<3d%':>6} {'<7d%':>6} "
          f"{'T/Mo':>6} {'Open$':>7}")
    print('-' * 110)

    best = None
    for spacing, sell, per_grid, max_g in combos:
        r = run_grid(df, spacing, sell, capital=1000,
                     per_grid_dollars=per_grid, max_grids=max_g)
        avg_h = f"{r['avg_hold_hours']:.0f}h"
        print(f"{spacing*100:>4.2f}% {sell*100:>5.2f}% "
              f"{r['return_pct']:>8.2f} {r['total_closed']:>6} {r['win_rate']:>5.1f} "
              f"{r['max_dd']:>7.2f} {avg_h:>7} {r['within_24h_pct']:>5.1f}% "
              f"{r['within_3d_pct']:>5.1f}% {r['within_7d_pct']:>5.1f}% "
              f"{r['trades_per_month']:>6.2f} {r['open_value']:>7.2f}")
        # Score: return * (within_7d_pct/100) - penalty for high DD
        score = r['return_pct'] * (r['within_7d_pct'] / 100) if r['within_7d_pct'] else 0
        if best is None or score > best[1]:
            best = ((spacing, sell, per_grid, max_g), score, r)

    print(f"\n===== BEST COMBO (by Return x Within7d Score) =====")
    print(f"Spacing: {best[0][0]*100}% | Sell gain: {best[0][1]*100}%")
    print(f"Return: {best[2]['return_pct']:.2f}%")
    print(f"Win Rate: {best[2]['win_rate']:.1f}%")
    print(f"Total sells: {best[2]['total_closed']}")
    print(f"Trades/month: {best[2]['trades_per_month']:.2f}")
    print(f"Trades/week: {best[2]['trades_per_week']:.2f}")
    print(f"Avg hold: {best[2]['avg_hold_hours']:.1f} hours ({best[2]['avg_hold_hours']/24:.1f} days)")
    print(f"Within 24h: {best[2]['within_24h_pct']:.1f}%")
    print(f"Within 3 days: {best[2]['within_3d_pct']:.1f}%")
    print(f"Within 7 days: {best[2]['within_7d_pct']:.1f}%")
    print(f"Max Drawdown: {best[2]['max_dd']:.2f}%")
    print(f"Open positions at end: {best[2]['open_positions']} (${best[2]['open_value']:.2f})")
    print(f"Cash at end: ${best[2]['cash_left']:.2f}")


if __name__ == '__main__':
    main()
