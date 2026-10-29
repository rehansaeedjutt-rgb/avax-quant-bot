"""
TOP-DOWN MULTI-TIMEFRAME BACKTEST (5.5 Years)
Timeframes: 1W -> 1D -> 4H -> 1H
Strategy: Trend Filter + DCA Ladder
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_data():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED_5Y.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df

def add_indicators(df, prefix):
    """Calculate EMA200, MACD, and RSI for a given timeframe."""
    df[f'{prefix}_ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df[f'{prefix}_above_ema'] = df['c'] > df[f'{prefix}_ema200']
    
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df[f'{prefix}_macd_bull'] = macd > signal
    
    delta = df['c'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    df[f'{prefix}_rsi'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    return df

def resample_and_align(df_1h):
    """Resample 1H data to 4H, 1D, 1W and forward-fill back to 1H."""
    # 4H
    df_4h = df_1h.resample('4h').agg({'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}).dropna()
    df_4h = add_indicators(df_4h, '4h')
    
    # 1D
    df_1d = df_1h.resample('1D').agg({'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}).dropna()
    df_1d = add_indicators(df_1d, '1d')
    
    # 1W
    df_1w = df_1h.resample('1W').agg({'o':'first', 'h':'max', 'l':'min', 'c':'last', 'v':'sum'}).dropna()
    df_1w = add_indicators(df_1w, '1w')
    
    # Align to 1H index (Causal - only use past data)
    df = df_1h.copy()
    df['1w_trend'] = df_1w['1w_above_ema'] & df_1w['1w_macd_bull']
    df['1d_trend'] = df_1d['1d_above_ema'] & df_1d['1d_macd_bull']
    df['4h_rsi'] = df_4h['4h_rsi']
    
    # 4H Area of Interest: RSI < 45 (Pullback zone)
    df['4h_zone'] = df['4h_rsi'] < 45
    
    # 1H Entry: MACD Bullish
    df = add_indicators(df, '1h')
    df['1h_entry'] = df['1h_macd_bull']
    
    # Forward fill higher timeframe signals to 1H
    df['1w_trend'] = df['1w_trend'].ffill()
    df['1d_trend'] = df['1d_trend'].ffill()
    df['4h_zone'] = df['4h_zone'].ffill()
    
    return df.dropna()

def backtest_topdown(df, tp_pct=0.03, max_hold=14):
    capital = 1000.0
    cash = capital
    cycle = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        hours = i # 1H bars
        
        if cycle:
            if high >= cycle['tp']:
                revenue = cycle['units'] * cycle['tp']
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100})
                cycle = None
            elif cycle['level'] < 3:
                if cycle['level'] == 1 and low <= cycle['start_price'] * 0.98:
                    add_cost = cycle['initial_cost'] * 0.30
                    if cash >= add_cost:
                        add_units = add_cost / close
                        cycle['units'] += add_units
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 2
                        cash -= add_cost
                elif cycle['level'] == 2 and low <= cycle['start_price'] * 0.96:
                    add_cost = cycle['initial_cost'] * 0.20
                    if cash >= add_cost:
                        add_units = add_cost / close
                        cycle['units'] += add_units
                        cycle['cost'] += add_cost
                        cycle['avg'] = cycle['cost'] / cycle['units']
                        cycle['tp'] = cycle['avg'] * (1 + tp_pct)
                        cycle['level'] = 3
                        cash -= add_cost
            elif hours - cycle['start_bar'] >= max_hold * 24: # 14 days in hours
                revenue = cycle['units'] * close
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100})
                cycle = None

        if cycle is None and cash > capital * 0.5:
            # TOP-DOWN LOGIC
            # 1. Weekly & Daily Trend must be UP
            # 2. 4H must be in Pullback Zone (RSI < 45)
            # 3. 1H must show Entry Trigger (MACD Bullish)
            if row['1w_trend'] and row['1d_trend'] and row['4h_zone'] and row['1h_entry']:
                cost = capital * 0.5
                units = cost / close
                cash -= cost
                cycle = {
                    'start_bar': i, 'start_price': close, 'units': units, 
                    'cost': cost, 'initial_cost': cost, 'avg': close, 
                    'tp': close * (1 + tp_pct), 'level': 1
                }

        current_equity = cash + (cycle['units'] * close if cycle else 0)
        equity.append(current_equity)

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100
    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gross_win = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gross_loss = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] <= 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    
    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'dd': dd, 'pf': pf}

if __name__ == '__main__':
    print("Loading and resampling 5.5 Years of data...")
    df_1h = load_data()
    df = resample_and_align(df_1h)
    
    print(f"Total 1H candles: {len(df)}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    
    r = backtest_topdown(df)
    
    print('\n' + '=' * 80)
    print('TOP-DOWN STRATEGY RESULTS (1W -> 1D -> 4H -> 1H)')
    print('=' * 80)
    print(f"Total Return   : {r['ret']:>8.2f}%")
    print(f"Total Trades   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Profit Factor  : {r['pf']:>8.2f}")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")
