# backtest_21_coins.py
# Same strategy as verify_full_backtest.py, but for 21 coins
# Uses the *_ALL.csv files downloaded earlier

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

COINS = ['BTC','ETH','BNB','XRP','DOGE','LTC','BCH','LINK','AVAX','SOL',
         'ADA','DOT','SUI','HYPE','MATIC','TON','SHIB','NEAR','APT','ARB','OP']

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
        candle_date = df.index[i]

        if pos:
            if low <= pos['start_price'] * (1 - cb_pct):
                cash += pos['units'] * close
                trades.append({'profit_pct': -cb_pct*100, 'type': 'CB',
                               'entry_date': pos['entry_date'], 'entry_price': pos['entry_price'],
                               'exit_date': candle_date, 'exit_price': close})
                pos = None
                equity.append(cash)
                continue

            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units'] * 0.5 * pos['tp1_price']
                pos['units'] *= 0.5
                pos['tp1_hit'] = True
                pos['sl'] = pos['avg']

            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units'] * pos['tp2_price']
                trades.append({'profit_pct': tp2_pct*100, 'type': 'TP2',
                               'entry_date': pos['entry_date'], 'entry_price': pos['entry_price'],
                               'exit_date': candle_date, 'exit_price': pos['tp2_price']})
                pos = None
                equity.append(cash)
                continue

            if low <= pos['sl']:
                cash += pos['units'] * pos['sl']
                profit = ((pos['sl'] / pos['avg']) - 1) * 100
                trades.append({'profit_pct': profit,
                               'type': 'SL' if not pos['tp1_hit'] else 'BE',
                               'entry_date': pos['entry_date'], 'entry_price': pos['entry_price'],
                               'exit_date': candle_date, 'exit_price': pos['sl']})
                pos = None
                equity.append(cash)
                continue

            dca1_price = pos['start_price'] * (1 - dca1_drop)
            dca2_price = pos['start_price'] * (1 - dca2_drop)
            if pos['level'] == 1 and low <= dca1_price:
                add_cost = pos['initial_cost'] * 0.30
                if cash >= add_cost:
                    pos['units'] += add_cost / close
                    pos['cost']  += add_cost
                    pos['avg']    = pos['cost'] / pos['units']
                    pos['tp1_price'] = pos['avg'] * (1 + tp1_pct)
                    pos['tp2_price'] = pos['avg'] * (1 + tp2_pct)
                    pos['level'] = 2
                    cash -= add_cost
            elif pos['level'] == 2 and low <= dca2_price:
                add_cost = pos['initial_cost'] * 0.20
                if cash >= add_cost:
                    pos['units'] += add_cost / close
                    pos['cost']  += add_cost
                    pos['avg']    = pos['cost'] / pos['units']
                    pos['tp1_price'] = pos['avg'] * (1 + tp1_pct)
                    pos['tp2_price'] = pos['avg'] * (1 + tp2_pct)
                    pos['level'] = 3
                    cash -= add_cost
        else:
            base_cond = row['c'] > row['ema200'] and row['macd_bull'] and row['smc_bull'] and row['adx_ok']
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
                    'sl': close * (1 - cb_pct),
                    'entry_date': candle_date, 'entry_price': close,
                }

        equity.append(cash + (pos['units'] * close if pos else 0))

    if len(equity) == 0:
        return 0, 0, 0, 0, 0, []

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    ret = (eq_arr[-1] - capital) / capital * 100
    wins = sum(1 for t in trades if t['profit_pct'] >= 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gw / gl) if gl > 0 else (99.9 if gw > 0 else 0)
    return ret, wr, pf, dd, total, trades

def main():
    results = []
    all_trades = []

    for coin in COINS:
        path = os.path.join(DATA_DIR, f'{coin}USDT_1d_ALL.csv')
        if not os.path.exists(path):
            print(f"SKIP {coin}: missing data")
            continue
        try:
            df = add_indicators(load_data(coin))
        except Exception as e:
            print(f"ERROR {coin}: {str(e)[:80]}")
            continue
        if len(df) < 260:
            print(f"SKIP {coin}: only {len(df)} candles (need 260+)")
            continue

        ret, wr, pf, dd, total, trades = run_backtest(df)
        results.append({
            'Coin': coin, 'Return %': round(ret, 1), 'Win Rate %': round(wr, 1),
            'PF': round(pf, 2), 'Max DD %': round(dd, 1), 'Trades': total,
            'First Trade': trades[0]['entry_date'].strftime('%Y-%m-%d') if trades else '-',
            'Last Trade':  trades[-1]['entry_date'].strftime('%Y-%m-%d') if trades else '-',
        })
        for t in trades:
            t['coin'] = coin
            t['hold_days'] = (t['exit_date'] - t['entry_date']).days
            all_trades.append(t)

    print("\n" + "="*110)
    print("BACKTEST RESULTS — 21 COINS (Original Strategy)")
    print("="*110)
    print(f"{'Coin':<6} | {'Return':>8} | {'WinRate':>8} | {'PF':>5} | {'MaxDD':>7} | {'Trades':>6} | {'First':>10} | {'Last':>10}")
    print('-'*110)
    for r in sorted(results, key=lambda x: -x['Return %']):
        print(f"{r['Coin']:<6} | {r['Return %']:>7.1f}% | {r['Win Rate %']:>7.1f}% | {r['PF']:>5.2f} | {r['Max DD %']:>6.1f}% | {r['Trades']:>6} | {r['First Trade']:>10} | {r['Last Trade']:>10}")
    print('-'*110)

    if results:
        avg_ret = sum(r['Return %'] for r in results) / len(results)
        avg_wr  = sum(r['Win Rate %'] for r in results) / len(results)
        total_trades = sum(r['Trades'] for r in results)
        print(f"\nAVERAGE Return: {avg_ret:.1f}% | AVERAGE Win Rate: {avg_wr:.1f}% | TOTAL Trades: {total_trades}")

    if all_trades:
        out = pd.DataFrame(all_trades)
        out = out[['coin','entry_date','entry_price','exit_date','exit_price','profit_pct','type','hold_days']]
        out = out.sort_values(['coin','entry_date'])
        csv = os.path.join(REPORT_DIR, 'backtest_21_coins_trades.csv')
        out.to_csv(csv, index=False)
        print(f"\nAll trades saved -> {csv}  ({len(out)} rows)")

if __name__ == '__main__':
    main()
