# secondary_strategy_meaneversion.py
# Gap-filler strategy: Mean Reversion for bear/sideways markets
# Tests on zero-signal months + all months
# Combines with main strategy for full portfolio analysis

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
    """RSI calculation"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    close, high, low = df['c'], df['h'], df['l']
    df['rsi'] = calculate_rsi(close, 14)
    df['high_20d'] = high.rolling(20).max()
    df['drop_from_high'] = ((close - df['high_20d']) / df['high_20d']) * 100
    # Add main strategy indicators for comparison
    df['ema200'] = close.ewm(span=200, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    # ADX
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

def run_main_strategy(df):
    """Main strategy: EMA200 + MACD + ADX"""
    capital = 1000.0; cash = capital; pos = None; trades = []
    tp1, tp2 = 0.025, 0.05; dca1, dca2 = 0.02, 0.04; cb = 0.15
    for i in range(len(df)):
        row = df.iloc[i]; close, high, low = row['c'], row['h'], row['l']
        if pos:
            if low <= pos['start_price']*(1-cb):
                cash += pos['units']*close
                trades.append({'profit_pct':-cb*100,'date':df.index[i]}); pos=None; continue
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units']*0.5*pos['tp1_price']
                pos['units']*=0.5; pos['tp1_hit']=True; pos['sl']=pos['avg']
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units']*pos['tp2_price']
                trades.append({'profit_pct':tp2*100,'date':df.index[i]}); pos=None; continue
            if low <= pos['sl']:
                cash += pos['units']*pos['sl']
                profit = ((pos['sl']/pos['avg'])-1)*100
                trades.append({'profit_pct':profit,'date':df.index[i]}); pos=None; continue
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
                cost = capital*0.50; units = cost/(close*1.0015); cash -= cost
                pos = {'start_price':close,'units':units,'cost':cost,'initial_cost':cost,
                       'avg':close,'level':1,'tp1_hit':False,
                       'tp1_price':close*(1+tp1),'tp2_price':close*(1+tp2),
                       'sl':close*(1-cb)}
    return trades

def run_secondary_strategy(df):
    """Secondary: RSI oversold bounce OR drop from high"""
    capital = 500.0  # Smaller allocation for secondary
    cash = capital; pos = None; trades = []
    TP = 0.05; SL = 0.08; DCA_DROP = 0.05; DCA_ADD = 0.30
    
    for i in range(len(df)):
        row = df.iloc[i]; close, high, low = row['c'], row['h'], row['l']
        rsi = row['rsi']
        drop = row['drop_from_high']
        
        if pos:
            # TP
            if high >= pos['tp_price']:
                cash += pos['units']*pos['tp_price']
                trades.append({'profit_pct':TP*100,'date':df.index[i],'type':'TP'}); pos=None; continue
            # SL
            if low <= pos['sl']:
                cash += pos['units']*pos['sl']
                profit = ((pos['sl']/pos['avg'])-1)*100
                trades.append({'profit_pct':profit,'date':df.index[i],'type':'SL'}); pos=None; continue
            # RSI overbought exit
            if rsi > 60:
                cash += pos['units']*close
                profit = ((close/pos['avg'])-1)*100
                trades.append({'profit_pct':profit,'date':df.index[i],'type':'RSI'}); pos=None; continue
            # DCA
            if not pos['dca_done']:
                dca_price = pos['start_price']*(1-DCA_DROP)
                if low <= dca_price:
                    add = pos['initial_cost']*DCA_ADD
                    if cash >= add:
                        pos['units'] += add/close; pos['cost'] += add
                        pos['avg'] = pos['cost']/pos['units']
                        pos['tp_price'] = pos['avg']*(1+TP)
                        pos['dca_done'] = True; cash -= add
        else:
            # Entry: RSI oversold OR big drop from high
            oversold = rsi < 30
            big_drop = drop < -15
            if oversold or big_drop:
                cost = capital*0.50
                units = cost/(close*1.0015); cash -= cost
                pos = {'start_price':close,'units':units,'cost':cost,'initial_cost':cost,
                       'avg':close,'tp_price':close*(1+TP),'sl':close*(1-SL),
                       'dca_done':False}
    return trades

def main():
    print("="*100)
    print("SECONDARY STRATEGY — MEAN REVERSION (Gap Filler)")
    print("="*100)
    print("Testing on zero-signal months + all months\n")

    # Zero-signal months
    ZERO_MONTHS = [(2022, 5), (2022, 7)]

    # Accumulate
    main_all_trades = []
    sec_all_trades = []
    sec_zero_month_trades = []

    for coin in COINS_21:
        df = load_data(coin)
        if df is None: continue
        try:
            df_ind = add_indicators(df.copy())
        except: continue

        # Main strategy trades
        main_trades = run_main_strategy(df_ind)
        for t in main_trades:
            main_all_trades.append({'coin': coin, **t})

        # Secondary strategy trades
        sec_trades = run_secondary_strategy(df_ind)
        for t in sec_trades:
            sec_all_trades.append({'coin': coin, **t})
            # Check if in zero-month
            t_year = t['date'].year
            t_month = t['date'].month
            if (t_year, t_month) in ZERO_MONTHS:
                sec_zero_month_trades.append({'coin': coin, **t})

    print(f"📊 MAIN STRATEGY TRADES: {len(main_all_trades)}")
    print(f"📊 SECONDARY STRATEGY TRADES: {len(sec_all_trades)}")
    print(f"📊 SECONDARY IN ZERO-MONTHS: {len(sec_zero_month_trades)}\n")

    # Analyze main strategy by month
    if main_all_trades:
        df_main = pd.DataFrame(main_all_trades)
        df_main['entry_date'] = pd.to_datetime(df_main['date'])
        df_main['year'] = df_main['entry_date'].dt.year
        df_main['month'] = df_main['entry_date'].dt.month
        main_monthly = df_main.groupby(['year','month']).size()
        print("MAIN STRATEGY — Zero Months:")
        zero_found = []
        for y in range(2019, 2027):
            for m in range(1, 13):
                if (y, m) not in main_monthly.index:
                    zero_found.append((y, m))
        month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        for y, m in zero_found:
            print(f"   {y}-{month_names[m-1]}")

    # Analyze secondary strategy by month
    if sec_all_trades:
        df_sec = pd.DataFrame(sec_all_trades)
        df_sec['entry_date'] = pd.to_datetime(df_sec['date'])
        df_sec['year'] = df_sec['entry_date'].dt.year
        df_sec['month'] = df_sec['entry_date'].dt.month
        sec_monthly = df_sec.groupby(['year','month']).size()

        print("\nSECONDARY STRATEGY — Coverage in Main's Zero Months:")
        for y, m in zero_found:
            if (y, m) in sec_monthly.index:
                count = sec_monthly[(y, m)]
                print(f"   {y}-{month_names[m-1]}: {count} trades ✅ FILLED")
            else:
                print(f"   {y}-{month_names[m-1]}: 0 trades ❌ STILL GAP")

    # Zero-month detailed results
    print(f"\n{'='*100}")
    print("ZERO-MONTH DETAILED ANALYSIS (2022 May + Jul)")
    print(f"{'='*100}")
    if sec_zero_month_trades:
        df_zm = pd.DataFrame(sec_zero_month_trades)
        df_zm['entry_date'] = pd.to_datetime(df_zm['date'])
        df_zm['month'] = df_zm['entry_date'].dt.month
        for month in [5, 7]:
            month_trades = df_zm[df_zm['month'] == month]
            if len(month_trades) > 0:
                wins = (month_trades['profit_pct'] > 0).sum()
                total = len(month_trades)
                avg_profit = month_trades['profit_pct'].mean()
                print(f"\n2022-{month_names[month-1]}:")
                print(f"   Trades: {total}")
                print(f"   Wins: {wins} ({wins/total*100:.1f}%)")
                print(f"   Avg profit: {avg_profit:.2f}%")
                print(f"   Coins: {', '.join(month_trades['coin'].unique())}")
            else:
                print(f"\n2022-{month_names[month-1]}: 0 trades (secondary also silent)")

    # Overall stats
    print(f"\n{'='*100}")
    print("OVERALL STATS")
    print(f"{'='*100}")

    for label, trades in [('MAIN', main_all_trades), ('SECONDARY', sec_all_trades)]:
        if not trades: continue
        df = pd.DataFrame(trades)
        wins = (df['profit_pct'] > 0).sum()
        total = len(df)
        wr = wins/total*100 if total else 0
        avg = df['profit_pct'].mean()
        total_ret = df['profit_pct'].sum()
        print(f"\n{label} STRATEGY:")
        print(f"   Total trades: {total}")
        print(f"   Win rate: {wr:.1f}%")
        print(f"   Avg profit per trade: {avg:.2f}%")
        print(f"   Sum of returns: {total_ret:.1f}%")

    # Save
    if main_all_trades:
        pd.DataFrame(main_all_trades).to_csv(os.path.join(REPORT_DIR, 'main_strategy_trades.csv'), index=False)
    if sec_all_trades:
        pd.DataFrame(sec_all_trades).to_csv(os.path.join(REPORT_DIR, 'secondary_strategy_trades.csv'), index=False)
    print(f"\n📁 Saved: reports/main_strategy_trades.csv, secondary_strategy_trades.csv")

if __name__ == '__main__':
    main()
