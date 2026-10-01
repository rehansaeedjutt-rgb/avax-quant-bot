import pandas as pd
import numpy as np
from backtesting import Strategy


def _rsi(close_series, period):
    close = pd.Series(close_series)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return (100 - (100 / (1 + rs))).to_numpy()


class SRBounceStrategy(Strategy):
    # --- Support / Resistance params ---
    pivot_lookback = 5       # bars left/right to confirm a pivot
    sr_window = 100          # how many recent bars to scan for S/R
    sr_tolerance = 0.02      # 2% zone around level
    min_touches = 2          # minimum times price touched to be valid S/R

    rsi_len = 14
    rsi_max = 45             # buy when RSI < this (dip)
    atr_len = 14
    tp_pct = 0.030           # 3% TP minimum
    sl_pct = 0.020           # 2% SL
    risk_per_trade = 0.02
    cooldown_bars = 5
    max_bars_in_trade = 100

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)
        open_p = pd.Series(self.data.Open)

        # RSI
        rsi_arr = _rsi(self.data.Close, self.rsi_len)

        # ATR for volatility
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_arr = tr.rolling(self.atr_len).mean().to_numpy()

        # Pivot highs and lows detection
        n = len(self.data)
        pivot_high = np.full(n, np.nan)
        pivot_low = np.full(n, np.nan)
        high_arr = high.to_numpy()
        low_arr = low.to_numpy()
        pl = self.pivot_lookback

        for i in range(pl, n - pl):
            window_high = high_arr[i - pl:i + pl + 1]
            window_low = low_arr[i - pl:i + pl + 1]
            if high_arr[i] == window_high.max():
                pivot_high[i] = high_arr[i]
            if low_arr[i] == window_low.min():
                pivot_low[i] = low_arr[i]

        self.rsi = self.I(lambda: rsi_arr, name='RSI')
        self.atr = self.I(lambda: atr_arr, name='ATR')
        self.pivot_high = self.I(lambda: pivot_high, name='PivotHigh')
        self.pivot_low = self.I(lambda: pivot_low, name='PivotLow')

        self.last_entry_bar = -99999
        self.entry_bar = -1

    def _find_nearest_support(self, idx):
        """Look back sr_window bars, find the highest pivot low below current price."""
        price = self.data.Close[-1]
        start = max(0, idx - self.sr_window)
        candidates = []
        for j in range(start, idx - self.pivot_lookback):
            pl = self.pivot_low[j]
            if pl is not None and not pd.isna(pl) and pl < price:
                candidates.append(pl)
        if not candidates:
            return None
        # Support = nearest pivot low that is still below price
        return max(candidates)

    def _find_nearest_resistance(self, idx):
        """Look back sr_window bars, find the lowest pivot high above current price."""
        price = self.data.Close[-1]
        start = max(0, idx - self.sr_window)
        candidates = []
        for j in range(start, idx - self.pivot_lookback):
            ph = self.pivot_high[j]
            if ph is not None and not pd.isna(ph) and ph > price:
                candidates.append(ph)
        if not candidates:
            return None
        # Resistance = nearest pivot high above price
        return min(candidates)

    def next(self):
        if len(self.data) < self.sr_window + 20:
            return

        idx = len(self.data) - 1
        price = self.data.Close[-1]
        open_p = self.data.Open[-1]
        low = self.data.Low[-1]

        rsi_v = self.rsi[-1]
        if pd.isna(rsi_v):
            return

        # Manage open position
        if self.position:
            if (idx - self.entry_bar) >= self.max_bars_in_trade:
                self.position.close()
            return

        # Cooldown
        if (idx - self.last_entry_bar) < self.cooldown_bars:
            return

        # Find S/R levels
        support = self._find_nearest_support(idx)
        resistance = self._find_nearest_resistance(idx)

        if support is None or resistance is None:
            return

        # Entry conditions
        near_support = low <= support * (1 + self.sr_tolerance) and price >= support * (1 - self.sr_tolerance)
        dip = rsi_v < self.rsi_max
        green = price > open_p
        enough_room = (resistance / price) >= 1.015  # at least 1.5% upside to resistance

        if near_support and dip and green and enough_room:
            # SL below support (but not more than sl_pct)
            raw_sl = support * (1 - 0.01)
            max_sl = price * (1 - self.sl_pct)
            sl_price = max(raw_sl, max_sl)  # tighter of the two

            # TP at resistance OR minimum tp_pct
            tp_price = max(resistance, price * (1 + self.tp_pct))

            risk_amount = self.equity * self.risk_per_trade
            risk_per_unit = price - sl_price
            if risk_per_unit <= 0:
                return

            size_units = int(min(risk_amount / risk_per_unit, (self.equity * 0.95) / price))
            if size_units >= 1:
                self.last_entry_bar = idx
                self.entry_bar = idx
                self.buy(size=size_units, sl=sl_price, tp=tp_price)
