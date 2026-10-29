"""
LINK MASTER INDICATOR BACKTEST (No DCA - Pure Swing)
Tests individual indicators on 7.5 years of LINK data.
"""
import os
import numpy as np
import pandas as pd

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

def backtest_single_indicator(df, signal_col):
    """
    Standard Swing Backtest:
    - Entry: When signal is True
    - TP: +5%
    - SL: -3%
    - No DCA.
    """
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []
    tp_pct = 0.05
    sl_pct = 0.03

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        
        if position:
            # Check TP
            if high >= position['tp']:
                proceeds = position['units'] * position['tp'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit_pct = ((proceeds - fee) / position['cost'] - 1) * 100
                trades.append(profit_pct)
                position = None
            # Check SL
            elif low <= position['sl']:
                proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                profit_pct = ((proceeds - fee) / position['cost'] - 1) * 100
                trades.append(profit_pct)
                position = None

        # Check Entry
        elif row[signal_col] and cash > 10:
            cost = cash * 0.95 # Risk 95% of account per trade
            units = cost / (close * (1 + SLIPPAGE))
            cash -= cost
            position = {
                'entry': close,
                'units': units,
                'cost': cost,
                'tp': close * (1 + tp_pct),
                'sl': close * (1 - sl_pct)
            }

        equity.append(cash + (position['units'] * close if position else 0))

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100 if len(eq_arr) > 0 else 0
    final = eq_arr[-1] if len(eq_arr) > 0 else capital
    ret_pct = (final - capital) / capital * 100
    
    wins = sum(1 for t in trades if t > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gross_win = sum(t for t in trades if t > 0)
    gross_loss = abs(sum(t for t in trades if t <= 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')

    return ret_pct, wr, pf, dd, total

def generate_indicators(df):
    # 1. RSI (14)
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    df['RSI_30'] = (100 - (100 / (1 + rs))) < 30  # Oversold
    
    # 2. EMA (50/200 Cross)
    df['EMA50'] = df['c'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['EMA_Cross'] = (df['EMA50'] > df['EMA200']) & (df['EMA50'].shift(1) <= df['EMA200'].shift(1))
    
    # 3. MACD (12, 26, 9)
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['MACD_Cross'] = (macd > signal) & (macd.shift(1) <= signal.shift(1))
    
    # 4. Fibonacci (Rolling 100-day High/Low, Golden Pocket 0.618)
    high100 = df['h'].rolling(100).max()
    low100 = df['l'].rolling(100).min()
    fib_618 = high100 - (high100 - low100) * 0.618
    df['Fib_618'] = (df['c'] <= fib_618 * 1.01) & (df['c'] > fib_618 * 0.99)
    
    # 5. OBV (On Balance Volume)
    obv = (np.sign(df['c'].diff()) * df['v']).fillna(0).cumsum()
    obv_ema = obv.ewm(span=20, adjust=False).mean()
    df['OBV_Trend'] = (obv > obv_ema) & (obv.shift(1) <= obv_ema.shift(1))
    
    # 6. Ichimoku (Kumo Breakout)
    high9 = df['h'].rolling(9).max()
    low9 = df['l'].rolling(9).min()
    tenkan = (high9 + low9) / 2
    high26 = df['h'].rolling(26).max()
    low26 = df['l'].rolling(26).min()
    kijun = (high26 + low26) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (df['h'].rolling(52).max() + df['l'].rolling(52).min()) / 2
    cloud_top = np.maximum(senkou_a, senkou_b)
    df['Ichimoku_Break'] = (df['c'] > cloud_top) & (df['c'].shift(1) <= cloud_top.shift(1))
    
    # 7. Bollinger Bands (Mean Reversion Lower Band)
    sma20 = df['c'].rolling(20).mean()
    std20 = df['c'].rolling(20).std()
    lower_band = sma20 - (std20 * 2)
    df['BB_Lower'] = df['c'] <= lower_band
    
    # 8. VWAP (Approximated Cumulative)
    df['VWAP'] = (df['v'] * df['c']).cumsum() / df['v'].cumsum()
    df['VWAP_Dip'] = (df['c'] < df['VWAP']) & (df['c'].shift(1) >= df['VWAP'].shift(1))
    
    # 9. LINK/BTC Ratio
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
        df['LINK_BTC_Trend'] = False # Skip if no BTC data

    return df.dropna()

if __name__ == '__main__':
    print("Loading LINK Data (2019 - 2026)...")
    df = load_data()
    df = generate_indicators(df)
    
    indicators = [
        'RSI_30', 'EMA_Cross', 'MACD_Cross', 'Fib_618', 
        'OBV_Trend', 'Ichimoku_Break', 'BB_Lower', 'VWAP_Dip', 'LINK_BTC_Trend'
    ]
    
    print('\n' + '=' * 95)
    print('LINK INDIVIDUAL INDICATOR BACKTEST (No DCA, TP:5%, SL:3%)')
    print('=' * 95)
    print(f'{"Indicator":<20} | {"Return":>10} | {"Trades":>7} | {"Win Rate":>9} | {"Profit Factor":>13} | {"Max DD":>8}')
    print('-' * 95)
    
    for ind in indicators:
        ret, wr, pf, dd, total = backtest_single_indicator(df, ind)
        print(f'{ind:<20} | {ret:>9.2f}% | {total:>7} | {wr:>8.2f}% | {pf:>13.2f} | {dd:>7.2f}%')
        
    print('=' * 95)
    print("\nNote: Paid indicators (Glassnode, MVRV, Liquidation Heatmaps) cannot be tested without API.")
    print("Testing done on pure price action & volume data.")
