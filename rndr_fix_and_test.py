# rndr_fix_and_test_new_coins.py
# 1) RNDR fix: RNDR (2021-2024) + RENDER (2024-2026) merge
# 2) Test 9 new coins with same strategy
# 3) Decision: KEEP or DROP

import os, time
import numpy as np
import pandas as pd
import pyvsmc
import ccxt

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
REPORT_DIR = os.path.join(ROOT, 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)

SLIPPAGE = 0.0015
FEE = 0.0005

NEW_COINS = ['ICP','FIL','ATOM','IMX','INJ','STX','RNDR','GRT','FET']

INCEPTION = {
    'ICP':'2021-05-11','FIL':'2020-10-15','ATOM':'2019-04-29',
    'IMX':'2022-01-10','INJ':'2020-10-21','STX':'2019-10-25',
    'RNDR':'2021-11-27','GRT':'2020-12-17','FET':'2019-02-28',
}

def get_exchange(name):
    try:
        cls = getattr(ccxt, name)
        return cls({'enableRateLimit': True, 'timeout': 30000})
    except:
        return None

def fetch_full(ex, symbol, since_ms):
    rows = []
    cursor = since_ms
    retries = 0
    while True:
        try:
            batch = ex.fetch_ohlcv(symbol, timeframe='1d', since=cursor, limit=1000)
            retries = 0
        except:
            retries += 1
            if retries >= 4: return []
            time.sleep(2 * retries); continue
        if not batch: break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts <= cursor: break
        cursor = last_ts + 1
        time.sleep(ex.rateLimit / 1000.0)
        if len(batch) < 1000: break
    return rows

def fix_rndr():
    """Download RENDER/USDT and merge with existing RNDR data"""
    print("\n[RNDR FIX] Downloading RENDER/USDT from Binance/Bybit/OKX...")
    all_rows = []
    for ex_name in ['binance','bybit','okx','kucoin','gate','bitget']:
        ex = get_exchange(ex_name)
        if ex is None: continue
        try:
            ex.load_markets()
            for sym in ['RENDER/USDT','RNDR/USDT']:
                if sym not in ex.markets: continue
                since_ms = int(pd.Timestamp('2000-01-01').timestamp() * 1000)
                rows = fetch_full(ex, sym, since_ms)
                if rows and len(rows) > 50:
                    print(f"  ✅ {ex_name} {sym}: {len(rows)} candles")
                    all_rows.extend(rows)
                    break
            if all_rows:
                break
        except Exception as e:
            print(f"  ❌ {ex_name}: {str(e)[:60]}")

    if not all_rows:
        print("  ❌ RENDER fetch failed — RNDR data stays as-is")
        return False

    # Load existing RNDR data
    rndr_path = os.path.join(DATA_DIR, 'RNDRUSDT_1d_ALL.csv')
    existing = pd.read_csv(rndr_path)
    existing_rows = existing[['open_time','open','high','low','close','volume']].values.tolist()

    # Merge
    merged = existing_rows + all_rows
    df = pd.DataFrame(merged, columns=['open_time','open','high','low','close','volume'])
    df = df.drop_duplicates(subset='open_time').sort_values('open_time').reset_index(drop=True)
    df.to_csv(rndr_path, index=False)
    t0 = pd.to_datetime(df['open_time'].iloc[0], unit='ms').date()
    t1 = pd.to_datetime(df['open_time'].iloc[-1], unit='ms').date()
    print(f"  💾 RNDR merged: {len(df)} candles ({t0} → {t1})")
    return True

def load_data(coin):
    path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
    df = pd.read_csv(path)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
    return df

def verify_data(df, coin):
    issues = []
    first, last = df.index[0], df.index[-1]
    expected = (last - first).days + 1
    actual = len(df)
    missing = ((expected - actual) / expected) * 100
    inc = INCEPTION.get(coin)
    if inc:
        diff = (first - pd.Timestamp(inc)).days
        if abs(diff) > 14:
            issues.append(f"first {first.date()} vs {inc} (diff {diff}d)")
    if missing > 2:
        issues.append(f"missing {missing:.1f}%")
    dup = df.index.duplicated().sum()
    if dup > 0: issues.append(f"{dup} dup")
    return {'coin':coin,'first':first.strftime('%Y-%m-%d'),'last':last.strftime('%Y-%m-%d'),
            'candles':actual,'missing_pct':round(missing,2),'issues':issues,
            'status':'OK' if not issues else 'WARN'}

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
        if pos:
            if low <= pos['start_price'] * (1 - cb_pct):
                cash += pos['units'] * close
                trades.append({'profit_pct': -cb_pct*100, 'type':'CB'}); pos = None; equity.append(cash); continue
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units'] * 0.5 * pos['tp1_price']
                pos['units'] *= 0.5; pos['tp1_hit'] = True; pos['sl'] = pos['avg']
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units'] * pos['tp2_price']
                trades.append({'profit_pct': tp2_pct*100, 'type':'TP2'}); pos = None; equity.append(cash); continue
            if low <= pos['sl']:
                cash += pos['units'] * pos['sl']
                profit = ((pos['sl'] / pos['avg']) - 1) * 100
                trades.append({'profit_pct': profit, 'type':'SL' if not pos['tp1_hit'] else 'BE'}); pos = None; equity.append(cash); continue
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
                       'sl':close*(1-cb_pct)}
        equity.append(cash + (pos['units'] * close if pos else 0))
    if len(equity) == 0: return 0,0,0,0,0
    eq_arr = np.array(equity); peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    ret = (eq_arr[-1] - capital) / capital * 100
    wins = sum(1 for t in trades if t['profit_pct'] >= 0); total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gw / gl) if gl > 0 else (99.9 if gw > 0 else 0)
    return ret, wr, pf, dd, total

