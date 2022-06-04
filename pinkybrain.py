from decimal import Decimal
import pandas as pd
import mplfinance as mpf
from ta.volatility import BollingerBands
from ta.momentum import tsi
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
    MFI_LOW = 27
    TSI_TOLERANCE = 10
    VELOCITY_TOLERANCE = 8

    def __init__(self, trading_pair, budget, commission, wix):
        self.base_symbol, self.quote_symbol = trading_pair
        self.commission = Decimal(commission)
        self.quote = Decimal(budget)
        self.base = Decimal("0")
        self.is_committed = False

        # some parameters
        self.stop_loss_factor = commission * 4
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
        self.data["velocity"] = self.data["close"].diff()

        bb = BollingerBands(close=self.data["close"], window=self.window)
        self.data["bb_ma"] = bb.bollinger_mavg()
        self.data["bb_high"] = bb.bollinger_hband()
        self.data["bb_low"] = bb.bollinger_lband()

        self.data["tsi"] = tsi(
            close=self.data["close"],
            window_fast=self.window,
            window_slow=self.slow_window,
        )
        self.data["trend_velocity"] = self.data["tsi"].diff()

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
            }
        )
        self.data["mfi"] = money_flow_index(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            volume=df["volume"],
            window=self.window,
        )

    def buy_in(self, itime, price):
        self.is_committed = True

        spent = self.quote
        bought = (1 - self.commission) * self.quote / price

        self.quote -= spent
        self.base += bought
        self.order_history.append((FlipSignals.BUY, itime, price))

        self.spent = spent
        self.commit_price = Decimal(price)
        self.stop_loss = price * (1 - self.stop_loss_factor)

        print(
            f"Bought {bought} {self.base_symbol} at {price} {self.quote_symbol}, spent {spent} {self.quote_symbol}]"
        )

    def sell_out(self, itime, price):
        self.is_committed = False

        sold = self.base
        amount = (1 - self.commission) * sold * price

        self.base -= sold
        self.quote += amount
        self.order_history.append((FlipSignals.SELL, itime, price))

        self.commit_price = None
        self.stop_loss = None

        profit = amount - self.spent

        print(
            f" Sold  {sold} {self.base_symbol} at {price} {self.quote_symbol} for {profit} {self.quote_symbol} profit [Wallet: {self.quote} {self.quote_symbol}]"
        )
        print(self)

    def backtest(self):
        next_move = None
        tolerance = 0.0015
        for i, (_, row) in enumerate(self.data.iterrows()):
            price = float(row["low"])
            if not self.is_committed:
                if (
                    next_move == FlipSignals.BUY
                    and (row["trend_velocity"] + self.VELOCITY_TOLERANCE) > 0
                ):
                    self.buy_in(i, row["close"])
                    next_move = None
                elif (
                    next_move is None
                    and row["mfi"] < self.MFI_LOW
                    and row["tsi"] > -self.TSI_TOLERANCE
                    and price <= (row["bb_low"] * (1 + tolerance))
                ):
                    if (row["trend_velocity"] + self.VELOCITY_TOLERANCE) > 0:
                        self.buy_in(i, row["close"])
                    else:
                        next_move = FlipSignals.BUY
            else:
                if float(row["close"]) <= self.stop_loss:
                    print("WARNING: Stop loss activated.")
                    self.sell_out(i, row["close"])
                    next_move = None
                    continue

                if (
                    next_move == FlipSignals.SELL
                    # and (row["trend_velocity"] - self.VELOCITY_TOLERANCE) < 0
                    and row["velocity"] <= 0
                ):
                    self.sell_out(i, row["close"])
                    next_move = None
                elif (
                    next_move is None
                    and row["mfi"] > self.MFI_HIGH
                    and price >= (row["bb_high"] * (1 - tolerance))
                    and row["velocity"] <= 0
                ):
                    if (row["trend_velocity"] - self.VELOCITY_TOLERANCE) > 0:
                        self.sell_out(i, row["close"])
                    else:
                        next_move = FlipSignals.SELL

    def draw_chart(self):

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
            }
        )

        df["tsi-high"] = self.TSI_TOLERANCE
        df["tsi-low"] = -self.TSI_TOLERANCE

        df["mfi-high"] = self.MFI_HIGH
        df["mfi-low"] = self.MFI_LOW

        extras = [
            mpf.make_addplot(df["bb_high"], color="olive", secondary_y=False, alpha=0.35),
            mpf.make_addplot(df["bb_ma"], color="blue", secondary_y=False, alpha=0.35),
            mpf.make_addplot(df["bb_low"], color="brown", secondary_y=False, alpha=0.35),

            mpf.make_addplot(df["tsi"], color="red", secondary_y=False, panel=1),
            mpf.make_addplot(
                df["tsi-high"], color="olive", alpha=0.35, secondary_y=False, panel=1
            ),
            mpf.make_addplot(
                df["tsi-low"], color="brown", alpha=0.35, secondary_y=False, panel=1
            ),
            mpf.make_addplot(
                df["trend_velocity"], color="pink", secondary_y=False, panel=1
            ),
            mpf.make_addplot(df["mfi"], color="red", secondary_y=False, panel=2),
            mpf.make_addplot(
                df["mfi-high"], color="olive", alpha=0.35, secondary_y=False, panel=2
            ),
            mpf.make_addplot(
                df["mfi-low"], color="brown", alpha=0.35, secondary_y=False, panel=2
            ),
        ]

        fig, axes = mpf.plot(
            df,
            type="candle",
            addplot=extras,
            title=f"{self.base_symbol}/{self.quote_symbol}",
            # volume=True,
            # figsize=(15.7, 5.5),
            tight_layout=True,
            style="yahoo",
            warn_too_much_data=1000,
            returnfig=True,
        )

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
            fig.axes[2].annotate(
                signal.name,
                xy=(time, df["tsi"].iloc[time]),
                fontsize="small",
                xytext=((-0, +55.0) if signal == FlipSignals.SELL else (-0, -55.0)),
                textcoords="offset pixels",
                color="green" if signal == FlipSignals.SELL else "red",
                horizontalalignment="center",
                verticalalignment="center",
                arrowprops=dict(arrowstyle="->"),
            )

        mpf.show()
