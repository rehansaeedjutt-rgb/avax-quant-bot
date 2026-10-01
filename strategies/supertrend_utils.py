import pandas as pd
import numpy as np


def supertrend(high, low, close, period=10, multiplier=3.0, use_wilder_atr=True):
    """
    Supertrend indicator (Pine Script equivalent).
    
    Returns:
        trend (np.array): 1 = bullish, -1 = bearish
        up (np.array): upper band (stops for long)
        dn (np.array): lower band (stops for short)
    """
    high = pd.Series(high).reset_index(drop=True)
    low = pd.Series(low).reset_index(drop=True)
    close = pd.Series(close).reset_index(drop=True)

    hl2 = (high + low) / 2.0

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    if use_wilder_atr:
        atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    else:
        atr = tr.rolling(period).mean()

    n = len(close)
    up = (hl2 - multiplier * atr).to_numpy()
    dn = (hl2 + multiplier * atr).to_numpy()
    close_arr = close.to_numpy()

    up_band = np.full(n, np.nan)
    dn_band = np.full(n, np.nan)
    trend = np.full(n, 1, dtype=int)

    for i in range(1, n):
        if np.isnan(up[i]) or np.isnan(dn[i]):
            up_band[i] = up_band[i - 1]
            dn_band[i] = dn_band[i - 1]
            trend[i] = trend[i - 1]
            continue

        prev_close = close_arr[i - 1]
        prev_up = up_band[i - 1] if not np.isnan(up_band[i - 1]) else up[i]
        prev_dn = dn_band[i - 1] if not np.isnan(dn_band[i - 1]) else dn[i]

        # Up band (final)
        up_band[i] = max(up[i], prev_up) if prev_close > prev_up else up[i]
        # Down band (final)
        dn_band[i] = min(dn[i], prev_dn) if prev_close < prev_dn else dn[i]

        prev_trend = trend[i - 1]
        if prev_trend == -1 and close_arr[i] > prev_dn:
            trend[i] = 1
        elif prev_trend == 1 and close_arr[i] < prev_up:
            trend[i] = -1
        else:
            trend[i] = prev_trend

    return trend, up_band, dn_band
