"""
LINK TREND FOLLOWING (No DCA, No Fixed TP - Trailing Stop)
"""
import os, numpy as np, pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_data():
    df = pd.read_csv(f'{DATA_DIR}/LINK_USDT_1d_EXACT.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df.dropna()

def backtest_trailing(df):
    # Indicators
    df['ema50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    df = df.dropna()

    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []
    
    # Trailing settings
    initial_sl_pct = 0.05 # 5% initial stop loss
    trail_pct = 0.10      # Trail 10% from the highest high

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        
        if position:
            # Update highest price
            if high > position['highest']:
                position['highest'] = high
                # Move stop loss up (Trailing)
                new_sl = position['highest'] * (1 - trail_pct)
                if new_sl > position['sl']:
                    position['sl'] = new_sl

            # Check Stop Loss (Trailing or Initial)
            if low <= position['sl']:
                exit_price = position['sl']
                proceeds = position['units'] * exit_price * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit_pct = ((proceeds - fee) / position['cost'] - 1) * 100
                trades.append(profit_pct)
                position = None

            # Trend Reversal Exit (EMA Cross)
            elif row['ema50'] < row['ema200'] and close < row['ema200']:
                exit_price = close
                proceeds = position['units'] * exit_price * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit_pct = ((proceeds - fee) / position['cost'] - 1) * 100
                trades.append(profit_pct)
                position = None

        elif row['macd_bull'] and row['ema50'] > row['ema200'] and cash > 10:
            # Entry
            cost = cash * 0.95
            units = cost / (close * (1 + SLIPPAGE))
            cash -= cost
            position = {
                'entry': close, 'units': units, 'cost': cost,
                'sl': close * (1 - initial_sl_pct),
                'highest': close
            }

        equity.append(cash + (position['units'] * close if position else 0))

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100
    wins = sum(1 for t in trades if t > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gross_win = sum(t for t in trades if t > 0)
    gross_loss = abs(sum(t for t in trades if t <= 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    
    return ret_pct, wr, pf, dd, total

if __name__ == '__main__':
    df = load_data()
    ret, wr, pf, dd, total = backtest_trailing(df)
    
    print('\n' + '=' * 85)
    print('LINK TREND FOLLOWING (Trailing Stop, No DCA)')
    print('=' * 85)
    print(f"Total Return   : {ret:>8.2f}%")
    print(f"Total Trades   : {total:>8}")
    print(f"Win Rate       : {wr:>8.2f}%")
    print(f"Profit Factor  : {pf:>8.2f}")
    print(f"Max Drawdown   : {dd:>8.2f}%")
    print('=' * 85)
