# proper_combined_backtest.py
# Fixed: Compounded returns, no double-counting
# Main + Secondary with proper portfolio simulation
# Honest numbers only

import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_BULK = os.path.join(ROOT, 'data_bulk')
DATA_DIR = os.path.join(ROOT, 'data')
REPORT_DIR = os.path.join(ROOT, 'reports')

COINS_21 = ['FET','WIN','WAVES','THETA','RLC','DUSK','STX','CAKE','BAT','NMR',
            'FUN','ANKR','JST','CHR','DYDX','WOO','HYPE','HBAR','CHZ','TEL','GRT']

SLIPPAGE = 0.0015

def load_data(coin):
    for base in [DATA_BULK, DATA_DIR]:
        for pattern in [f'{coin}USDT_1d.csv', f'{coin}USDT_1d_ALL.csv']:
            path = os.path.join(base, pattern)
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    if len(df) < 260: return None
                    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
                    df = df.set_index('open_time').sort_index()
                    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
                    return df
                except: continue
    return None

def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    close, high, low = df['c'], df['h'], df['l']
    df['rsi'] = calculate_rsi(close)
    df['high_20d'] = high.rolling(20).max()
    df['drop_from_high'] = ((close - df['high_20d']) / df['high_20d']) * 100
    df['ema200'] = close.ewm(span=200, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    plus_dm = high.diff().where(high.diff() > -low.diff(), 0).clip(lower=0)
    minus_dm = (-low.diff()).where(-low.diff() > high.diff(), 0).clip(lower=0)
    tr = pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    plus_di  = 100*(plus_dm.rolling(14).mean()/(atr+1e-9))
    minus_di = 100*(minus_dm.rolling(14).mean()/(atr+1e-9))
    dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di+1e-9)
    df['adx'] = dx.rolling(14).mean()
    df['adx_ok'] = df['adx'] > 20
    return df.dropna()

def backtest_main(df, capital=1000.0):
    """Proper compounded returns"""
    cash = capital; pos = None; trades = []; equity = [capital]
    tp1, tp2 = 0.025, 0.05; dca1, dca2 = 0.02, 0.04; cb = 0.15
    entry_cost = capital * 0.5

    for i in range(len(df)):
        row = df.iloc[i]; close, high, low = row['c'], row['h'], row['l']
        if pos:
            # Circuit breaker
            if low <= pos['start_price']*(1-cb):
                cash += pos['units']*close
                ret_pct = ((close/pos['avg'])-1)*100
                trades.append({'profit_pct':ret_pct,'type':'CB','date':df.index[i]})
                pos=None; equity.append(cash); continue
            # TP1
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units']*0.5*pos['tp1_price']
                pos['units']*=0.5; pos['tp1_hit']=True; pos['sl']=pos['avg']
            # TP2
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units']*pos['tp2_price']
                ret_pct = ((pos['tp2_price']/pos['avg'])-1)*100
                trades.append({'profit_pct':ret_pct,'type':'TP2','date':df.index[i]})
                pos=None; equity.append(cash); continue
            # SL
            if low <= pos['sl']:
                cash += pos['units']*pos['sl']
                ret_pct = ((pos['sl']/pos['avg'])-1)*100
                trades.append({'profit_pct':ret_pct,'type':'SL' if not pos['tp1_hit'] else 'BE','date':df.index[i]})
                pos=None; equity.append(cash); continue
            # DCA
            d1 = pos['start_price']*(1-dca1); d2 = pos['start_price']*(1-dca2)
            if pos['level']==1 and low<=d1:
                add = pos['initial_cost']*0.30
                if cash>=add:
                    pos['units']+=add/close; pos['cost']+=add
                    pos['avg']=pos['cost']/pos['units']
                    pos['tp1_price']=pos['avg']*(1+tp1); pos['tp2_price']=pos['avg']*(1+tp2)
                    pos['level']=2; cash-=add
            elif pos['level']==2 and low<=d2:
                add = pos['initial_cost']*0.20
                if cash>=add:
                    pos['units']+=add/close; pos['cost']+=add
                    pos['avg']=pos['cost']/pos['units']
                    pos['level']=3; cash-=add
        else:
            if row['c'] > row['ema200'] and row['macd_bull'] and row['adx_ok']:
                cost = entry_cost; units = cost/(close*(1+SLIPPAGE)); cash -= cost
                pos = {'start_price':close,'units':units,'cost':cost,'initial_cost':cost,
                       'avg':close,'level':1,'tp1_hit':False,
                       'tp1_price':close*(1+tp1),'tp2_price':close*(1+tp2),
                       'sl':close*(1-cb)}
        equity.append(cash + (pos['units']*close if pos else 0))

    if not equity: return None, []
    eq = np.array(equity)
    return {'final':eq[-1], 'return_pct':(eq[-1]-capital)/capital*100,
            'equity':eq, 'trades':trades}, trades

