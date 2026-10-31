"""
=============================================================================
FUTURE ADMIRAL - FINAL LOCKED STRATEGY (v10.0)
=============================================================================
This is the exact logic running on the live bot.
Do not change these parameters without rigorous backtesting.

Strategy Type: Long-Only (Spot)
Timeframe: 1-Day (1D)
Assets: 9 Coins (AVAX, LINK, SOL, ADA, SUI, DOT, ETH, BNB, HYPE)

CORE LOGIC:
1. Macro Trend: Price > EMA 200
2. Momentum: MACD (12, 26, 9) is Bullish
3. Strength: ADX (14) > 20
4. Institutional: SMC (Bullish Order Block or FVG in last 5 candles)
5. Slippage: Current price must be within 1.5% of previous daily close.

RISK MANAGEMENT:
- Entry: 50% of allocated capital.
- DCA 1: Add 30% if price drops -2.0%.
- DCA 2: Add 20% if price drops -4.0%.
- TP1: Close 50% at +2.5%. Move SL to Breakeven.
- TP2: Close remaining 50% at +5.0%. Trail SL by 3% until TP2 is hit.
- Circuit Breaker: Hard exit if price drops -15% from original entry.

=============================================================================
"""

import pandas as pd
import numpy as np
import pyvsmc

# =============================================================================
# INDICATOR CALCULATIONS
# =============================================================================

def calculate_adx(high, low, close, period=14):
    """Calculate ADX (Average Directional Index) for trend strength."""
    plus_dm = high.diff().where(high.diff() > -low.diff(), 0).clip(lower=0)
    minus_dm = (-low.diff()).where(-low.diff() > high.diff(), 0).clip(lower=0)
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / (atr + 1e-9))
    minus_di = 100 * (minus_dm.rolling(period).mean() / (atr + 1e-9))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    return dx.rolling(period).mean()

def check_entry_filters(df: pd.DataFrame) -> tuple[bool, bool, bool, bool]:
    """Returns (EMA_OK, MACD_OK, SMC_OK, ADX_OK)."""
    close, high, low = df['close'], df['high'], df['low']
    
    # 1. Macro Trend (EMA 200)
    ema200 = close.ewm(span=200, adjust=False).mean()
    above_ema = bool(close.iloc[-1] > ema200.iloc[-1])
    
    # 2. Momentum (MACD 12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_bull = bool(macd.iloc[-1] > signal.iloc[-1])
    
    # 3. Trend Strength (ADX 14 > 20)
    adx_series = calculate_adx(high, low, close, period=14)
    adx_valid = bool(adx_series.iloc[-1] > 20)
    
    # 4. Institutional Support (SMC Order Blocks & FVG)
    try:
        fvg = pyvsmc.detect_fvg(high=high.to_numpy(), low=low.to_numpy(), close=close.to_numpy())
        ob = pyvsmc.detect_order_blocks(open_=df['open'].to_numpy(), high=high.to_numpy(), low=low.to_numpy(), close=close.to_numpy())
        
        # Check last 5 candles for a valid setup
        recent_bull_fvg = any(fvg.bullish[-5:] & ~fvg.mitigated[-5:])
        recent_bull_ob = any(ob.bullish_ob[-5:])
        smc_bull = bool(recent_bull_fvg or recent_bull_ob)
    except Exception:
        smc_bull = False
        
    return above_ema, macd_bull, smc_bull, adx_valid

# =============================================================================
# BACKTEST ENGINE (Exact logic of the live bot)
# =============================================================================

