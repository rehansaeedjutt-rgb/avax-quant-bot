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


def _bb_lower(close_series, period=20, mult=2.0):
    close = pd.Series(close_series)
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return (ma - mult * sd).to_numpy()


class SRLongStrategy(Strategy):
    ema_fast_len = 20
    ema_med_len = 50
    ema_slow_len = 200
    rsi2_len = 2
    rsi2_max = 12
    bb_period = 20
    bb_mult = 2.0
    tp_pct = 0.007
    sl_pct = 0.025
    risk_per_trade = 0.02
    cooldown_bars = 3
    max_bars_in_trade = 200
    vol_factor = 0.8

    def init(self):
        close = pd.Series(self.data.Close)
        open_p = pd.Series(self.data.Open)
        low = pd.Series(self.data.Low)
        vol = pd.Series(self.data.Volume)
        n = len(self.data)
        fast_len = min(self.ema_fast_len, max(10, n // 30))
        med_len = min(self.ema_med_len, max(15, n // 15))
        slow_len = min(self.ema_slow_len, max(20, n // 8))

        ema_f = close.ewm(span=fast_len, adjust=False).mean().to_numpy()
        ema_m = close.ewm(span=med_len, adjust=False).mean().to_numpy()
        ema_s = close.ewm(span=slow_len, adjust=False).mean().to_numpy()
        rsi2 = _rsi(self.data.Close, self.rsi2_len)
        bb_lo = _bb_lower(self.data.Close, self.bb_period, self.bb_mult)
        vol_ma = vol.rolling(20).mean().to_numpy()

        self.ema_f = self.I(lambda: ema_f, name='EMA_F')
        self.ema_m = self.I(lambda: ema_m, name='EMA_M')
        self.ema_s = self.I(lambda: ema_s, name='EMA_S')
        self.rsi2 = self.I(lambda: rsi2, name='RSI2')
        self.bb_lo = self.I(lambda: bb_lo, name='BB_Lo')
        self.vol_ma = self.I(lambda: vol_ma, name='VolMA')

        self.last_entry_bar = -99999
        self.entry_bar = -1
        self.use_strict_trend = n >= 500

    def next(self):
        if len(self.data) < 40:
            return

        ema_f = self.ema_f[-1]
        ema_m = self.ema_m[-1]
        ema_s = self.ema_s[-1]
        r2 = self.rsi2[-1]
        bbl = self.bb_lo[-1]
        vm = self.vol_ma[-1]
        vol = self.data.Volume[-1]

        if any(pd.isna(x) for x in [ema_f, ema_m, ema_s, r2, bbl, vm]):
            return

        if self.position:
            if (len(self.data) - self.entry_bar) >= self.max_bars_in_trade:
                self.position.close()
            return

        if (len(self.data) - self.last_entry_bar) < self.cooldown_bars:
            return

        price = self.data.Close[-1]
        open_p = self.data.Open[-1]
        low = self.data.Low[-1]

        if self.use_strict_trend:
            uptrend = (price > ema_m) and (ema_m > ema_s)
        else:
            uptrend = price > ema_s

        oversold = r2 < self.rsi2_max
        bb_touch = low <= bbl * 1.005
        green_candle = price > open_p
        volume_ok = vol > vm * self.vol_factor

        if uptrend and oversold and bb_touch and green_candle and volume_ok:
            sl_price = price * (1 - self.sl_pct)
            tp_price = price * (1 + self.tp_pct)
            risk_amount = self.equity * self.risk_per_trade
            risk_per_unit = price - sl_price
            if risk_per_unit <= 0:
                return
            size_units = int(min(risk_amount / risk_per_unit, (self.equity * 0.95) / price))
            if size_units >= 1:
                self.last_entry_bar = len(self.data)
                self.entry_bar = len(self.data)
                self.buy(size=size_units, sl=sl_price, tp=tp_price)
