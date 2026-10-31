# final_verify_20_coins.py
# TON excluded. Baaki 20 coins ka full data verify + backtest + decision.
# Har coin ko RAKHNA ya CHHODNA ka faisla.

import os
import numpy as np
import pandas as pd
import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
REPORT_DIR = os.path.join(ROOT, 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)

SLIPPAGE = 0.0015
FEE = 0.0005

# TON excluded (data incomplete)
COINS = ['BTC','ETH','BNB','XRP','DOGE','LTC','BCH','LINK','AVAX','SOL',
         'ADA','DOT','SUI','HYPE','MATIC','SHIB','NEAR','APT','ARB','OP']

# Expected inception dates (Binance listing)
INCEPTION = {
    'BTC':  '2017-08-17', 'ETH':  '2017-08-17', 'BNB':  '2017-11-06',
    'XRP':  '2018-05-04', 'DOGE': '2019-07-05', 'LTC':  '2017-12-13',
    'BCH':  '2019-11-28', 'LINK': '2019-01-16', 'AVAX': '2020-09-22',
    'SOL':  '2020-08-11', 'ADA':  '2018-04-17', 'DOT':  '2020-08-18',
    'SUI':  '2023-05-03', 'HYPE': '2025-07-11', 'MATIC':'2019-04-26',
    'SHIB': '2021-05-10', 'NEAR': '2020-10-14', 'APT':  '2022-10-19',
    'ARB':  '2023-03-23', 'OP':   '2022-06-01',
}

def load_data(coin):
    path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
    df = pd.read_csv(path)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
    return df

def verify_data(df, coin):
    issues = []
    first = df.index[0]
    last = df.index[-1]
    expected_days = (last - first).days + 1
    actual_days = len(df)
    missing_pct = ((expected_days - actual_days) / expected_days) * 100

    inc = INCEPTION.get(coin)
    if inc:
        diff = (first - pd.Timestamp(inc)).days
        if abs(diff) > 14:
            issues.append(f"first {first.date()} vs inception {inc} (diff {diff}d)")

    if missing_pct > 2:
        issues.append(f"missing {missing_pct:.1f}%")

    dup = df.index.duplicated().sum()
    if dup > 0:
        issues.append(f"{dup} duplicates")

    if (df[['o','h','l','c']] <= 0).any().any():
        issues.append("zero/negative price")

    bad_ohlc = ((df['h'] < df['l']) | (df['c'] > df['h']) | (df['c'] < df['l'])).sum()
    if bad_ohlc > 0:
        issues.append(f"{bad_ohlc} bad OHLC")

    return {
        'coin': coin, 'first': first.strftime('%Y-%m-%d'), 'last': last.strftime('%Y-%m-%d'),
        'days': expected_days, 'candles': actual_days, 'missing_pct': round(missing_pct,2),
        'issues': issues, 'status': 'OK' if not issues else 'WARN'
    }

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

def decide(return_pct, wr, pf, dd, trades):
    if trades < 15: return 'DROP', f'low sample ({trades})'
    if return_pct < 0: return 'DROP', f'negative ({return_pct:.1f}%)'
    if wr < 85: return 'DROP', f'low WR ({wr:.1f}%)'
    if pf < 1.5: return 'DROP', f'low PF ({pf:.2f})'
    if dd < -25: return 'DROP', f'high DD ({dd:.1f}%)'
    rating = 'EXCELLENT' if (return_pct > 50 and pf > 2.5) else 'GOOD' if (return_pct > 25 and pf > 2) else 'ACCEPTABLE'
    return 'KEEP', f'{rating}'

def main():
    print("="*115)
    print("STEP 1: DATA VERIFICATION (20 coins, TON excluded)")
    print("="*115)
    checks = []; loaded = {}
    for coin in COINS:
        try:
            df = load_data(coin)
            c = verify_data(df, coin)
            checks.append(c); loaded[coin] = df
            status = "✅" if c['status']=='OK' else "⚠️"
            issue_str = '; '.join(c['issues']) if c['issues'] else 'clean'
            print(f"{status} {coin:6} | {c['first']} → {c['last']} | {c['candles']:5} candles | missing {c['missing_pct']:5.2f}% | {issue_str}")
        except Exception as e:
            print(f"❌ {coin:6} | ERROR: {e}")
            loaded[coin] = None

    print("\n" + "="*115)
    print("STEP 2: STRATEGY BACKTEST (Full Data)")
    print("="*115)
    print(f"{'Coin':<6} | {'Return':>8} | {'WinRate':>8} | {'PF':>5} | {'MaxDD':>7} | {'Trades':>6} | {'Decision':<10} | Reason")
    print('-'*115)
    results = []
    for coin in COINS:
        if loaded[coin] is None or len(loaded[coin]) < 260:
            print(f"{coin:<6} | {'-':>8} | {'-':>8} | {'-':>5} | {'-':>7} | {'-':>6} | {'SKIP':<10} | insufficient data")
            continue
        try:
            df = add_indicators(loaded[coin].copy())
            ret, wr, pf, dd, total = run_backtest(df)
            decision, reason = decide(ret, wr, pf, dd, total)
            idx = [c['coin'] for c in checks].index(coin)
            results.append({'Coin':coin,'Return':ret,'WinRate':wr,'PF':pf,'MaxDD':dd,'Trades':total,
                            'Decision':decision,'Reason':reason,'First':checks[idx]['first'],'Last':checks[idx]['last']})
            print(f"{coin:<6} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {total:>6} | {decision:<10} | {reason}")
        except Exception as e:
            print(f"{coin:<6} | ERROR: {str(e)[:60]}")
    print('-'*115)

    print("\n" + "="*115)
    print("STEP 3: FINAL DECISION")
    print("="*115)
    keep = sorted([r for r in results if r['Decision']=='KEEP'], key=lambda x:-x['Return'])
    drop = sorted([r for r in results if r['Decision']=='DROP'], key=lambda x:-x['Return'])
    print(f"\n✅ KEEP ({len(keep)} coins):")
    for r in keep:
        print(f"   {r['Coin']:6} | Return {r['Return']:>6.1f}% | WR {r['WinRate']:>5.1f}% | PF {r['PF']:>5.2f} | DD {r['MaxDD']:>6.1f}% | {r['Trades']:>4} trades")
    print(f"\n❌ DROP ({len(drop)} coins):")
    for r in drop:
        print(f"   {r['Coin']:6} | Return {r['Return']:>6.1f}% | Reason: {r['Reason']}")

    if results:
        pd.DataFrame(results).to_csv(os.path.join(REPORT_DIR,'final_decision_20_coins.csv'), index=False)
        print(f"\n📁 Saved: reports/final_decision_20_coins.csv")

if __name__ == '__main__':
    main()
