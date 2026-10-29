"""
GRID + MACRO FILTER BACKTEST
- Grid spacing: 1.0%
- TP per trade: 1.0%
- Position size: $20 per grid (Max 30 grids = $600)
- Filter: Only place new BUY orders if BTC > EMA50 AND AVAX/BTC > EMA20
- No Stop Loss, Max Hold: 7 days per trade (then force exit to free capital)
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    
    btc = pd.read_csv(f'{DATA_DIR}/BTC_USDT_1h.csv')
    btc['timestamp'] = pd.to_datetime(btc['timestamp'])
    btc = btc.set_index('timestamp').sort_index()
    btc['btc_ema50'] = btc['close'].ewm(span=50, adjust=False).mean()
    btc['btc_up'] = btc['close'] > btc['btc_ema50']
    
    # Calculate AVAX/BTC ratio
    merged = df[['c']].join(btc[['close', 'btc_up']], how='inner')
    merged['ratio'] = merged['c'] / merged['close']
    merged['ratio_ema20'] = merged['ratio'].ewm(span=20, adjust=False).mean()
    merged['ratio_up'] = merged['ratio'] > merged['ratio_ema20']
    
    # Merge filters back to AVAX df
    df = df.join(merged[['btc_up', 'ratio_up']], how='inner')
    df = df.dropna()
    return df

def backtest(df, spacing=0.01, tp_pct=0.01, per_grid=20.0, max_grids=30, max_hold_h=168):
    capital = 1000.0
    cash = capital
    positions = []
    trades = []
    equity = []
    anchor = None

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        btc_up, ratio_up = row['btc_up'], row['ratio_up']

        # 1. Check Take Profit & Time Exits
        for p in list(positions):
            hours_held = i - p['bar']
            # TP
            if high >= p['buy_price'] * (1 + tp_pct):
                sell_price = p['buy_price'] * (1 + tp_pct)
                proceeds = p['units'] * sell_price * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit = (proceeds - fee) - (p['units'] * p['buy_price'])
                trades.append({'profit_pct': (profit / (p['units'] * p['buy_price'])) * 100, 'type': 'TP'})
                positions.remove(p)
            # Time Exit (Breakeven or small loss)
            elif hours_held >= max_hold_h:
                proceeds = p['units'] * close * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit = (proceeds - fee) - (p['units'] * p['buy_price'])
                trades.append({'profit_pct': (profit / (p['units'] * p['buy_price'])) * 100, 'type': 'TIME'})
                positions.remove(p)

        # 2. Update Anchor (Trailing the high)
        if anchor is None:
            anchor = close
        elif not positions and high > anchor:
            anchor = max(anchor, close)

        # 3. Check Buys (Apply Macro Filter)
        # We only buy if BTC is up AND AVAX/BTC ratio is up
        filter_ok = btc_up and ratio_up

        if filter_ok and len(positions) < max_grids and cash >= per_grid:
            if not positions:
                next_buy_price = anchor * (1 - spacing)
            else:
                lowest_buy = min(p['buy_price'] for p in positions)
                next_buy_price = lowest_buy * (1 - spacing)

            if low <= next_buy_price:
                units = per_grid / next_buy_price
                cash -= per_grid
                positions.append({'buy_price': next_buy_price, 'units': units, 'bar': i})

        current_equity = cash + sum(p['units'] * close for p in positions)
        equity.append(current_equity)

    # Close any open positions at the end
    for p in positions:
        cash += p['units'] * df['c'].iloc[-1]

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0

    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'dd': dd, 'final': final}

if __name__ == '__main__':
    print('=' * 80)
    print('GRID + MACRO FILTER BACKTEST')
    print('=' * 80)
    df = load()
    r = backtest(df)
    
    print(f"\nFinal Balance  : ${r['final']:.2f}")
    print(f"Total Return   : {r['ret']:>8.2f}%")
    print(f"Total Trades   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")
