from decimal import Decimal
import pandas as pd
import mplfinance as mpf
from matplotlib import pyplot as plt
from ta.volatility import BollingerBands, ulcer_index
from ta.momentum import awesome_oscillator
from ta.volume import money_flow_index
from metaflip import CandleStick, FlipSignals


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
    MFI_HIGH = 65
    MFI_LOW = 35

    def __init__(self, trading_pair, budget, commission, wix):
        self.base_symbol, self.quote_symbol = trading_pair
        self.commission = Decimal(commission)
        self.quote = Decimal(budget)
        self.base = Decimal("0")
        self.is_committed = False

        # some parameters
        self.stop_loss_factor = commission * 8
        self.wix = wix

        # running data
        self.data = pd.DataFrame()
        self.order_history = list()
        self.commit_price = None
        self.stop_loss = None

    def __repr__(self) -> str:
        last_price = self.data["close"].iloc[-1]
        est_value = (1 - self.commission) * self.base * last_price + self.quote
        return f"{self.base:.8f} {self.base_symbol} + {self.quote} {self.quote_symbol} => {est_value} {self.quote_symbol}"

    @property
    def window(self):
        return self.FF[self.wix]

    @property
    def fast_window(self):
        return self.FF[self.wix - 1]

    @property
    def slow_window(self):
        return self.FF[self.wix + 1]

    def feed(self, kline_data):
        if not kline_data:
            print(".: Provided feed seems empty, skipped.")
            return

        if len(kline_data) > 1000:
            print(".: Provided feed was truncated to last 1000.")
            kline_data = kline_data[-1000:]

        klines = [CandleStick(x) for x in kline_data]
        new_df = pd.DataFrame(klines)
        new_df.index = pd.DatetimeIndex(new_df["close_time"])

        self.data = pd.concat([self.data.tail(1000 - new_df.size), new_df])

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

        bb = BollingerBands(close=self.data["close"], window=self.window)
        self.data["bb_ma"] = bb.bollinger_mavg()
        self.data["bb_high"] = bb.bollinger_hband()
        self.data["bb_low"] = bb.bollinger_lband()

        self.data["ulcer"] = ulcer_index(close=df["close"], window=self.window)
        self.data["ulcer_slope"] = self.data["ulcer"].diff()

        self.data["mfi"] = money_flow_index(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            volume=df["volume"],
            window=self.window,
        )

    def buy_in(self, itime, price):
        spent = self.quote
        bought = (1 - self.commission) * self.quote / price

        self.quote -= spent
        self.base += bought
        self.order_history.append((FlipSignals.BUY, itime, price))

        self.spent = spent
        self.is_committed = True
        self.commit_price = Decimal(price)
        self.stop_loss = price * (1 - self.stop_loss_factor)

        print(
            f"Bought {bought} {self.base_symbol} at {price} {self.quote_symbol}, spent {spent} {self.quote_symbol}]"
        )

    def sell_out(self, itime, price, stop_loss=False):
        sold = self.base
        amount = (1 - self.commission) * sold * price
        profit = amount - self.spent
        if profit < 0 and not stop_loss:
            print("Not selling without profit", profit, self.quote_symbol)
            return

        self.base -= sold
        self.quote += amount
        self.order_history.append((FlipSignals.SELL, itime, price))

        self.is_committed = False
        self.commit_price = None
        self.stop_loss = None

        print(
            f" Sold  {sold} {self.base_symbol} at {price} {self.quote_symbol} for {profit} {self.quote_symbol} profit [Wallet: {self.quote} {self.quote_symbol}]"
        )

    def backtest(self):

        TTL = 4
        meta_signals = dict(
            bb=(FlipSignals.HOLD, None),
            mfi=(FlipSignals.HOLD, None),
            ulcer=(FlipSignals.HOLD, None),
        )

        def age_meta_signal(key):
            ms, ttl = meta_signals[key]
            if ms != FlipSignals.HOLD:
                ttl -= 1
                meta_signals[key] = (ms, ttl) if ttl else (FlipSignals.HOLD, None)

        def meta_signals_are_aligned():
            mss = set(ms for ms, ttl in meta_signals.values())
            return mss.pop() if len(mss) == 1 else None

        tolerance = 0.001

        for i, (_, row) in enumerate(self.data.iterrows()):
            # process technical indicators
            if row["mfi"] >= self.MFI_HIGH:
                meta_signals["mfi"] = (FlipSignals.SELL, TTL)
            elif row["mfi"] <=  self.MFI_LOW:
                meta_signals["mfi"] = (FlipSignals.BUY, TTL)
            else:
                age_meta_signal("mfi")

            if row["ulcer_slope"] > -0.01:
                meta_signals["ulcer"] = (FlipSignals.BUY, TTL)
            elif row["ulcer_slope"] < +0.01:
                meta_signals["ulcer"] = (FlipSignals.SELL, TTL)
            else:
                age_meta_signal("ulcer")

            if float(row["high"]) >= row["bb_high"] * (1-tolerance) and row["slope"] < 0:
                meta_signals["bb"] = (FlipSignals.SELL, TTL)
            elif float(row["low"]) <= row["bb_low"] * (1+tolerance) and row["slope"] > 0:
                meta_signals["bb"] = (FlipSignals.BUY, TTL)
            else:
                age_meta_signal("bb")

            signal = meta_signals_are_aligned()

            if self.is_committed:
                if row["close"] <= self.stop_loss:
                    print("WARNING: Stop loss activated.")
                    self.sell_out(i, row["close"], stop_loss=True)
                elif signal == FlipSignals.SELL:
                    self.sell_out(i, row["close"])
            else:
                if signal == FlipSignals.BUY:
                    self.buy_in(i, row["close"])

    def draw_chart(self):

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
            }
        )

        ulcer_colors = ["red" if s > 0 else "green" for s in df["ulcer_slope"]]

        df["mfi-high"] = self.MFI_HIGH
        df["mfi-low"] = self.MFI_LOW

        extras = [
            mpf.make_addplot(df["bb_high"], color="olive", secondary_y=False, alpha=0.35),
            mpf.make_addplot(df["bb_ma"], color="blue", secondary_y=False, alpha=0.35),
            mpf.make_addplot(df["bb_low"], color="brown", secondary_y=False, alpha=0.35),

            mpf.make_addplot(df["mfi"], color="red", secondary_y=False, panel=1),
            mpf.make_addplot(
                df["mfi-high"], color="olive", alpha=0.35, secondary_y=False, panel=1
            ),
            mpf.make_addplot(
                df["mfi-low"], color="brown", alpha=0.35, secondary_y=False, panel=1
            ),

            mpf.make_addplot(df["ulcer"], type="bar", color=ulcer_colors, panel=2),
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
            warn_too_much_data=1000,
            returnfig=True,
        )

        for ax in axes:
            ax.yaxis.tick_left()
            ax.yaxis.label.set_visible(False)
            ax.margins(0.0)

        for signal, time, price in self.order_history:
            fig.axes[0].annotate(
                signal.name,
                xy=(time, price),
                fontsize="small",
                xytext=((-0, +55.0) if signal == FlipSignals.SELL else (-0, -55.0)),
                textcoords="offset pixels",
                color="green" if signal == FlipSignals.SELL else "red",
                horizontalalignment="center",
                verticalalignment="center",
                arrowprops=dict(arrowstyle="->"),
            )

        fig.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)
        # plt.savefig('image.png', bbox_inches='tight', pad_inches = 0.3)
        plt.show()
