import pandas as pd
import pyvsmc
import logging

logger = logging.getLogger(__name__)

def check_filters(df: pd.DataFrame) -> tuple[bool, bool, bool]:
    """Calculates EMA200, MACD, and SMC Order Blocks."""
    close = df['close']
    
    # 1. Macro Trend
    ema200 = close.ewm(span=200, adjust=False).mean()
    above_ema = bool(close.iloc[-1] > ema200.iloc[-1])
    
    # 2. MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_bull = bool(macd.iloc[-1] > signal.iloc[-1])
    
    # 3. SMC (Order Blocks & FVG)
    try:
        fvg = pyvsmc.detect_fvg(high=df['high'].to_numpy(), low=df['low'].to_numpy(), close=df['close'].to_numpy())
        ob = pyvsmc.detect_order_blocks(open_=df['open'].to_numpy(), high=df['high'].to_numpy(), low=df['low'].to_numpy(), close=df['close'].to_numpy())
        
        # Check last 5 candles for a valid setup
        recent_bull_fvg = any(fvg.bullish[-5:] & ~fvg.mitigated[-5:])
        recent_bull_ob = any(ob.bullish_ob[-5:])
        smc_bull = bool(recent_bull_fvg or recent_bull_ob)
    except Exception as e:
        logger.error(f"SMC Detection Error: {e}")
        smc_bull = False
        
    return above_ema, macd_bull, smc_bull
