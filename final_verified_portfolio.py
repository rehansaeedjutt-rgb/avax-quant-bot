# final_verified_portfolio_v2.py
# Fixed: trades mein dates save karta hai, CSV properly generate hoti hai

import os
import numpy as np
import pandas as pd
import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
REPORT_DIR = os.path.join(ROOT, 'reports')

SLIPPAGE = 0.0015

TIER1_CORE = ['BTC','ETH','BNB','LINK','LTC','ADA','SOL','AVAX','DOT','NEAR']
TIER2_GROWTH = ['FET','INJ','GRT','STX','OP','APT','SUI','FIL']
TIER3_WATCHLIST = ['HYPE','ICP']
VERIFIED = TIER1_CORE + TIER2_GROWTH + TIER3_WATCHLIST

REMOVED = {
    'TON':  'Data incomplete (stopped 2026-06-30)',
    'MATIC':'POL migration, delisted',
    'RNDR': 'RENDER migration, symbol change',
    'SHIB': 'Meme coin, no real utility',
    'DOGE': 'Meme coin, negative return',
    'BCH':  'Bitcoin fork, declining adoption',
    'XRP':  'SEC lawsuits, regulatory risk',
    'ATOM': 'Declining ecosystem, low WR',
    'ARB':  'Low PF (1.33), small sample',
}

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
    capital = 1000.0; cash = capital; pos = None; trades = []; equity = []
    tp1_pct, tp2_pct = 0.025, 0.05
    dca1_drop, dca2_drop = 0.02, 0.04
    cb_pct = 0.15
    for i in range(250, len(df)):
        row = df.iloc[i]; close, high, low = row['c'], row['h'], row['l']
        candle_date = df.index[i]
        if pos:
            if low <= pos['start_price'] * (1 - cb_pct):
                cash += pos['units'] * close
                trades.append({'profit_pct': -cb_pct*100, 'type':'CB',
                               'entry_date':pos['entry_date'],'entry_price':pos['entry_price'],
                               'exit_date':candle_date,'exit_price':close}); pos = None; equity.append(cash); continue
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units'] * 0.5 * pos['tp1_price']
                pos['units'] *= 0.5; pos['tp1_hit'] = True; pos['sl'] = pos['avg']
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units'] * pos['tp2_price']
                trades.append({'profit_pct': tp2_pct*100, 'type':'TP2',
                               'entry_date':pos['entry_date'],'entry_price':pos['entry_price'],
                               'exit_date':candle_date,'exit_price':pos['tp2_price']}); pos = None; equity.append(cash); continue
            if low <= pos['sl']:
                cash += pos['units'] * pos['sl']
                profit = ((pos['sl'] / pos['avg']) - 1) * 100
                trades.append({'profit_pct': profit, 'type':'SL' if not pos['tp1_hit'] else 'BE',
                               'entry_date':pos['entry_date'],'entry_price':pos['entry_price'],
                               'exit_date':candle_date,'exit_price':pos['sl']}); pos = None; equity.append(cash); continue
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
                       'sl':close*(1-cb_pct),'entry_date':candle_date,'entry_price':close}
        equity.append(cash + (pos['units'] * close if pos else 0))
    if len(equity) == 0: return 0,0,0,0,0,[]
    eq_arr = np.array(equity); peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    ret = (eq_arr[-1] - capital) / capital * 100
    wins = sum(1 for t in trades if t['profit_pct'] >= 0); total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gw / gl) if gl > 0 else (99.9 if gw > 0 else 0)
    return ret, wr, pf, dd, total, trades

def main():
    print("="*100)
    print("FINAL VERIFIED PORTFOLIO — 18 COINS (v2 with CSV fix)")
    print("="*100)

    results = []
    all_trades = []

    for coin in VERIFIED:
        try:
            df = add_indicators(load_data(coin))
            ret, wr, pf, dd, total, trades = run_backtest(df)
            tier = 'T1-Core' if coin in TIER1_CORE else 'T2-Growth' if coin in TIER2_GROWTH else 'T3-Watchlist'
            results.append({'Coin':coin, 'Tier':tier, 'Return':round(ret,1), 'WinRate':round(wr,1),
                            'PF':round(pf,2), 'MaxDD':round(dd,1), 'Trades':total})
            for t in trades:
                t['coin'] = coin; t['tier'] = tier
                all_trades.append(t)
        except Exception as e:
            print(f"ERROR {coin}: {e}")

    print(f"\n{'Coin':<6} | {'Tier':<12} | {'Return':>8} | {'WinRate':>8} | {'PF':>5} | {'MaxDD':>7} | {'Trades':>6}")
    print('-'*100)
    for r in sorted(results, key=lambda x:-x['Return']):
        print(f"{r['Coin']:<6} | {r['Tier']:<12} | {r['Return']:>7.1f}% | {r['WinRate']:>7.1f}% | {r['PF']:>5.2f} | {r['MaxDD']:>6.1f}% | {r['Trades']:>6}")
    print('-'*100)

    for tier_name, tier_coins in [('TIER 1 (CORE - Free)', TIER1_CORE),
                                   ('TIER 2 (GROWTH - VIP)', TIER2_GROWTH),
                                   ('TIER 3 (WATCHLIST)', TIER3_WATCHLIST)]:
        tier_results = [r for r in results if r['Coin'] in tier_coins]
        if not tier_results: continue
        avg_ret = sum(r['Return'] for r in tier_results) / len(tier_results)
        total_trades = sum(r['Trades'] for r in tier_results)
        print(f"\n{tier_name} ({len(tier_results)} coins, {total_trades} trades, avg return {avg_ret:.1f}%)")
        print(f"   {', '.join([r['Coin'] for r in tier_results])}")

    print(f"\n" + "="*100)
    print(f"REMOVED COINS ({len(REMOVED)}) + Exact Reasons")
    print("="*100)
    for coin, reason in REMOVED.items():
        print(f"  ❌ {coin:6} — {reason}")

    # Save CSVs
    pd.DataFrame(results).to_csv(os.path.join(REPORT_DIR, 'final_verified_portfolio.csv'), index=False)
    if all_trades:
        df_t = pd.DataFrame(all_trades)
        df_t = df_t.sort_values(['tier','coin','entry_date'])
        df_t.to_csv(os.path.join(REPORT_DIR, 'verified_trades.csv'), index=False)
        print(f"\n📁 Saved:")
        print(f"   reports/final_verified_portfolio.csv ({len(results)} coins)")
        print(f"   reports/verified_trades.csv ({len(all_trades)} trades)")
    else:
        print(f"\n📁 Saved: reports/final_verified_portfolio.csv")

if __name__ == '__main__':
    main()
