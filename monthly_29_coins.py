import os
import numpy as np
import pandas as pd
import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
REPORT_DIR = os.path.join(ROOT, 'reports')

SLIPPAGE = 0.0015

COINS_29 = ['BTC','ETH','BNB','XRP','DOGE','LTC','BCH','LINK','AVAX','SOL',
            'ADA','DOT','SUI','HYPE','MATIC','SHIB','NEAR','APT','ARB','OP',
            'ICP','FIL','ATOM','IMX','INJ','STX','RNDR','GRT','FET']

def load_data(coin):
    path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
    df = pd.read_csv(path)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
    return df

def calculate_adx(high, low, close, period=14):
    plus_dm = high.diff().where(high.diff() > -low.diff(), 0).clip(lower=0)
    minus_dm = (-low.diff()).where(-low.diff() > high.diff(), 0).clip(lower=0)
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di  = 100 * (plus_dm.rolling(period).mean()  / (atr + 1e-9))
    minus_di = 100 * (minus_dm.rolling(period).mean() / (atr + 1e-9))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    return dx.rolling(period).mean()

def add_indicators(df):
    close, high, low = df['c'], df['h'], df['l']
    df['ema200'] = close.ewm(span=200, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    try:
        fvg = pyvsmc.detect_fvg(high=high.to_numpy(), low=low.to_numpy(), close=close.to_numpy())
        ob  = pyvsmc.detect_order_blocks(open_=df['o'].to_numpy(), high=high.to_numpy(), low=low.to_numpy(), close=close.to_numpy())
        df['smc_bull'] = (fvg.bullish & ~fvg.mitigated) | ob.bullish_ob
    except:
        df['smc_bull'] = True
    df['adx'] = calculate_adx(high, low, close)
    df['adx_ok'] = df['adx'] > 20
    return df.dropna()

def run_backtest(df):
    capital = 1000.0; cash = capital; pos = None; trades = []
    tp1_pct, tp2_pct = 0.025, 0.05
    dca1_drop, dca2_drop = 0.02, 0.04
    cb_pct = 0.15
    for i in range(250, len(df)):
        row = df.iloc[i]; close, high, low = row['c'], row['h'], row['l']
        candle_date = df.index[i]
        if pos:
            if low <= pos['start_price'] * (1 - cb_pct):
                cash += pos['units'] * close
                trades.append({'profit_pct': -cb_pct*100, 'entry_date':pos['entry_date']}); pos = None; continue
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units'] * 0.5 * pos['tp1_price']
                pos['units'] *= 0.5; pos['tp1_hit'] = True; pos['sl'] = pos['avg']
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units'] * pos['tp2_price']
                trades.append({'profit_pct': tp2_pct*100, 'entry_date':pos['entry_date']}); pos = None; continue
            if low <= pos['sl']:
                cash += pos['units'] * pos['sl']
                profit = ((pos['sl'] / pos['avg']) - 1) * 100
                trades.append({'profit_pct': profit, 'entry_date':pos['entry_date']}); pos = None; continue
            dca1 = pos['start_price'] * (1 - dca1_drop); dca2 = pos['start_price'] * (1 - dca2_drop)
            if pos['level'] == 1 and low <= dca1:
                add = pos['initial_cost'] * 0.30
                if cash >= add:
                    pos['units'] += add/close; pos['cost'] += add; pos['avg'] = pos['cost']/pos['units']
                    pos['tp1_price'] = pos['avg']*(1+tp1_pct); pos['tp2_price'] = pos['avg']*(1+tp2_pct)
                    pos['level'] = 2; cash -= add
            elif pos['level'] == 2 and low <= dca2:
                add = pos['initial_cost'] * 0.20
                if cash >= add:
                    pos['units'] += add/close; pos['cost'] += add; pos['avg'] = pos['cost']/pos['units']
                    pos['tp1_price'] = pos['avg']*(1+tp1_pct); pos['tp2_price'] = pos['avg']*(1+tp2_pct)
                    pos['level'] = 3; cash -= add
        else:
            if row['c'] > row['ema200'] and row['macd_bull'] and row['smc_bull'] and row['adx_ok']:
                cost = capital * 0.50; units = cost / (close * (1 + SLIPPAGE)); cash -= cost
                pos = {'start_price':close,'units':units,'cost':cost,'initial_cost':cost,
                       'avg':close,'level':1,'tp1_hit':False,
                       'tp1_price':close*(1+tp1_pct),'tp2_price':close*(1+tp2_pct),
                       'sl':close*(1-cb_pct),'entry_date':candle_date}
    return trades

def main():
    all_trades = []
    for coin in COINS_29:
        path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
        if not os.path.exists(path):
            continue
        try:
            df = add_indicators(load_data(coin))
            trades = run_backtest(df)
            for t in trades:
                t['coin'] = coin
                all_trades.append(t)
        except Exception as e:
            print(f"ERROR {coin}: {e}")

    if not all_trades:
        print("No trades.")
        return

    df_trades = pd.DataFrame(all_trades)
    df_trades['entry_date'] = pd.to_datetime(df_trades['entry_date'])
    df_trades['year'] = df_trades['entry_date'].dt.year
    df_trades['month'] = df_trades['entry_date'].dt.month

    pivot = df_trades.pivot_table(index='year', columns='month', values='profit_pct', aggfunc='sum', fill_value=0)
    pivot.columns = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    pivot['Year Total'] = pivot.sum(axis=1)
    pivot['Trades'] = df_trades.groupby('year').size()

    print("\n" + "="*150)
    print("HISTORICAL TRADING OVERVIEW — Net Return by Entry Month (29 Coins Combined)")
    print("="*150)
    print("Year   | " + " | ".join(f"{m:>6}" for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']) + " |  Year Tot | Trades")
    print("-"*150)
    for year in sorted(pivot.index):
        row = pivot.loc[year]
        cells = " | ".join(f"{row[m]:>6.1f}" for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])
        print(f"{int(year)}   | {cells} | {row['Year Total']:>8.1f}% | {int(row['Trades']):>6}")
    print("-"*150)
    grand_total = df_trades['profit_pct'].sum()
    print(f"Total trades: {len(df_trades)} | Grand Total: {grand_total:.1f}%")

    pivot.reset_index().to_csv(os.path.join(REPORT_DIR, 'monthly_return_29_coins.csv'), index=False)
    df_trades[['coin','entry_date','profit_pct']].to_csv(os.path.join(REPORT_DIR, 'all_trades_29_coins.csv'), index=False)
    print(f"\n📁 Saved:")
    print(f"   reports/monthly_return_29_coins.csv")
    print(f"   reports/all_trades_29_coins.csv")

if __name__ == '__main__':
    main()
