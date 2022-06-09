from decimal import Decimal
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import mplfinance as mpf
from matplotlib import pyplot as plt, dates as mdates

from ta.volatility import BollingerBands
from ta.trend import ADXIndicator, PSARIndicator, stc
from ta.volume import money_flow_index

from metaflip import (
    KLinePoint,
    CandleStick,
    FlipSignals,
    FULL_CYCLE,
    WEEKLY_CYCLE,
    DAILY_CYCLE,
    FIBONACCI,
)


class PinkyTracker:
    SIGNAL_TTL = 5
    MFI_HIGH = 65
    MFI_LOW = 35

    def __init__(self, trading_pair, wix=6):
        self.base_symbol, self.quote_symbol = trading_pair
        self.wix = wix

        self.data = pd.DataFrame(
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
            ]
        )

    @property
    def faster_window(self):
        return FIBONACCI[self.wix - 1]

    @property
    def fast_window(self):
        return FIBONACCI[self.wix - 1]

    @property
    def window(self):
        return FIBONACCI[self.wix]

    @property
    def slow_window(self):
        return FIBONACCI[self.wix + 1]

    @property
    def slower_window(self):
        return FIBONACCI[self.wix + 1]

    @property
    def last_close_time(self):
        self.data.drop(self.data.tail(1).index, inplace=True)
        close_time = int(self.data["close_time"].iloc[-1].timestamp()) * 1000
        return close_time

    def feed(self, kline_data, limit=FULL_CYCLE):
        if not kline_data:
            print("Provided feed seems empty, skipped.")
            return

        if len(kline_data) > limit:
            kline_data = kline_data[-limit:]
            print(f"Provided feed was truncated to last {len(kline_data)}.")

        klines = [CandleStick(x) for x in kline_data]
        new_df = pd.DataFrame(klines)
        new_df.index = pd.DatetimeIndex(new_df["open_time"])

        self.data = pd.concat([self.data.tail(limit - new_df.size), new_df])

    def run_indicators(self):
        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "volume": "float",
            }
        )
        adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"])
        self.data["adx_pos"] = adx.adx_pos()
        self.data["adx_neg"] = adx.adx_neg()

    def apply_triggers(self):
        if self.data["adx_pos"].size == 0:
            return FlipSignals.HOLD

        adx_pos = self.data["adx_pos"].iloc[-1]
        adx_neg = self.data["adx_neg"].iloc[-1]
        treshold = 30

        if adx_pos >= treshold and adx_pos > adx_neg:
            return FlipSignals.SELL

        if adx_neg >= treshold and adx_neg > adx_pos:
            return FlipSignals.BUY

        return FlipSignals.HOLD

    def draw_chart(self, to_file, limit=FULL_CYCLE):

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "volume": "float",
            }
        )  # again :()

        extras = [
            mpf.make_addplot(
                self.data["adx_pos"], color="dodgerblue", panel=1, secondary_y=False
            ),
            mpf.make_addplot(
                self.data["adx_neg"], color="darkorange", panel=1, secondary_y=False
            ),
        ]

        fig, axes = mpf.plot(
            df,
            type="candle",
            addplot=extras,
            title=f"{self.base_symbol}/{self.quote_symbol}",
            # volume=True,
            figsize=(13, 8),
            tight_layout=True,
            style="yahoo",
            xrotation=0,
            warn_too_much_data=limit,
            returnfig=True,
        )

        plt.savefig(to_file, bbox_inches="tight", pad_inches=0.3, dpi=300)
        plt.close()
        print(f"saved chart as {to_file}")