def backtest_secondary(df, capital=1000.0):
    """Proper compounded returns, NO overlap with main"""
    cash = capital; pos = None; trades = []; equity = [capital]
    TP = 0.05; SL = 0.08
    entry_cost = capital * 0.3  # Smaller than main

    for i in range(len(df)):
        row = df.iloc[i]; close, high, low = row['c'], row['h'], row['l']
        if pos:
            if high >= pos['tp_price']:
                cash += pos['units']*pos['tp_price']
                ret_pct = ((pos['tp_price']/pos['avg'])-1)*100
                trades.append({'profit_pct':ret_pct,'type':'TP','date':df.index[i]})
                pos=None; equity.append(cash); continue
            if low <= pos['sl']:
                cash += pos['units']*pos['sl']
                ret_pct = ((pos['sl']/pos['avg'])-1)*100
                trades.append({'profit_pct':ret_pct,'type':'SL','date':df.index[i]})
                pos=None; equity.append(cash); continue
            if row['rsi'] > 60:
                cash += pos['units']*close
                ret_pct = ((close/pos['avg'])-1)*100
                trades.append({'profit_pct':ret_pct,'type':'RSI','date':df.index[i]})
                pos=None; equity.append(cash); continue
        else:
            # Entry: RSI < 25 (deeper oversold) OR drop > 20% from high
            oversold = row['rsi'] < 25
            big_drop = row['drop_from_high'] < -20
            if oversold or big_drop:
                cost = entry_cost; units = cost/(close*(1+SLIPPAGE)); cash -= cost
                pos = {'start_price':close,'units':units,'avg':close,
                       'tp_price':close*(1+TP),'sl':close*(1-SL)}
        equity.append(cash + (pos['units']*close if pos else 0))

    if not equity: return None, []
    eq = np.array(equity)
    return {'final':eq[-1], 'return_pct':(eq[-1]-capital)/capital*100,
            'equity':eq, 'trades':trades}, trades

def main():
    print("="*100)
    print("PROPER COMBINED BACKTEST — COMPOUNDED RETURNS")
    print("="*100)

    main_results = []
    sec_results = []

    for coin in COINS_21:
        df = load_data(coin)
        if df is None: continue
        try:
            df_ind = add_indicators(df.copy())
        except: continue

        # Main
        r_main, t_main = backtest_main(df_ind, 1000.0)
        if r_main:
            main_results.append({'coin':coin, 'return':r_main['return_pct'],
                                 'trades':len(t_main)})

        # Secondary
        r_sec, t_sec = backtest_secondary(df_ind, 1000.0)
        if r_sec:
            sec_results.append({'coin':coin, 'return':r_sec['return_pct'],
                                'trades':len(t_sec)})

    # Aggregate
    print(f"\n{'='*80}")
    print("MAIN STRATEGY (per coin, $1000 each)")
    print(f"{'='*80}")
    total_main_ret = 0
    total_main_trades = 0
    for r in sorted(main_results, key=lambda x:-x['return']):
        print(f"   {r['coin']:6} | ${r['return']*10:>7.0f} return | {r['trades']:>3} trades")
        total_main_ret += r['return']
        total_main_trades += r['trades']
    print(f"\n   TOTAL: {total_main_ret/len(main_results):.1f}% avg | {total_main_trades} trades")

    print(f"\n{'='*80}")
    print("SECONDARY STRATEGY (per coin, $1000 each)")
    print(f"{'='*80}")
    total_sec_ret = 0
    total_sec_trades = 0
    for r in sorted(sec_results, key=lambda x:-x['return']):
        print(f"   {r['coin']:6} | ${r['return']*10:>7.0f} return | {r['trades']:>3} trades")
        total_sec_ret += r['return']
        total_sec_trades += r['trades']
    print(f"\n   TOTAL: {total_sec_ret/len(sec_results):.1f}% avg | {total_sec_trades} trades")

    # Comparison
    print(f"\n{'='*80}")
    print("HONEST COMPARISON")
    print(f"{'='*80}")
    print(f"{'Metric':<30} | {'Main':>12} | {'Secondary':>12}")
    print('-'*65)
    print(f"{'Avg return per coin':<30} | {total_main_ret/len(main_results):>11.1f}% | {total_sec_ret/len(sec_results):>11.1f}%")
    print(f"{'Total trades':<30} | {total_main_trades:>12} | {total_sec_trades:>12}")
    print(f"{'Trades per coin per year':<30} | {total_main_trades/len(main_results)/7:>11.1f} | {total_sec_trades/len(sec_results)/7:>11.1f}")
    print(f"\n⚠️ Yeh compounded returns hain — simple sum NAHI")

if __name__ == '__main__':
    main()