def decide(ret, wr, pf, dd, trades):
    if trades < 15: return 'DROP', f'low sample ({trades})'
    if ret < 0: return 'DROP', f'negative ({ret:.1f}%)'
    if wr < 85: return 'DROP', f'low WR ({wr:.1f}%)'
    if pf < 1.5: return 'DROP', f'low PF ({pf:.2f})'
    if dd < -25: return 'DROP', f'high DD ({dd:.1f}%)'
    rating = 'EXCELLENT' if (ret > 50 and pf > 2.5) else 'GOOD' if (ret > 25 and pf > 2) else 'ACCEPTABLE'
    return 'KEEP', rating

def main():
    # Step 0: Fix RNDR
    print("="*90)
    print("STEP 0: RNDR FIX (RNDR + RENDER merge)")
    print("="*90)
    fix_rndr()

    # Step 1: Verify
    print("\n" + "="*90)
    print("STEP 1: DATA VERIFICATION")
    print("="*90)
    checks = []; loaded = {}
    for coin in NEW_COINS:
        try:
            df = load_data(coin)
            c = verify_data(df, coin)
            checks.append(c); loaded[coin] = df
            s = "✅" if c['status']=='OK' else "⚠️"
            iss = '; '.join(c['issues']) if c['issues'] else 'clean'
            print(f"{s} {coin:5} | {c['first']} → {c['last']} | {c['candles']:5}c | miss {c['missing_pct']:5.2f}% | {iss}")
        except Exception as e:
            print(f"❌ {coin:5} | ERROR: {e}")
            loaded[coin] = None

    # Step 2: Backtest
    print("\n" + "="*90)
    print("STEP 2: BACKTEST NEW 9 COINS")
    print("="*90)
    print(f"{'Coin':<6} | {'Return':>8} | {'WinRate':>8} | {'PF':>6} | {'MaxDD':>7} | {'Trades':>6} | {'Decision':<10} | Reason")
    print('-'*110)
    results = []
    for coin in NEW_COINS:
        if loaded[coin] is None or len(loaded[coin]) < 260:
            print(f"{coin:<6} | {'-':>8} | {'-':>8} | {'-':>6} | {'-':>7} | {'-':>6} | {'SKIP':<10} | insufficient")
            continue
        try:
            df = add_indicators(loaded[coin].copy())
            ret, wr, pf, dd, total = run_backtest(df)
            decision, reason = decide(ret, wr, pf, dd, total)
            idx = [c['coin'] for c in checks].index(coin)
            results.append({'Coin':coin,'Return':ret,'WinRate':wr,'PF':pf,'MaxDD':dd,'Trades':total,
                            'Decision':decision,'Reason':reason,
                            'First':checks[idx]['first'],'Last':checks[idx]['last']})
            print(f"{coin:<6} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>6.2f} | {dd:>6.1f}% | {total:>6} | {decision:<10} | {reason}")
        except Exception as e:
            print(f"{coin:<6} | ERROR: {str(e)[:50]}")
    print('-'*110)

    # Step 3: Final decision
    print("\n" + "="*90)
    print("STEP 3: FINAL DECISION — NEW 9 COINS")
    print("="*90)
    keep = sorted([r for r in results if r['Decision']=='KEEP'], key=lambda x:-x['Return'])
    drop = sorted([r for r in results if r['Decision']=='DROP'], key=lambda x:-x['Return'])
    print(f"\n✅ KEEP ({len(keep)}):")
    for r in keep:
        print(f"   {r['Coin']:6} | Return {r['Return']:>6.1f}% | WR {r['WinRate']:>5.1f}% | PF {r['PF']:>5.2f} | DD {r['MaxDD']:>6.1f}% | {r['Trades']:>3} trades")
    print(f"\n❌ DROP ({len(drop)}):")
    for r in drop:
        print(f"   {r['Coin']:6} | Return {r['Return']:>6.1f}% | Reason: {r['Reason']}")

    if results:
        pd.DataFrame(results).to_csv(os.path.join(REPORT_DIR, 'final_decision_new_9_coins.csv'), index=False)
        print(f"\n📁 Saved: reports/final_decision_new_9_coins.csv")

if __name__ == '__main__':
    main()
