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

def calculate_adx(high, low, close, period=14):
    plus_dm = high.diff().where(high.diff() > -low.diff(), 0).clip(lower=0)
    minus_dm = (-low.diff()).where(-low.diff() > high.diff(), 0).clip(lower=0)
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / (atr + 1e-9))
    minus_di = 100 * (minus_dm.rolling(period).mean() / (atr + 1e-9))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    return dx.rolling(period).mean()

def calculate_wavetrend(high, low, close, channel_len=10, avg_len=21):
    ap = (high + low + close) / 3
    esa = ap.ewm(span=channel_len, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=channel_len, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d + 1e-9)
    wt1 = ci.ewm(span=avg_len, adjust=False).mean()
    wt2 = wt1.rolling(4).mean()
    return wt1, wt2

def calculate_ichimoku(df):
    high, low, close = df['h'], df['l'], df['c']
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (high.rolling(52).max() + low.rolling(52).min()) / 2
    cloud_top = np.maximum(senkou_a, senkou_b)
    return tenkan, kijun, cloud_top

def add_indicators(df):
    close, high, low = df['c'], df['h'], df['l']
    
    # Base
    df['ema200'] = close.ewm(span=200, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    # SMC
    try:
        fvg = pyvsmc.detect_fvg(high=high.to_numpy(), low=low.to_numpy(), close=close.to_numpy())
        ob = pyvsmc.detect_order_blocks(open_=df['o'].to_numpy(), high=high.to_numpy(), low=low.to_numpy(), close=close.to_numpy())
        df['smc_bull'] = (fvg.bullish & ~fvg.mitigated) | ob.bullish_ob
    except:
        df['smc_bull'] = True
    
    # ADX
    df['adx'] = calculate_adx(high, low, close)
    df['adx_ok'] = df['adx'] > 20
    
    # WaveTrend
    wt1, wt2 = calculate_wavetrend(high, low, close)
    df['wt1'] = wt1
    df['wt2'] = wt2
    # Bullish cross in oversold
    df['wt_cross'] = (wt1 > wt2) & (wt1.shift(1) <= wt2.shift(1)) & (wt2 < -50)
    
    # Ichimoku
    tenkan, kijun, cloud_top = calculate_ichimoku(df)
    df['ichimoku_bull'] = (close > cloud_top) & (tenkan > kijun)
    
    # RSI Divergence (Simplified)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))
    df['rsi'] = rsi
    
    # Simple divergence: Price lower low, RSI higher low over 5 bars
    price_lower_low = (close < close.shift(5)) & (close.shift(5) < close.shift(10))
    rsi_higher_low = (rsi > rsi.shift(5)) & (rsi.shift(5) < rsi.shift(10))
    df['rsi_div_bull'] = price_lower_low & rsi_higher_low & (rsi < 40)
    
    return df.dropna()

def run_backtest(df, use_wt=False, use_ichimoku=False, use_rsi_div=False):
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
            base_cond = row['c'] > row['ema200'] and row['macd_bull'] and row['smc_bull'] and row['adx_ok']
            
            if use_wt: base_cond = base_cond and row['wt_cross']
            if use_ichimoku: base_cond = base_cond and row['ichimoku_bull']
            if use_rsi_div: base_cond = base_cond and row['rsi_div_bull']
                
            if base_cond:
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
        return 0, 0, 0, 0, 0

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
    
    return ret, wr, pf, dd, total

if __name__ == '__main__':
    print(f"{'Coin':<6} | {'Strategy':<28} | {'Return':>8} | {'Win Rate':>8} | {'PF':>5} | {'Max DD':>7} | {'Trades':>6}")
    print('-' * 95)
    
    for coin, filename in COINS.items():
        try:
            df = load_data(filename)
            df = add_indicators(df)
        except Exception as e:
            print(f"{coin:<6} | ERROR: {str(e)[:50]}")
            continue

        # 1. Base + ADX (Current Live Strategy)
        ret, wr, pf, dd, total = run_backtest(df)
        print(f"{coin:<6} | {'Base (SMC+DCA+ADX)':<28} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        # 2. Base + WaveTrend
        ret, wr, pf, dd, total = run_backtest(df, use_wt=True)
        print(f"{coin:<6} | {'Base + WaveTrend':<28} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        # 3. Base + Ichimoku
        ret, wr, pf, dd, total = run_backtest(df, use_ichimoku=True)
        print(f"{coin:<6} | {'Base + Ichimoku':<28} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        # 4. Base + RSI Divergence
        ret, wr, pf, dd, total = run_backtest(df, use_rsi_div=True)
        print(f"{coin:<6} | {'Base + RSI Divergence':<28} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        # 5. Base + WaveTrend + RSI Divergence
        ret, wr, pf, dd, total = run_backtest(df, use_wt=True, use_rsi_div=True)
        print(f"{coin:<6} | {'Base + WT + RSI Div':<28} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6}")

        print('-' * 95)