def run_locked_backtest(df: pd.DataFrame, initial_capital=1000.0):
    """
    Simulates the exact live trading logic.
    Returns: (Return %, Win Rate %, Profit Factor, Max Drawdown %)
    """
    capital = initial_capital
    cash = capital
    position = None
    trades = []
    equity_curve = []
    
    # --- LOCKED PARAMETERS ---
    TP1_PCT = 0.025        # +2.5%
    TP2_PCT = 0.05         # +5.0%
    DCA1_DROP = 0.02       # -2.0%
    DCA2_DROP = 0.04       # -4.0%
    TRAIL_PCT = 0.03       # 3% Trailing Stop after TP1
    CIRCUIT_BREAKER = 0.15 # 15% Hard Stop Loss
    SLIPPAGE = 0.0015      # 0.15%
    FEE = 0.0005           # 0.05%

    # We start at 250 to allow EMA200 to calculate
    for i in range(250, len(df)):
        row = df.iloc[i]
        close, high, low = row['close'], row['high'], row['low']
        
        # ==========================================
        # A. MANAGE ACTIVE TRADE
        # ==========================================
        if position:
            # 1. Circuit Breaker (Hard Stop)
            if low <= position['start_price'] * (1 - CIRCUIT_BREAKER):
                cash += (position['units'] * close)
                trades.append({'profit_pct': -CIRCUIT_BREAKER * 100, 'type': 'CB'})
                position = None
                equity_curve.append(cash)
                continue
            
            # 2. Partial Take Profit (TP1)
            if not position['tp1_hit'] and high >= position['tp1_price']:
                cash += (position['units'] * 0.5 * position['tp1_price'])
                position['units'] *= 0.5
                position['tp1_hit'] = True
                position['sl'] = position['avg'] # Move SL to Breakeven
                position['highest_price'] = high  # Start trailing
                
            # 3. Trailing Stop & Final Take Profit (TP2)
            if position['tp1_hit']:
                # Update highest price
                if high > position.get('highest_price', 0):
                    position['highest_price'] = high
                
                # Update trailing stop
                trail_sl = position['highest_price'] * (1 - TRAIL_PCT)
                if trail_sl > position['sl']:
                    position['sl'] = trail_sl
                    
                # Check TP2
                if high >= position['tp2_price']:
                    cash += (position['units'] * position['tp2_price'])
                    trades.append({'profit_pct': TP2_PCT * 100, 'type': 'TP2'})
                    position = None
                    equity_curve.append(cash)
                    continue
                    
                # Check Trailing SL hit
                if low <= position['sl']:
                    cash += (position['units'] * position['sl'])
                    profit = ((position['sl'] / position['avg']) - 1) * 100
                    trades.append({'profit_pct': profit, 'type': 'TRAIL'})
                    position = None
                    equity_curve.append(cash)
                    continue

            # 4. DCA Logic (Only if TP1 not hit yet)
            elif position['level'] < 3:
                dca1_price = position['start_price'] * (1 - DCA1_DROP)
                dca2_price = position['start_price'] * (1 - DCA2_DROP)
                
                if position['level'] == 1 and low <= dca1_price:
                    add_cost = position['initial_cost'] * 0.30
                    if cash >= add_cost:
                        position['units'] += add_cost / close
                        position['cost'] += add_cost
                        position['avg'] = position['cost'] / position['units']
                        position['tp1_price'] = position['avg'] * (1 + TP1_PCT)
                        position['tp2_price'] = position['avg'] * (1 + TP2_PCT)
                        position['level'] = 2
                        cash -= add_cost
                        
                elif position['level'] == 2 and low <= dca2_price:
                    add_cost = position['initial_cost'] * 0.20
                    if cash >= add_cost:
                        position['units'] += add_cost / close
                        position['cost'] += add_cost
                        position['avg'] = position['cost'] / position['units']
                        position['tp1_price'] = position['avg'] * (1 + TP1_PCT)
                        position['tp2_price'] = position['avg'] * (1 + TP2_PCT)
                        position['level'] = 3
                        cash -= add_cost
                        
        # ==========================================
        # B. NEW ENTRY
        # ==========================================
        else:
            # 1. Slippage Check (vs previous daily close)
            prev_close = df['close'].iloc[i-1]
            slippage_pct = abs(close - prev_close) / prev_close
            if slippage_pct > 0.015:
                equity_curve.append(cash)
                continue
            
            # 2. Check all filters
            ema_ok, macd_ok, smc_ok, adx_ok = check_entry_filters(df.iloc[:i+1])
            
            if ema_ok and macd_ok and smc_ok and adx_ok:
                cost = capital * 0.50
                units = cost / (close * (1 + SLIPPAGE))
                cash -= cost
                position = {
                    'start_price': close,
                    'units': units,
                    'cost': cost,
                    'initial_cost': cost,
                    'avg': close,
                    'level': 1,
                    'tp1_hit': False,
                    'tp1_price': close * (1 + TP1_PCT),
                    'tp2_price': close * (1 + TP2_PCT),
                    'sl': close * (1 - CIRCUIT_BREAKER),
                    'highest_price': close
                }

        # Update equity curve
        equity_curve.append(cash + (position['units'] * close if position else 0))

    # ==========================================
    # C. CALCULATE METRICS
    # ==========================================
    if len(equity_curve) == 0:
        return 0, 0, 0, 0
        
    eq_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / peak).min() * 100
    ret = (eq_arr[-1] - capital) / capital * 100
    
    wins = sum(1 for t in trades if t['profit_pct'] >= 0)
    total = len(trades)
    wr = (wins / total * 100) if total else 0
    
    # PROFIT FACTOR FORMULA
    gross_win = sum(t['profit_pct'] for t in trades if t['profit_pct'] > 0)
    gross_loss = abs(sum(t['profit_pct'] for t in trades if t['profit_pct'] < 0))
    pf = (gross_win / gross_loss) if gross_loss > 0 else 0
    
    return ret, wr, pf, dd