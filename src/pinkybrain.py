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
    MarketSignal,
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
    def price(self):
        return float(self.data["close"].iloc[-1])

    def pop_close_time(self):
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
        adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=self.fast_window)
        self.data["adx_pos"] = adx.adx_pos()
        self.data["adx_neg"] = adx.adx_neg()

        bb = BollingerBands(close=df["close"], window=self.window)
        self.data["bb_high"] = bb.bollinger_hband()
        self.data["bb_low"] = bb.bollinger_lband()

        self.data["mfi"] = money_flow_index(df["high"], df["low"], df["close"], df["volume"], window=self.fast_window)

    def apply_adx_trigger(self):
        if self.data["adx_pos"].size == 0:
            return MarketSignal.HOLD

        adx_pos = self.data["adx_pos"].iloc[-1]
        adx_neg = self.data["adx_neg"].iloc[-1]
        treshold = 30

        if adx_pos >= treshold and adx_pos > adx_neg:
            return MarketSignal.SELL

        if adx_neg >= treshold and adx_neg > adx_pos:
            return MarketSignal.BUY

        return MarketSignal.HOLD

    def apply_mfi_trigger(self):
        if self.data["mfi"].size == 0:
            return MarketSignal.HOLD

        mfi = self.data["mfi"].iloc[-1]

        if mfi >= self.MFI_HIGH:
            return MarketSignal.SELL

        if mfi <= self.MFI_LOW:
            return MarketSignal.BUY

        return MarketSignal.HOLD

    def apply_bb_trigger(self):
        if self.data["mfi"].size == 0:
            return MarketSignal.HOLD

        price = self.price
        high = self.data["bb_high"].iloc[-1]
        low = self.data["bb_low"].iloc[-1]
        tolerance = price * 0.001

        if price + tolerance >= high:
            return MarketSignal.SELL

        if price - tolerance <= low:
            return MarketSignal.BUY

        return MarketSignal.HOLD

    def pick_dominant_signal(self, signals):
        bears = signals.count(MarketSignal.SELL)
        bulls = signals.count(MarketSignal.BUY)

        if bears > bulls and bears >= 2:
            signal = MarketSignal.SELL
        elif bulls > bears and bulls >= 2:
            signal = MarketSignal.BUY
        else:
            signal = MarketSignal.HOLD

        return signal

    def apply_all_triggers(self):
        triggers = dict(
            bb=self.apply_bb_trigger(),
            mfi=self.apply_mfi_trigger(),
            adx=self.apply_adx_trigger(),
        )
        return self.pick_dominant_signal(list(triggers.values())), triggers

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
                self.data["bb_high"], color="dodgerblue", panel=0, secondary_y=False
            ),
            mpf.make_addplot(
                self.data["bb_low"], color="darkorange", panel=0, secondary_y=False
            ),

            mpf.make_addplot(
                self.data["adx_pos"], color="dodgerblue", panel=1, secondary_y=False
            ),
            mpf.make_addplot(
                self.data["adx_neg"], color="darkorange", panel=1, secondary_y=False
            ),
            mpf.make_addplot(
                self.data["mfi"], color="tomato", panel=1, secondary_y=False
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
            returnfig=True,
        )

        for ax in axes:
            ax.yaxis.tick_left()
            ax.yaxis.label.set_visible(False)
            ax.margins(x=0.1, y=0.1, tight=False)

        plt.savefig(to_file, bbox_inches="tight", pad_inches=0.3, dpi=300)
        plt.close()
        print(f"saved chart as {to_file}")
