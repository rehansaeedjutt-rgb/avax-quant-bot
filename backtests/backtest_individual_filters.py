"""
INDIVIDUAL INDICATOR BACKTEST (5 Years Daily)
Testing each filter individually against the Base DCA Strategy.
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_data():
    df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1d_MERGED_5Y.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df.dropna()

def apply_indicator(df, name):
    """Calculate specific indicator and return a boolean filter column."""
    if name == 'None':
        return pd.Series(True, index=df.index)
        
    elif name == 'EMA_200':
        ema200 = df['c'].ewm(span=200, adjust=False).mean()
        return df['c'] > ema200
        
    elif name == 'RSI_<_70':
        delta = df['c'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))
        return rsi < 70
        
    elif name == 'MACD_Bullish':
        ema12 = df['c'].ewm(span=12, adjust=False).mean()
        ema26 = df['c'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd > signal
        
    elif name == 'Bollinger_Lower':
        sma20 = df['c'].rolling(20).mean()
        std20 = df['c'].rolling(20).std()
        lower_band = sma20 - (std20 * 2)
        return df['c'] <= (lower_band * 1.02) # Near or below lower band
        
    elif name == 'OBV_Trend':
        obv = (np.sign(df['c'].diff()) * df['v']).fillna(0).cumsum()
        obv_ema = obv.ewm(span=20, adjust=False).mean()
        return obv > obv_ema
        
    elif name == 'Ichimoku_Bullish':
        # Simple Ichimoku check: Price above Kumo Cloud
        high_9 = df['h'].rolling(9).max()
        low_9 = df['l'].rolling(9).min()
        tenkan = (high_9 + low_9) / 2
        high_26 = df['h'].rolling(26).max()
        low_26 = df['l'].rolling(26).min()
        kijun = (high_26 + low_26) / 2
        return df['c'] > tenkan # Price above conversion line
        
    elif name == 'VWAP':
        vwap = (df['v'] * df['c']).cumsum() / df['v'].cumsum()
        return df['c'] < vwap # Buy when price is below VWAP

    return pd.Series(True, index=df.index)

def backtest(df, filter_series, capital=1000.0, tp_pct=0.03, max_hold=14):
    cash = capital
    cycle = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        hours = 0
        
        if cycle:
            hours = i - cycle['start_bar']
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
            elif hours >= max_hold:
                revenue = cycle['units'] * close
                fee = revenue * FEE
                cash += (revenue - fee)
                profit = revenue - cycle['cost'] - fee
                trades.append({'profit_pct': (profit / cycle['cost']) * 100})
                cycle = None

        # Entry Signal (Check specific filter)
        if cycle is None and cash > capital * 0.5:
            if filter_series.iloc[i]:
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
    
    # Calculate Profit Factor
    gross_win = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gross_loss = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] <= 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float('inf')
    
    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'dd': dd, 'pf': pf}

if __name__ == '__main__':
    df = load_data()
    indicators = [
        'None', 'EMA_200', 'RSI_<_70', 'MACD_Bullish', 
        'Bollinger_Lower', 'OBV_Trend', 'Ichimoku_Bullish', 'VWAP'
    ]
    
    print('=' * 95)
    print(f'{"Indicator Filter":<18} | {"Return":>10} | {"Trades":>6} | {"Win Rate":>8} | {"Profit Factor":>13} | {"Max DD":>8}')
    print('=' * 95)
    
    for ind in indicators:
        filter_series = apply_indicator(df, ind)
        # Drop rows where indicator is not yet calculated (NaN)
        valid_idx = filter_series.notna()
        df_valid = df[valid_idx]
        filter_valid = filter_series[valid_idx]
        
        r = backtest(df_valid, filter_valid)
        print(f'{ind:<18} | {r["ret"]:>9.2f}% | {r["trades"]:>6} | {r["wr"]:>7.2f}% | {r["pf"]:>13.2f} | {r["dd"]:>7.2f}%')
    
    print('=' * 95)
