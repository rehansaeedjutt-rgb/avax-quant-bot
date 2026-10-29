"""
BACKTEST v6.2 — Exact match of live bot logic
Rules:
- Buy Threshold: 0.15
- TP1: +1.5% (Close 50%, move SL to Breakeven)
- TP2: +3.0% (Close remaining 50%)
- SL: -2.0% (if TP1 not hit)
- DCA: Level 1 at -1.0% (add 25%), Level 2 at -1.5% (add 25%)
- Max Hold: 100 hours
"""
import os
import numpy as np
import pandas as pd

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
SLIPPAGE = 0.0015
FEE = 0.0005

def load():
    df = pd.read_csv(f'{DATA_DIR}/avax_master_score.csv')
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    ohlcv = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1h_MERGED.csv')
    ohlcv['open_time'] = pd.to_datetime(ohlcv['open_time'], unit='ms')
    ohlcv = ohlcv.set_index('open_time').sort_index()
    ohlcv = ohlcv.rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
    return df.join(ohlcv[['o', 'h', 'l', 'c']], how='inner')

def backtest(df, buy_th=0.15, max_hold=100):
    capital = 1000.0
    cash = capital
    position = None
    trades = []
    equity = []

    for i, (ts, row) in enumerate(df.iterrows()):
        close, high, low = row['c'], row['h'], row['l']
        score = row['master']

        if position:
            hours = i - position['bar']
            is_tp1_hit = position['tp1_hit']
            
            # 1. Update DCA (Only if TP1 not hit yet)
            if not is_tp1_hit:
                if not position['dca1_hit'] and low <= position['entry'] * 0.99:
                    position['dca1_hit'] = True
                    # Add 25% of initial position size
                    add_units = (position['initial_units'] * 0.25) / close
                    position['units'] += add_units
                    position['cost'] += (add_units * close)
                    position['avg'] = position['cost'] / position['units']
                    # Update targets
                    position['tp1'] = position['avg'] * 1.015
                    position['tp2'] = position['avg'] * 1.030
                    position['sl'] = position['avg'] * 0.980
                elif position['dca1_hit'] and not position['dca2_hit'] and low <= position['entry'] * 0.985:
                    position['dca2_hit'] = True
                    add_units = (position['initial_units'] * 0.25) / close
                    position['units'] += add_units
                    position['cost'] += (add_units * close)
                    position['avg'] = position['cost'] / position['units']
                    position['tp1'] = position['avg'] * 1.015
                    position['tp2'] = position['avg'] * 1.030
                    position['sl'] = position['avg'] * 0.980

            # 2. Check TP1
            if not is_tp1_hit and high >= position['tp1']:
                position['tp1_hit'] = True
                position['sl'] = position['avg'] # Move SL to breakeven
                # Sell 50%
                sell_units = position['units'] * 0.5
                proceeds = sell_units * position['tp1'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                position['units'] -= sell_units
                position['realized_profit'] = (proceeds - fee) - (sell_units * position['avg'] * (1 + SLIPPAGE))

            # 3. Check TP2 (Remaining 50%)
            elif position['tp1_hit'] and high >= position['tp2']:
                proceeds = position['units'] * position['tp2'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                total_profit = position['realized_profit'] + (proceeds - fee) - (position['units'] * position['avg'] * (1 + SLIPPAGE))
                trades.append({'profit_pct': (total_profit / (position['initial_units'] * position['entry'])) * 100, 'type': 'TP2', 'held': hours})
                position = None

            # 4. Check SL (Initial or Breakeven)
            elif low <= position['sl']:
                proceeds = position['units'] * position['sl'] * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                total_profit = position.get('realized_profit', 0) + (proceeds - fee) - (position['units'] * position['avg'] * (1 + SLIPPAGE))
                trades.append({'profit_pct': (total_profit / (position['initial_units'] * position['entry'])) * 100, 'type': 'BE' if is_tp1_hit else 'SL', 'held': hours})
                position = None
                
            # 5. Time Exit
            elif hours >= max_hold:
                proceeds = position['units'] * close * (1 - SLIPPAGE)
                fee = proceeds * FEE
                cash += (proceeds - fee)
                total_profit = position.get('realized_profit', 0) + (proceeds - fee) - (position['units'] * position['avg'] * (1 + SLIPPAGE))
                trades.append({'profit_pct': (total_profit / (position['initial_units'] * position['entry'])) * 100, 'type': 'TIME', 'held': hours})
                position = None

        # Entry Signal
        elif score >= buy_th and cash > 50:
            dollars = cash * 0.20 # 20% of equity
            units = dollars / (close * (1 + SLIPPAGE))
            cash -= dollars
            position = {
                'entry': close, 'avg': close, 'units': units, 'initial_units': units, 'cost': dollars,
                'tp1': close * 1.015, 'tp2': close * 1.030, 'sl': close * 0.980,
                'tp1_hit': False, 'dca1_hit': False, 'dca2_hit': False,
                'bar': i, 'realized_profit': 0
            }

        # Update Equity
        current_equity = cash + (position['units'] * close if position else 0)
        equity.append(current_equity)

    # Close any open position at the end
    if position:
        proceeds = position['units'] * df['c'].iloc[-1]
        cash += proceeds

    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    final = eq_arr[-1]
    ret_pct = (final - capital) / capital * 100

    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gw / gl) if gl > 0 else 0

    tp2_count = sum(1 for t in trades if t['type'] == 'TP2')
    be_count = sum(1 for t in trades if t['type'] == 'BE')
    sl_count = sum(1 for t in trades if t['type'] == 'SL')
    time_count = sum(1 for t in trades if t['type'] == 'TIME')

    return {'ret': ret_pct, 'trades': total, 'wr': wr, 'pf': pf, 'dd': dd,
            'tp2': tp2_count, 'be': be_count, 'sl': sl_count, 'time': time_count}

if __name__ == '__main__':
    print('=' * 80)
    print('BACKTEST v6.2 — Partial TP, Breakeven SL, 2% SL')
    print('=' * 80)
    df = load()
    r = backtest(df)
    
    print(f"\nTotal Return   : {r['ret']:>8.2f}%")
    print(f"Total Trades   : {r['trades']:>8}")
    print(f"Win Rate       : {r['wr']:>8.2f}%")
    print(f"Profit Factor  : {r['pf']:>8.2f}")
    print(f"Max Drawdown   : {r['dd']:>8.2f}%")
    print(f"\nExit Breakdown:")
    print(f"  Final TP2    : {r['tp2']:>8}")
    print(f"  Breakeven    : {r['be']:>8}")
    print(f"  Full SL      : {r['sl']:>8}")
    print(f"  Time Exit    : {r['time']:>8}")
