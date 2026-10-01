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


def run_dca(df, buy_drop_pct, sell_gain_pct, capital=1000,
            per_buy_dollars=50, max_buys=15):
    """
    DCA + Take Profit backtest.
    - Buy when price drops buy_drop_pct from last buy (first buy at start)
    - Sell ALL when price >= avg_entry * (1 + sell_gain_pct)
    - NEVER stop out. Hold forever if not profitable.
    """
    cash = capital
    units = 0.0
    avg_entry = 0.0
    last_buy_price = None
    buy_cycle_count = 0

    buys = []
    sells = []
    equity_curve = []

    closes = df['Close'].to_numpy()
    index = df.index
    max_capital_deployed = 0.0

    for i, price in enumerate(closes):
        # SELL condition first
        if units > 0 and price >= avg_entry * (1 + sell_gain_pct):
            proceeds = units * price
            profit = proceeds - units * avg_entry
            cash += proceeds
            sells.append({
                'time': str(index[i]), 'price': price,
                'units': units, 'avg_entry': avg_entry,
                'profit': profit,
            })
            units = 0.0
            avg_entry = 0.0
            last_buy_price = None
            buy_cycle_count = 0

        # BUY condition
        else:
            should_buy = False
            if last_buy_price is None and buy_cycle_count == 0:
                should_buy = True
            elif last_buy_price is not None and price <= last_buy_price * (1 - buy_drop_pct):
                should_buy = True

            if should_buy and cash >= per_buy_dollars and buy_cycle_count < max_buys:
                buy_units = per_buy_dollars / price
                new_total_cost = units * avg_entry + per_buy_dollars
                units += buy_units
                avg_entry = new_total_cost / units
                cash -= per_buy_dollars
                last_buy_price = price
                buy_cycle_count += 1
                deployed = units * price
                max_capital_deployed = max(max_capital_deployed, deployed)
                buys.append({
                    'time': str(index[i]), 'price': price,
                    'units': buy_units, 'cash_left': cash,
                })

        equity_curve.append(cash + units * price)

    final_value = cash + units * closes[-1]
    return_pct = (final_value - capital) / capital * 100

    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = dd.min() * 100

    wins = sum(1 for s in sells if s['profit'] > 0)
    losses = sum(1 for s in sells if s['profit'] <= 0)
    total_sells = len(sells)
    wr = wins / total_sells * 100 if total_sells else 0

    # Years covered
    days = (df.index[-1] - df.index[0]).days
    years = days / 365.25
    trades_per_year = total_sells / years if years > 0 else 0

    return {
        'return_pct': return_pct,
        'final_value': final_value,
        'total_buys': len(buys),
        'total_sells': total_sells,
        'wins': wins,
        'losses': losses,
        'win_rate': wr,
        'max_dd': max_dd,
        'open_units': units,
        'open_value': units * closes[-1],
        'cash_left': cash,
        'max_capital_deployed': max_capital_deployed,
        'trades_per_year': trades_per_year,
        'trades_per_month': trades_per_year / 12,
    }


def main():
    tf = '1h'
    df = load_data(tf)
    print(f"\nData: {len(df)} bars | {df.index[0]} -> {df.index[-1]}")

    combos = [
        (0.01, 0.005),  # 1% drop, 0.5% gain
        (0.01, 0.01),   # 1% drop, 1% gain
        (0.02, 0.005),  # 2% drop, 0.5% gain
        (0.02, 0.01),   # 2% drop, 1% gain
        (0.02, 0.02),   # 2% drop, 2% gain
        (0.03, 0.01),   # 3% drop, 1% gain
        (0.03, 0.02),   # 3% drop, 2% gain
        (0.05, 0.02),   # 5% drop, 2% gain
        (0.05, 0.03),   # 5% drop, 3% gain
        (0.05, 0.05),   # 5% drop, 5% gain
    ]

    print(f"\n{'Buy%':>6} {'Sell%':>6} {'Ret%':>8} {'Buys':>6} {'Sells':>6} "
          f"{'WR%':>6} {'MaxDD%':>8} {'Trades/Mo':>10} {'Open$':>8} {'Cash$':>8}")
    print('-' * 100)

    best = None
    for buy_drop, sell_gain in combos:
        r = run_dca(df, buy_drop, sell_gain)
        print(f"{buy_drop*100:>5.1f}% {sell_gain*100:>5.1f}% "
              f"{r['return_pct']:>8.2f} {r['total_buys']:>6} {r['total_sells']:>6} "
              f"{r['win_rate']:>6.1f} {r['max_dd']:>8.2f} {r['trades_per_month']:>10.2f} "
              f"{r['open_value']:>8.2f} {r['cash_left']:>8.2f}")

        if best is None or r['return_pct'] > best[1]['return_pct']:
            best = ((buy_drop, sell_gain), r)

    print(f"\n===== BEST COMBO =====")
    print(f"Buy drop: {best[0][0]*100}% | Sell gain: {best[0][1]*100}%")
    print(f"Return: {best[1]['return_pct']:.2f}%")
    print(f"Win Rate: {best[1]['win_rate']:.2f}%")
    print(f"Trades: {best[1]['total_sells']} sells / {best[1]['total_buys']} buys")
    print(f"Trades per month: {best[1]['trades_per_month']:.2f}")
    print(f"Max Drawdown: {best[1]['max_dd']:.2f}%")
    print(f"Open position value at end: ${best[1]['open_value']:.2f}")
    print(f"Cash at end: ${best[1]['cash_left']:.2f}")


if __name__ == '__main__':
    main()
