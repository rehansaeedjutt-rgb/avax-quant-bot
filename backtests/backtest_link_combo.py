"""
LINK COMBO INDICATOR BACKTEST (No DCA)
Combines: MACD + OBV + LINK/BTC Trend
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

def generate_indicators(df):
    # MACD
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['MACD_Cross'] = (macd > signal) & (macd.shift(1) <= signal.shift(1))
    
    # OBV
    obv = (np.sign(df['c'].diff()) * df['v']).fillna(0).cumsum()
    obv_ema = obv.ewm(span=20, adjust=False).mean()
    df['OBV_Trend'] = obv > obv_ema
    
    # LINK/BTC Ratio
    try:
        btc = pd.read_csv(f'{DATA_DIR}/BTC_USDT_1d.csv')
        btc['timestamp'] = pd.to_datetime(btc['timestamp'])
        btc = btc.set_index('timestamp').sort_index()
        merged = df[['c']].join(btc[['close']], how='inner')
        merged['ratio'] = merged['c'] / merged['close']
        merged['ratio_ema'] = merged['ratio'].ewm(span=20, adjust=False).mean()
        df = df.join(merged[['ratio', 'ratio_ema']], how='left')
        df['LINK_BTC_Trend'] = df['ratio'] > df['ratio_ema']
    except:
        df['LINK_BTC_Trend'] = False

    # COMBINED SIGNAL: MACD Cross AND OBV Trend AND LINK/BTC Trend UP
    df['Combo_Signal'] = df['MACD_Cross'] & df['OBV_Trend'] & df['LINK_BTC_Trend']
    return df.dropna()

def backtest_combo(df, tp_pct=0.05, sl_pct=0.03):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        
        if position:
            if high >= position['tp']:
                proceeds = position['units'] * position['tp'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit_pct = ((proceeds - fee) / position['cost'] - 1) * 100
                trades.append(profit_pct)
                position = None
            elif low <= position['sl']:
                proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit_pct = ((proceeds - fee) / position['cost'] - 1) * 100
                trades.append(profit_pct)
                position = None

        elif row['Combo_Signal'] and cash > 10:
            cost = cash * 0.95 
            units = cost / (close * (1 + SLIPPAGE))
            cash -= cost
            position = {
                'entry': close, 'units': units, 'cost': cost,
                'tp': close * (1 + tp_pct), 'sl': close * (1 - sl_pct)
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
    df = generate_indicators(df)
    
    ret, wr, pf, dd, total = backtest_combo(df)
    
    print('\n' + '=' * 85)
    print('LINK COMBO STRATEGY: MACD + OBV + LINK/BTC (No DCA)')
    print('=' * 85)
    print(f"Total Return   : {ret:>8.2f}%")
    print(f"Total Trades   : {total:>8}")
    print(f"Win Rate       : {wr:>8.2f}%")
    print(f"Profit Factor  : {pf:>8.2f}")
    print(f"Max Drawdown   : {dd:>8.2f}%")
    print('=' * 85)
