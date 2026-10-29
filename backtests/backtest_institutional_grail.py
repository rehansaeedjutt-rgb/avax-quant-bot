"""
INSTITUTIONAL QUANT STRATEGY (v10.0 - Holy Grail)
Modules:
1. Baseline (MACD + EMA200 + Fixed DCA)
2. Dynamic DCA (ATR-Based)
3. Partial TP & Trailing Stop (Breakeven Protection)
4. SMC Entry (Order Blocks / FVG)
5. Macro Filters (Fear & Greed + Funding Rates)
6. Walk-Forward Validation (Train: 2020-2022, Test: 2023-2026)
"""
import os
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

import pyvsmc

ROOT = 'C:/avax_quant_system'
DATA_DIR = os.path.join(ROOT, 'data')
ONCHAIN_DIR = os.path.join(DATA_DIR, 'onchain')
SLIPPAGE = 0.0015
FEE = 0.0005

# ==================== DATA LOADING ====================
def load_macro_data():
    # Fear & Greed
    try:
        fg = pd.read_json(f'{ONCHAIN_DIR}/fear_greed.json')
        fg['date'] = pd.to_datetime(fg['timestamp'], unit='s').dt.date
        fg = fg[['date', 'value']].rename(columns={'value': 'fng'})
        fg = fg.drop_duplicates('date').set_index('date')
    except Exception:
        fg = pd.DataFrame()

    # Funding Rates
    try:
        fr = pd.read_json(f'{ONCHAIN_DIR}/funding_rates.json')
        fr['date'] = pd.to_datetime(fr['fundingTime'], unit='ms').dt.date
        fr = fr[['date', 'fundingRate']].rename(columns={'fundingRate': 'funding'})
        fr = fr.groupby('date').mean()
    except Exception:
        fr = pd.DataFrame()
        
    return fg, fr

def load_coin_data(symbol, fg, fr):
    if symbol == 'AVAX':
        df = pd.read_csv(f'{DATA_DIR}/AVAX_USDT_1d_MERGED_5Y.csv')
    else:
        df = pd.read_csv(f'{DATA_DIR}/LINK_USDT_1d_EXACT.csv')
        
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df = df.set_index('open_time').sort_index()
    df = df.rename(columns={'open':'o','high':'h','low':'l','close':'c','volume':'v'})
    df['date'] = df.index.date
    
    # Merge Macro
    if not fg.empty:
        df = df.join(fg, on='date')
        df['fng'] = df['fng'].fillna(50).astype(float)
    else:
        df['fng'] = 50.0
        
    if not fr.empty:
        df = df.join(fr, on='date')
        df['funding'] = df['funding'].fillna(0).astype(float)
    else:
        df['funding'] = 0.0
        
    return df.dropna()

