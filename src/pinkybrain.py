from decimal import Decimal
from datetime import datetime, timedelta

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
)


class PinkyTracker:
    FF = [
        2,
        3,
        5,
        8,
        13,
        21,
        34,
        55,
        89,
        144,
    ]
    SIGNAL_TTL = 5
    MFI_HIGH = 65
    MFI_LOW = 35

    def __init__(self, trading_pair, budget, commission, wix):
        self.base_symbol, self.quote_symbol = trading_pair
        self.commission = Decimal(commission)
        self.quote = Decimal(budget)
        self.base = Decimal("0")
        self.is_committed = False

        # some parameters
        self.stop_loss_factor = 0.05
        self.wix = wix

        # running data
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
        self.order_history = list()
        self.commit_price = None
        self.stop_loss = None

    def wallet(self, price) -> str:
        est_value = (1 - self.commission) * self.base * price + self.quote
        return f"{self.base:.8f} {self.base_symbol} + {self.quote} {self.quote_symbol} => {est_value} {self.quote_symbol}"

    @property
    def window(self):
        return self.FF[self.wix]

    @property
    def faster_window(self):
        return self.FF[self.wix - 1]

    @property
    def fast_window(self):
        return self.FF[self.wix - 1]

    @property
    def slow_window(self):
        return self.FF[self.wix + 1]

    @property
    def slower_window(self):
        return self.FF[self.wix + 1]

    def feed(self, kline_data):
        if not kline_data:
            print("Provided feed seems empty, skipped.")
            return

        if len(kline_data) > FULL_CYCLE:
            kline_data = kline_data[-FULL_CYCLE:]
            print(f"Provided feed was truncated to last {len(kline_data)}.")

        for dx in kline_data[-4:]:
            kx = KLinePoint(*dx)
            print(kx)

        klines = [CandleStick(x) for x in kline_data]
        new_df = pd.DataFrame(klines)
        new_df.index = pd.DatetimeIndex(new_df["open_time"])

        self.data = pd.concat([self.data.tail(FULL_CYCLE - new_df.size), new_df])

        # add indicators to dataframe
        self.data["slope"] = self.data["close"].diff()

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
            }
        )

    def buy_in(self, itime, price):
        spent = min(self.quote, 250)
        bought = (1 - self.commission) * spent / price

        self.quote -= spent
        self.base += bought
        self.order_history.append((FlipSignals.BUY, itime, price))

        self.spent = spent
        self.is_committed = True
        self.commit_price = Decimal(price)

        print(
            f"Bought {bought} {self.base_symbol} at {price} {self.quote_symbol}, spent {spent} {self.quote_symbol}",
            f"\n\tWallet: {self.wallet(price)}",
        )

    def sell_out(self, itime, price):
        sold = self.base
        amount = (1 - self.commission) * sold * price
        profit = amount - self.spent

        if profit < 0:
            print("Not selling without profit", profit, self.quote_symbol)
            print(self)
            return

        self.base -= sold
        self.quote += amount
        self.order_history.append((FlipSignals.SELL, itime, price))

        self.is_committed = False
        self.commit_price = None

        print(
            f" Sold  {sold} {self.base_symbol} at {price} {self.quote_symbol} for {profit} {self.quote_symbol} profit",
            f"\n\tWallet: {self.wallet(price)}",
        )

    def age_meta_signals(self, meta_signals):
        aged_meta_signals = dict()
        for key in meta_signals:
            ms, ttl = meta_signals[key]
            if ms != FlipSignals.HOLD:
                ttl -= 1
                if ttl == 0:
                    ms = FlipSignals.HOLD
                    ttl = None
            aged_meta_signals[key] = (ms, ttl)
        return aged_meta_signals

    def apply_money_flow(self, row, previous):
        if row["mfi"] >= self.MFI_HIGH:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif row["mfi"] <= self.MFI_LOW:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def apply_bollinger_bands(self, row, previous):
        tolerance = 0.001
        bb_high = row["bb_high"] * (1 - tolerance)
        bb_low = row["bb_low"] * (1 + tolerance)

        if float(row["high"]) >= bb_high and row["slope"] < 0:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif float(row["low"]) <= bb_low and row["slope"] > 0:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def apply_psar_signals(self, row, previous):
        if row.isna()["psar_up"]:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif row.isna()["psar_down"]:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def apply_stc_signals(self, row, previous):
        if row["stc"] < 25:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif row["stc"] > 75:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def pick_dominant_signal(self, meta_signals):
        mss = [ms for ms, _ in meta_signals.values()]
        bears = mss.count(FlipSignals.SELL)
        bulls = mss.count(FlipSignals.BUY)

        if bears > bulls and bears > 2:
            signal = FlipSignals.SELL
        elif bulls > bears and bulls > 2:
            signal = FlipSignals.BUY
        else:
            signal = FlipSignals.HOLD

        return signal

    def backtest(self):

        previous_meta = dict()

        for i, (_, row) in enumerate(self.data.iterrows()):
            if i <= self.slower_window:
                continue

            meta_signals = dict(
                # mfi=self.apply_money_flow(row, previous_meta.get("mfi")),
                # bb=self.apply_bollinger_bands(row, previous_meta.get("bb")),
                # psar=self.apply_psar_signals(row, previous_meta.get("psar")),
                # stc=self.apply_stc_signals(row, previous_meta.get("stc")),
            )

            aligned = self.pick_dominant_signal(meta_signals)
            if self.is_committed and aligned == FlipSignals.SELL:
                self.sell_out(i, row["close"])
            elif not self.is_committed and aligned == FlipSignals.BUY:
                self.buy_in(i, row["close"])

            previous_meta = self.age_meta_signals(meta_signals)

    def draw_chart(self):

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "volume": "float",
                "buy_volume": "float",
                "sell_volume": "float",
            }
        )

        extras = [
            mpf.make_addplot(df["stc"], color="royalblue", panel=2),
            # mpf.make_addplot(df["stc_slope"], color="darkorange", secondary_y=False, panel=2),
            # mpf.make_addplot(df["adx_plus"], color="dodgerblue", secondary_y=False, panel=2),
            # mpf.make_addplot(df["adx_minus"], color="darkorange", secondary_y=False, panel=2),
        ]

        fig, axes = mpf.plot(
            df,
            type="candle",
            addplot=extras,
            title=f"{self.base_symbol}/{self.quote_symbol}",
            volume=True,
            figsize=(13, 8),
            tight_layout=True,
            style="yahoo",
            warn_too_much_data=FULL_CYCLE,
            returnfig=True,
        )

        for ax in axes:
            ax.yaxis.tick_left()
            ax.yaxis.label.set_visible(False)
            ax.margins(x=0.1, y=0.1, tight=False)

        fig.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)

        plt.savefig("show.png", bbox_inches="tight", pad_inches=0.3)
        print("saved show.png")
