import pandas as pd
import numpy as np
from backtesting import Strategy
import sys
sys.path.insert(0, 'C:/avax_quant_system')
from strategies.supertrend_utils import supertrend


def _rsi(close_series, period):
    close = pd.Series(close_series)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return (100 - (100 / (1 + rs))).to_numpy()


class CombinedStrategy(Strategy):
    atr_period = 10
    atr_multiplier = 3.0
    rsi2_len = 2
    rsi2_max = 25
    ema_fast_len = 50
    ema_slow_len = 200
    tp_pct = 0.020
    sl_pct = 0.020
    risk_per_trade = 0.02
    cooldown_bars = 3

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)
        open_p = pd.Series(self.data.Open)

        trend, up, dn = supertrend(high, low, close,
                                    self.atr_period, self.atr_multiplier)
        ema_f = close.ewm(span=self.ema_fast_len, adjust=False).mean().to_numpy()
        ema_s = close.ewm(span=self.ema_slow_len, adjust=False).mean().to_numpy()
        rsi2 = _rsi(self.data.Close, self.rsi2_len)

        self.trend = self.I(lambda: trend, name='Trend')
        self.up_band = self.I(lambda: up, name='UpBand')
        self.ema_f = self.I(lambda: ema_f, name='EMA_F')
        self.ema_s = self.I(lambda: ema_s, name='EMA_S')
        self.rsi2 = self.I(lambda: rsi2, name='RSI2')

        self.last_entry_bar = -99999

    def next(self):
        if len(self.data) < 210:
            return

        trend_now = self.trend[-1]
        price = self.data.Close[-1]
        ema_f = self.ema_f[-1]
        ema_s = self.ema_s[-1]
        r2 = self.rsi2[-1]

        if any(pd.isna(x) for x in [ema_f, ema_s, r2]):
            return

        if self.position:
            return

        if (len(self.data) - self.last_entry_bar) < self.cooldown_bars:
            return

        # Entry conditions:
        # 1. Supertrend bullish
        # 2. Price > EMA50 > EMA200 (uptrend)
        # 3. RSI2 dip (< 25)
        cond1 = trend_now == 1
        cond2 = price > ema_f > ema_s
        cond3 = r2 < self.rsi2_max

        if cond1 and cond2 and cond3:
            sl_price = price * (1 - self.sl_pct)
            tp_price = price * (1 + self.tp_pct)
            risk_amount = self.equity * self.risk_per_trade
            risk_per_unit = price - sl_price
            if risk_per_unit <= 0:
                return
            size = int(min(risk_amount / risk_per_unit, (self.equity * 0.95) / price))
            if size >= 1:
                self.last_entry_bar = len(self.data)
                self.buy(size=size, sl=sl_price, tp=tp_price)
