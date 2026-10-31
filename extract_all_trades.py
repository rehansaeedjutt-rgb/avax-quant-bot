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

COINS = {
    'HYPE': 'HYPEUSDT_1d_EXACT.csv',
    'ETH':  'ETHUSDT_1d_EXACT.csv',
    'BNB':  'BNBUSDT_1d_EXACT.csv',
    'AVAX': 'AVAX_USDT_1d_MERGED_5Y.csv',
    'LINK': 'LINK_USDT_1d_EXACT.csv',
    'SOL':  'SOLUSDT_1d_EXACT.csv',
    'ADA':  'ADAUSDT_1d_EXACT.csv',
    'SUI':  'SUIUSDT_1d_EXACT.csv',
    'DOT':  'DOTUSDT_1d_EXACT.csv',
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

def run_backtest_with_dates(df):
    capital = 1000.0
    cash = capital
    pos = None
    trades = []
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
            # Circuit Breaker
            if low <= pos['start_price'] * (1 - cb_pct):
                cash += pos['units'] * close
                trades.append({
                    'profit_pct': -cb_pct*100, 'type': 'CB',
                    'entry_date': pos['entry_date'], 'entry_price': pos['entry_price'],
                    'exit_date': candle_date, 'exit_price': close,
                })
                pos = None
                continue

            # TP1 partial exit (no trade append in original)
            if not pos['tp1_hit'] and high >= pos['tp1_price']:
                cash += pos['units'] * 0.5 * pos['tp1_price']
                pos['units'] *= 0.5
                pos['tp1_hit'] = True
                pos['sl'] = pos['avg']

            # TP2 full exit
            if pos['tp1_hit'] and high >= pos['tp2_price']:
                cash += pos['units'] * pos['tp2_price']
                trades.append({
                    'profit_pct': tp2_pct*100, 'type': 'TP2',
                    'entry_date': pos['entry_date'], 'entry_price': pos['entry_price'],
                    'exit_date': candle_date, 'exit_price': pos['tp2_price'],
                })
                pos = None
                continue

            # SL / BE
            if low <= pos['sl']:
                cash += pos['units'] * pos['sl']
                profit = ((pos['sl'] / pos['avg']) - 1) * 100
                trades.append({
                    'profit_pct': profit,
                    'type': 'SL' if not pos['tp1_hit'] else 'BE',
                    'entry_date': pos['entry_date'], 'entry_price': pos['entry_price'],
                    'exit_date': candle_date, 'exit_price': pos['sl'],
                })
                pos = None
                continue

            # DCA
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

    return trades

def main():
    all_trades = []
    summary = []

    for coin, fn in COINS.items():
        path = os.path.join(DATA_DIR, fn)
        if not os.path.exists(path):
            print(f'SKIP {coin}: {fn} missing'); continue
        try:
            df = add_indicators(load_data(fn))
        except Exception as e:
            print(f'ERROR {coin}: {e}'); continue

        trades = run_backtest_with_dates(df)
        if not trades:
            print(f'{coin}: 0 trades'); continue

        for t in trades:
            t['coin'] = coin
            t['hold_days'] = (t['exit_date'] - t['entry_date']).days
            all_trades.append(t)

        wins = sum(1 for t in trades if t['profit_pct'] >= 0)
        summary.append({
            'coin': coin, 'total': len(trades), 'wins': wins,
            'wr': round(wins/len(trades)*100, 2),
            'first': trades[0]['entry_date'].strftime('%Y-%m-%d'),
            'last':  trades[-1]['entry_date'].strftime('%Y-%m-%d'),
        })

    if all_trades:
        out = pd.DataFrame(all_trades)
        out = out[['coin','entry_date','entry_price','exit_date','exit_price','profit_pct','type','hold_days']]
        out = out.sort_values(['coin','entry_date'])
        csv = os.path.join(REPORT_DIR, 'all_trades_detail.csv')
        out.to_csv(csv, index=False)
        print(f'\nSAVED {len(all_trades)} trades -> {csv}\n')

        print('='*95)
        print('SUMMARY (wins count includes BE / profit_pct >= 0)')
        print('='*95)
        for s in summary:
            print(f"{s['coin']:5} | trades:{s['total']:4} | wins:{s['wins']:4} | WR:{s['wr']:5.1f}% | {s['first']} -> {s['last']}")

        print('\n' + '='*95)
        print('PER-COIN TRADE LIST')
        print('='*95)
        for coin in COINS.keys():
            ct = [t for t in all_trades if t['coin'] == coin]
            if not ct: continue
            print(f"\n--- {coin} ({len(ct)} trades) ---")
            for t in ct:
                ed = t['entry_date'].strftime('%Y-%m-%d')
                xd = t['exit_date'].strftime('%Y-%m-%d')
                print(f"  {ed} -> {xd} | {t['type']:3} | {t['profit_pct']:+7.2f}% | entry ${t['entry_price']:.4f} exit ${t['exit_price']:.4f} | {t['hold_days']}d")
    else:
        print('No trades.')

if __name__ == '__main__':
    main()
