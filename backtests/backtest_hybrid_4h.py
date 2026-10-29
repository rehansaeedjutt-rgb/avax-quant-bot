"""
ULTIMATE HYBRID 4H TEST (Fixed Typo)
"""
import os
import numpy as np
import pandas as pd
import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load_data(symbol):
    if symbol == 'AVAX':
        df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_4h_MERGED_5Y.csv')
    else:
        df = pd.read_csv(f'{DATA_DIR}/LINK_USDT_4h_EXACT.csv')
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
    return df

def add_indicators(df):
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    try:
        fvg = pyvsmc.detect_fvg(high=df['h'].to_numpy(), low=df['l'].to_numpy(), close=df['c'].to_numpy())
        ob = pyvsmc.detect_order_blocks(open_=df['o'].to_numpy(), high=df['h'].to_numpy(), low=df['l'].to_numpy(), close=df['c'].to_numpy())
        df['smc_bull'] = (fvg.bullish & ~fvg.mitigated) | ob.bullish_ob
    except:
        df['smc_bull'] = True
    return df.dropna()

def run_hybrid_backtest(df, symbol):
    capital = 1000.0
    cash = capital
    pos = None
    trades = []
    equity = []
    
    tp1_pct = 0.02
    tp2_pct = 0.04
    dca1_drop = 0.015
    dca2_drop = 0.03
    cb_pct = 0.10
    
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
            if row['c'] > row['ema200'] and row['macd_bull'] and row['smc_bull']:
                cost = capital * 0.50
                units = cost / (close * (1 + SLIPPAGE))
                cash -= cost
                pos = {
                    'start_price': close, 'units': units, 'cost': cost,
                    'initial_cost': cost, 'avg': close, 'level': 1,
                    'tp1_hit': False, 
                    'tp1_price': close * (1 + tp1_pct),
                    'tp2_price': close * (1 + tp2_pct),
                    'sl': close * (1 - 0.02)
                }
                
        equity.append(cash + (pos['units'] * close if pos else 0))

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
    for symbol in ['AVAX', 'LINK']:
        print(f"\n{'='*80}")
        print(f"ULTIMATE HYBRID 4H — {symbol}")
        print(f"{'='*80}")
        
        df = load_data(symbol)
        df = add_indicators(df) # <-- Yahan typo fix ho gaya
        
        test_df = df[df.index >= '2023-01-01'].copy()
        ret, wr, pf, dd, total = run_hybrid_backtest(test_df, symbol)
        tpm = total / 36
        
        print(f"Total Return   : {ret:.2f}%")
        print(f"Win Rate (incl. BE): {wr:.2f}%")
        print(f"Profit Factor  : {pf:.2f}")
        print(f"Max Drawdown   : {dd:.2f}%")
        print(f"Total Trades   : {total} ({tpm:.1f} per month)")
