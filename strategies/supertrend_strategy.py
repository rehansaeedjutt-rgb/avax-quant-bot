import pandas as pd
import numpy as np
from backtesting import Strategy
import sys
sys.path.insert(0, 'C:/avax_quant_system')
from strategies.supertrend_utils import supertrend


class SupertrendStrategy(Strategy):
    atr_period = 10
    atr_multiplier = 3.0
    tp_pct = 0.030
    sl_pct = 0.020
    risk_per_trade = 0.02
    use_ema_filter = True
    ema_len = 200

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        trend, up, dn = supertrend(high, low, close,
                                    self.atr_period, self.atr_multiplier)
        ema_arr = close.ewm(span=self.ema_len, adjust=False).mean().to_numpy()

        self.trend = self.I(lambda: trend, name='Trend')
        self.up_band = self.I(lambda: up, name='UpBand')
        self.dn_band = self.I(lambda: dn, name='DnBand')
        self.ema = self.I(lambda: ema_arr, name='EMA')

    def next(self):
        if len(self.data) < self.atr_period + 5:
            return

        trend_now = self.trend[-1]
        trend_prev = self.trend[-2]
        price = self.data.Close[-1]
        ema_v = self.ema[-1]

        if pd.isna(ema_v):
            return

        # Manage open position
        if self.position:
            return

        # Entry: Supertrend flips from -1 to 1
        buy_signal = trend_now == 1 and trend_prev == -1
        ema_ok = (not self.use_ema_filter) or (price > ema_v)

        if buy_signal and ema_ok:
            sl_price = price * (1 - self.sl_pct)
            tp_price = price * (1 + self.tp_pct)

            risk_amount = self.equity * self.risk_per_trade
            risk_per_unit = price - sl_price
            if risk_per_unit <= 0:
                return
            size = int(min(risk_amount / risk_per_unit, (self.equity * 0.95) / price))
            if size >= 1:
                self.buy(size=size, sl=sl_price, tp=tp_price)
