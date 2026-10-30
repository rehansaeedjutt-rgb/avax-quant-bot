"""
ADVANCED FILTERS BACKTEST (Deep Research Validation)
Tests adding Z-Score, ADX, and BB Width filters to the Base SMC+DCA strategy.
"""
import os
import numpy as np
import pandas as pd
import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

COINS = {
    'AVAX': 'AVAX_USDT_1d_MERGED_5Y.csv',
    'LINK': 'LINK_USDT_1d_EXACT.csv',
    'SOL': 'SOLUSDT_1d_EXACT.csv',
    'ADA': 'ADAUSDT_1d_EXACT.csv',
    'SUI': 'SUIUSDT_1d_EXACT.csv',
    'DOT': 'DOTUSDT_1d_EXACT.csv'
}

def load_data(filename):
    df = pd.read_csv(f'{DATA_DIR}/{filename}')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
    return df

def add_indicators(df):
    # Base
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    # SMC
    try:
        fvg = pyvsmc.detect_fvg(high=df['h'].to_numpy(), low=df['l'].to_numpy(), close=df['c'].to_numpy())
        ob = pyvsmc.detect_order_blocks(open_=df['o'].to_numpy(), high=df['h'].to_numpy(), low=df['l'].to_numpy(), close=df['c'].to_numpy())
        df['smc_bull'] = (fvg.bullish & ~fvg.mitigated) | ob.bullish_ob
    except:
        df['smc_bull'] = True
    
    # Z-Score (20-period)
    sma20 = df['c'].rolling(20).mean()
    std20 = df['c'].rolling(20).std()
    df['z_score'] = (df['c'] - sma20) / std20
    
    # ADX (14)
    high, low, close = df['h'], df['l'], df['c']
    plus_dm = high.diff().where(high.diff() > -low.diff(), 0).clip(lower=0)
    minus_dm = (-low.diff()).where(-low.diff() > high.diff(), 0).clip(lower=0)
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / (atr + 1e-9))
    minus_di = 100 * (minus_dm.rolling(14).mean() / (atr + 1e-9))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df['adx'] = dx.rolling(14).mean()
    
    # BB Width
    bb_upper = sma20 + 2*std20
    bb_lower = sma20 - 2*std20
    df['bb_width'] = (bb_upper - bb_lower) / (sma20 + 1e-9)
    
    return df.dropna()

def run_backtest(df, filter_condition=None):
    capital = 1000.0
    cash = capital
    pos = None
    trades = []
    equity = []
    
    tp1_pct = 0.025
    tp2_pct = 0.05
    dca1_drop = 0.02
    dca2_drop = 0.04
    cb_pct = 0.15
    
    for i in range(250, len(df)):
        row = df.iloc[i]
        close, high, low = row['c'], row['h'], row['l']
        
        if pos:
            if low <= pos['start_price'] * (1 - cb_pct):
                cash += (pos['units'] * close)
                trades.append({'profit_pct': -cb_pct*100, 'type': 'CB'})
                pos = None
                equity.append(cash)
                continue
            
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += (pos['units'] * 0.5 * pos['tp1_price'])
                pos['units'] *= 0.5
                pos['tp1_hit'] = True
                pos['sl'] = pos['avg']
                
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += (pos['units'] * pos['tp2_price'])
                trades.append({'profit_pct': tp2_pct*100, 'type': 'TP2'})
                pos = None
                equity.append(cash)
                continue
                
            if low <= pos['sl']:
                cash += (pos['units'] * pos['sl'])
                profit = ((pos['sl'] / pos['avg']) - 1) * 100
                trades.append({'profit_pct': profit, 'type': 'SL' if not pos['tp1_hit'] else 'BE'})
                pos = None
                equity.append(cash)
                continue
                
            dca1_price = pos['start_price'] * (1 - dca1_drop)
            dca2_price = pos['start_price'] * (1 - dca2_drop)
            
            if pos['level'] == 1 and low <= dca1_price:
                add_cost = pos['initial_cost'] * 0.30
                if cash >= add_cost:
                    pos['units'] += add_cost / close
                    pos['cost'] += add_cost
                    pos['avg'] = pos['cost'] / pos['units']
                    pos['tp1_price'] = pos['avg'] * (1 + tp1_pct)
                    pos['tp2_price'] = pos['avg'] * (1 + tp2_pct)
                    pos['level'] = 2
                    cash -= add_cost
            elif pos['level'] == 2 and low <= dca2_price:
                add_cost = pos['initial_cost'] * 0.20
                if cash >= add_cost:
                    pos['units'] += add_cost / close
                    pos['cost'] += add_cost
                    pos['avg'] = pos['cost'] / pos['units']
                    pos['tp1_price'] = pos['avg'] * (1 + tp1_pct)
                    pos['tp2_price'] = pos['avg'] * (1 + tp2_pct)
                    pos['level'] = 3
                    cash -= add_cost
                    
        else:
            # Base entry condition
            base_condition = row['c'] > row['ema200'] and row['macd_bull'] and row['smc_bull']
            
            # Apply additional filter if provided
            if filter_condition is not None:
                base_condition = base_condition and filter_condition(row)
                
            if base_condition:
                cost = capital * 0.50
                units = cost / (close * (1 + SLIPPAGE))
                cash -= cost
                pos = {
                    'start_price': close, 'units': units, 'cost': cost,
                    'initial_cost': cost, 'avg': close, 'level': 1,
                    'tp1_hit': False,
                    'tp1_price': close * (1 + tp1_pct),
                    'tp2_price': close * (1 + tp2_pct),
                    'sl': close * (1 - cb_pct)
                }
                
        equity.append(cash + (pos['units'] * close if pos else 0))

    if len(equity) == 0:
        return 0, 0, 0, 0, 0, 0

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    ret = (eq_arr[-1] - capital) / capital * 100
    
    wins = sum(1 for t in trades if t['profit_pct'] >= 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gw / gl) if gl > 0 else 0
    
    return ret, wr, pf, dd, total, len(trades)

if __name__ == '__main__':
    print(f"{'Coin':<6} | {'Strategy':<30} | {'Return':>8} | {'Win Rate':>8} | {'PF':>5} | {'Max DD':>7} | {'Trades':>6}")
    print('-' * 95)
    
    for coin, filename in COINS.items():
        try:
            df = load_data(filename)
            df = add_indicators(df)
        except:
            print(f"{coin:<6} | ERROR: Data missing")
            continue

        # 1. Base Strategy
        ret, wr, pf, dd, total, _ = run_backtest(df)
        print(f"{coin:<6} | {'Base (SMC + DCA)':<30} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        # 2. Base + Z-Score Filter (Z < 1.5, not overbought)
        ret, wr, pf, dd, total, _ = run_backtest(df, lambda r: r['z_score'] < 1.5)
        print(f"{coin:<6} | {'Base + Z-Score < 1.5':<30} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        # 3. Base + ADX Filter (ADX > 20, trending)
        ret, wr, pf, dd, total, _ = run_backtest(df, lambda r: r['adx'] > 20)
        print(f"{coin:<6} | {'Base + ADX > 20':<30} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        # 4. Base + BB Width Filter (Width > 0.05, not squeeze)
        ret, wr, pf, dd, total, _ = run_backtest(df, lambda r: r['bb_width'] > 0.05)
        print(f"{coin:<6} | {'Base + BB Width > 5%':<30} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        print('-' * 95)
