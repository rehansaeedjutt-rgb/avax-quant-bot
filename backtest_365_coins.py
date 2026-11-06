# backtest_365_coins.py
# Honest backtest — NO SMC (no look-ahead bias)
# 365 coins from data_bulk/ + data/
# Quality filter: return > 0, WR >= 45%, PF >= 1.3, DD >= -35%, trades >= 15
# Vectorized where possible for speed

import os
import numpy as np
import pandas as pd
from datetime import datetime

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
DATA_BULK = os.path.join(ROOT, 'data_bulk')
REPORT_DIR = os.path.join(ROOT, 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)

SLIPPAGE = 0.0015

def load_data(coin):
    """Load from data_bulk first, then data/"""
    for base in [DATA_BULK, DATA_DIR]:
        for pattern in [f'{coin}USDT_1d.csv', f'{coin}USDT_1d_ALL.csv']:
            path = os.path.join(base, pattern)
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    if len(df) < 260:
                        return None
                    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
                    df = df.set_index('open_time').sort_index()
                    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
                    return df
                except:
                    continue
    return None

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
    """EMA200 + MACD + ADX only. NO SMC. No look-ahead."""
    close, high, low = df['c'], df['h'], df['l']
    df['ema200'] = close.ewm(span=200, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    df['adx'] = calculate_adx(high, low, close)
    df['adx_ok'] = df['adx'] > 20
    return df.dropna()

def run_backtest(df):
    capital = 1000.0
    cash = capital
    pos = None
    trades = []
    equity = []
    tp1_pct, tp2_pct = 0.025, 0.05
    dca1_drop, dca2_drop = 0.02, 0.04
    cb_pct = 0.15

    for i in range(250, len(df)):
        row = df.iloc[i]
        close, high, low = row['c'], row['h'], row['l']
        if pos:
            if low <= pos['start_price'] * (1 - cb_pct):
                cash += pos['units'] * close
                trades.append({'profit_pct': -cb_pct*100, 'type': 'CB'})
                pos = None; equity.append(cash); continue
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units'] * 0.5 * pos['tp1_price']
                pos['units'] *= 0.5; pos['tp1_hit'] = True; pos['sl'] = pos['avg']
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units'] * pos['tp2_price']
                trades.append({'profit_pct': tp2_pct*100, 'type': 'TP2'})
                pos = None; equity.append(cash); continue
            if low <= pos['sl']:
                cash += pos['units'] * pos['sl']
                profit = ((pos['sl'] / pos['avg']) - 1) * 100
                trades.append({'profit_pct': profit, 'type': 'SL' if not pos['tp1_hit'] else 'BE'})
                pos = None; equity.append(cash); continue
            dca1 = pos['start_price'] * (1 - dca1_drop)
            dca2 = pos['start_price'] * (1 - dca2_drop)
            if pos['level'] == 1 and low <= dca1:
                add = pos['initial_cost'] * 0.30
                if cash >= add:
                    pos['units'] += add/close; pos['cost'] += add
                    pos['avg'] = pos['cost']/pos['units']
                    pos['tp1_price'] = pos['avg']*(1+tp1_pct)
                    pos['tp2_price'] = pos['avg']*(1+tp2_pct)
                    pos['level'] = 2; cash -= add
            elif pos['level'] == 2 and low <= dca2:
                add = pos['initial_cost'] * 0.20
                if cash >= add:
                    pos['units'] += add/close; pos['cost'] += add
                    pos['avg'] = pos['cost']/pos['units']
                    pos['tp1_price'] = pos['avg']*(1+tp1_pct)
                    pos['tp2_price'] = pos['avg']*(1+tp2_pct)
                    pos['level'] = 3; cash -= add
        else:
            if row['c'] > row['ema200'] and row['macd_bull'] and row['adx_ok']:
                cost = capital * 0.50
                units = cost / (close * (1 + SLIPPAGE))
                cash -= cost
                pos = {'start_price':close,'units':units,'cost':cost,'initial_cost':cost,
                       'avg':close,'level':1,'tp1_hit':False,
                       'tp1_price':close*(1+tp1_pct),'tp2_price':close*(1+tp2_pct),
                       'sl':close*(1-cb_pct)}
        equity.append(cash + (pos['units'] * close if pos else 0))

    if len(equity) == 0:
        return None
    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    ret = (eq_arr[-1] - capital) / capital * 100
    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    be_count = sum(1 for t in trades if t['profit_pct'] == 0)
    losses = sum(1 for t in trades if t['profit_pct'] < 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gw / gl) if gl > 0 else (99.9 if gw > 0 else 0)
    return {'return':round(ret,1),'win_rate':round(wr,1),'pf':round(pf,2),
            'max_dd':round(dd,1),'trades':total,'wins':wins,'be':be_count,'losses':losses,
            'candles':len(df),'first':str(df.index[0].date()),'last':str(df.index[-1].date())}

def decide(ret, wr, pf, dd, trades):
    if trades < 15: return 'DROP', f'low sample ({trades})'
    if ret < 0: return 'DROP', f'negative ({ret:.1f}%)'
    if wr < 45: return 'DROP', f'low WR ({wr:.1f}%)'
    if pf < 1.3: return 'DROP', f'low PF ({pf:.2f})'
    if dd < -35: return 'DROP', f'high DD ({dd:.1f}%)'
    rating = 'EXCELLENT' if (ret > 100 and pf > 2.0) else 'GOOD' if (ret > 50 and pf > 1.5) else 'ACCEPTABLE'
    return 'KEEP', rating

def main():
    # Find all coins
    coin_files = set()
    for base in [DATA_BULK, DATA_DIR]:
        if not os.path.exists(base): continue
        for f in os.listdir(base):
            if f.endswith('.csv'):
                coin = f.replace('USDT_1d_ALL.csv','').replace('USDT_1d.csv','')
                coin_files.add(coin)

    print("="*115)
    print(f"HONEST BACKTEST — {len(coin_files)} COINS (NO SMC)")
    print("="*115)

    results = []
    errors = []
    start_time = datetime.now()

    for i, coin in enumerate(sorted(coin_files), 1):
        try:
            df = load_data(coin)
            if df is None:
                continue
            df_ind = add_indicators(df.copy())
            if len(df_ind) < 260:
                continue
            r = run_backtest(df_ind)
            if r is None:
                continue
            decision, reason = decide(r['return'], r['win_rate'], r['pf'], r['max_dd'], r['trades'])
            results.append({'Coin':coin, **r, 'Decision':decision, 'Reason':reason})
        except Exception as e:
            errors.append((coin, str(e)[:50]))

        if i % 50 == 0:
            el = (datetime.now() - start_time).total_seconds()
            print(f"  [{i}/{len(coin_files)}] tested={len(results)} errors={len(errors)} | {el/60:.0f}min elapsed")

    # Sort by return
    results_sorted = sorted(results, key=lambda x: -x['return'])

    print(f"\n{'Coin':<8} | {'Return':>8} | {'WR':>6} | {'PF':>5} | {'MaxDD':>7} | {'Trades':>6} | {'W/BE/L':>10} | {'Decision':<10} | Reason")
    print('-'*135)
    for r in results_sorted:
        print(f"{r['Coin']:<8} | {r['return']:>7.1f}% | {r['win_rate']:>5.1f}% | {r['pf']:>5.2f} | "
              f"{r['max_dd']:>6.1f}% | {r['trades']:>6} | {r['wins']}/{r['be']}/{r['losses']:>3} | "
              f"{r['Decision']:<10} | {r['Reason']}")
    print('-'*135)

    keep = [r for r in results if r['Decision']=='KEEP']
    drop = [r for r in results if r['Decision']=='DROP']

    print(f"\n{'='*80}")
    print(f"FINAL RESULTS")
    print(f"{'='*80}")
    print(f"  Tested:  {len(results)} coins")
    print(f"  KEEP:    {len(keep)} coins")
    print(f"  DROP:    {len(drop)} coins")
    print(f"  Errors:  {len(errors)}")
    print(f"  Time:    {(datetime.now()-start_time).total_seconds()/60:.1f} min")

    if keep:
        print(f"\n✅ TOP 30 KEEP (by return):")
        print(f"{'Rank':<5} | {'Coin':<8} | {'Return':>8} | {'WR':>6} | {'PF':>5} | {'DD':>7} | {'Trades':>6} | Rating")
        print('-'*80)
        for i, r in enumerate(sorted(keep, key=lambda x:-x['return'])[:30], 1):
            print(f"{i:<5} | {r['Coin']:<8} | {r['return']:>7.1f}% | {r['win_rate']:>5.1f}% | "
                  f"{r['pf']:>5.2f} | {r['max_dd']:>6.1f}% | {r['trades']:>6} | {r['Reason']}")

    # Save
    pd.DataFrame(results).to_csv(os.path.join(REPORT_DIR, 'BACKTEST_365_HONEST.csv'), index=False)
    pd.DataFrame(keep).to_csv(os.path.join(REPORT_DIR, 'KEEP_365.csv'), index=False)
    print(f"\n📁 Saved:")
    print(f"   reports/BACKTEST_365_HONEST.csv ({len(results)} coins)")
    print(f"   reports/KEEP_365.csv ({len(keep)} coins)")

if __name__ == '__main__':
    main()