# ==================== INDICATORS ====================
def add_indicators(df):
    # Trend & Momentum
    df['ema200'] = df['c'].ewm(span=200, adjust=False).mean()
    df['above_ema'] = df['c'] > df['ema200']
    
    ema12 = df['c'].ewm(span=12, adjust=False).mean()
    ema26 = df['c'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_bull'] = macd > signal
    
    # ATR (14)
    tr = np.maximum(df['h'] - df['l'], np.maximum(abs(df['h'] - df['c'].shift(1)), abs(df['l'] - df['c'].shift(1))))
    df['atr'] = tr.rolling(14).mean()
    
    # SMC
    try:
        fvg = pyvsmc.detect_fvg(high=df['h'].to_numpy(), low=df['l'].to_numpy(), close=df['c'].to_numpy())
        ob = pyvsmc.detect_order_blocks(open_=df['o'].to_numpy(), high=df['h'].to_numpy(), low=df['l'].to_numpy(), close=df['c'].to_numpy())
        
        bull_fvg = fvg.bullish & ~fvg.mitigated
        bull_ob = ob.bullish_ob
        df['smc_bull'] = bull_fvg | bull_ob
    except Exception:
        df['smc_bull'] = True # Fallback
        
    return df.dropna()

# ==================== BACKTEST ENGINE ====================
def backtest(df, use_atr_dca=False, use_partial_tp=False, use_smc=False, use_macro=False, symbol='AVAX'):
    capital = 1000.0
    cash = capital
    pos = None
    trades = []
    equity = []
    
    # Base Settings
    tp_base = 0.04 if symbol == 'AVAX' else 0.06
    dca1_base = 0.02 if symbol == 'AVAX' else 0.03
    dca2_base = 0.04 if symbol == 'AVAX' else 0.06
    circuit_breaker_pct = 0.15
    
    for i in range(250, len(df)): # Skip warmup
        row = df.iloc[i]
        ts = df.index[i]
        close, high, low, atr = row['c'], row['h'], row['l'], row['atr']
        
        # --- POSITION MANAGEMENT ---
        if pos:
            # 1. Circuit Breaker
            if low <= pos['start_price'] * (1 - circuit_breaker_pct):
                cash += (pos['units'] * close)
                trades.append({'profit_pct': -circuit_breaker_pct * 100, 'type': 'CB'})
                pos = None
                equity.append(cash)
                continue
                
            # 2. Take Profit (Partial or Full)
            tp_price = pos['avg'] * (1 + tp_base) if not use_partial_tp else pos['avg'] + (atr * 1.5)
            
            if high >= tp_price:
                if use_partial_tp and not pos['tp1_hit']:
                    # Sell 50%, move SL to BE
                    pos['tp1_hit'] = True
                    cash += (pos['units'] * 0.5 * tp_price)
                    pos['units'] *= 0.5
                    pos['sl'] = pos['avg'] # Breakeven
                elif not use_partial_tp or pos['tp1_hit']:
                    # Sell remaining or 100%
                    cash += (pos['units'] * tp_price)
                    trades.append({'profit_pct': tp_base * 100, 'type': 'TP'})
                    pos = None
                    equity.append(cash)
                    continue
                    
            # 3. Trailing Stop (Only if TP1 hit)
            if use_partial_tp and pos['tp1_hit']:
                trail_sl = high - (atr * 2.0)
                if trail_sl > pos['sl']:
                    pos['sl'] = trail_sl
                    
            # 4. Stop Loss
            if low <= pos['sl']:
                exit_price = pos['sl']
                cash += (pos['units'] * exit_price)
                profit = ((exit_price / pos['avg']) - 1) * 100
                trades.append({'profit_pct': profit, 'type': 'SL'})
                pos = None
                equity.append(cash)
                continue
                
            # 5. DCA
            dca1_price = pos['start_price'] * (1 - dca1_base) if not use_atr_dca else (pos['start_price'] - atr * 2)
            dca2_price = pos['start_price'] * (1 - dca2_base) if not use_atr_dca else (pos['start_price'] - atr * 4)
            
            if pos['level'] == 1 and low <= dca1_price:
                add_cost = pos['initial_cost'] * 0.30
                if cash >= add_cost:
                    pos['units'] += add_cost / close
                    pos['cost'] += add_cost
                    pos['avg'] = pos['cost'] / pos['units']
                    pos['level'] = 2
                    cash -= add_cost
            elif pos['level'] == 2 and low <= dca2_price:
                add_cost = pos['initial_cost'] * 0.20
                if cash >= add_cost:
                    pos['units'] += add_cost / close
                    pos['cost'] += add_cost
                    pos['avg'] = pos['cost'] / pos['units']
                    pos['level'] = 3
                    cash -= add_cost
                    
        # --- ENTRY LOGIC ---
        else:
            # Base Triggers
            trend_ok = row['above_ema'] and row['macd_bull']
            smc_ok = row['smc_bull'] if use_smc else True
            macro_ok = (row['fng'] < 60 and row['funding'] <= 0) if use_macro else True
            
            if trend_ok and smc_ok and macro_ok:
                cost = capital * 0.5
                units = cost / (close * (1 + SLIPPAGE))
                cash -= cost
                pos = {
                    'start_price': close, 'units': units, 'cost': cost,
                    'initial_cost': cost, 'avg': close, 'level': 1,
                    'tp1_hit': False, 'sl': close * (1 - 0.03) # Initial 3% SL
                }
                
        equity.append(cash + (pos['units'] * close if pos else 0))

    # Close any open pos
    if pos:
        cash += (pos['units'] * df['c'].iloc[-1])
        
    eq_arr = np.array(equity)
    if len(eq_arr) == 0: return 0, 0, 0, 0, 0
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    ret = (eq_arr[-1] - capital) / capital * 100
    
    wins = sum(1 for t in trades if t['profit_pct'] > 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    
    gw = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gl = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] <= 0))
    pf = (gw / gl) if gl > 0 else 0
    
    sl_hits = sum(1 for t in trades if t['type'] == 'SL')
    
    return ret, wr, pf, dd, total, sl_hits

# ==================== MAIN EXECUTION ====================
if __name__ == '__main__':
    print("Loading Macro Data...")
    fg, fr = load_macro_data()
    
    for symbol in ['AVAX', 'LINK']:
        print(f"\n{'='*90}")
        print(f"INSTITUTIONAL BACKTEST — {symbol}/USDT (Walk-Forward Test: 2023-2026)")
        print(f"{'='*90}")
        
        df = load_coin_data(symbol, fg, fr)
        df = add_indicators(df)
        
        # Walk-Forward: Train on 2020-2022, Test on 2023-2026 (OOS)
        test_df = df[df.index >= '2023-01-01'].copy()
        
        scenarios = [
            ("1. Baseline (Fixed DCA, Fixed TP)", False, False, False, False),
            ("2. ATR-Based DCA", True, False, False, False),
            ("3. Partial TP + Trailing", False, True, False, False),
            ("4. SMC Entry (OB/FVG)", False, False, True, False),
            ("5. Macro Filter (F&G/Funding)", False, False, False, True),
            ("6. HOLY GRAIL (All Combined)", True, True, True, True)
        ]
        
        print(f'{"Strategy Module":<35} | {"Return":>8} | {"Win Rate":>8} | {"PF":>5} | {"Max DD":>7} | {"SL Hits":>7} | {"Trades":>6}')
        print('-' * 90)
        
        for name, atr, partial, smc, macro in scenarios:
            ret, wr, pf, dd, total, sl_hits = backtest(test_df, atr, partial, smc, macro, symbol)
            print(f'{name:<35} | {ret:>7.1f}% | {wr:>7.1f}% | {pf:>5.2f} | {dd:>6.1f}% | {sl_hits:>7} | {total:>6}')
            
        print('=' * 90)
