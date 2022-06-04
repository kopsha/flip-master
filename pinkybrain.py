from collections import deque
from decimal import Decimal
from heapq import heappush, heappop

import pandas as pd
import mplfinance as mpf
from matplotlib import pyplot as plt
from matplotlib import dates as mdates

from metaflip import CandleStick, FlipSignals


class PinkyTracker:
    def __init__(self, trading_pair, budget, commission, window, factor):
        self.base_symbol, self.quote_symbol = trading_pair
        self.commission = Decimal(commission)
        self.budget = Decimal(budget)
        self.quote = Decimal(budget)
        self.base = Decimal(0)
        self.is_committed = False
        self.order_history = list()

        self.window = int(window)
        self.factor = Decimal(factor)
        self.ff = float(factor)

        self.data = pd.DataFrame()

    def __repr__(self) -> str:
        return f"{self.base} {self.base_symbol} on {self.quote} {self.quote_symbol}"

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

        self.data["velocity"] = self.data["close"] - self.data["open"]
        self.data["stdev"] = self.data["close"].rolling(self.window).std(ddof=0)
        self.data["sma"] = self.data["close"].rolling(self.window * 2 + 1).mean()
        self.data["ema"] = self.data["close"].ewm(span=self.window).mean()
        self.data["top"] = self.data["ema"] + self.ff * self.data["stdev"]
        self.data["bottom"] = self.data["ema"] - self.ff * self.data["stdev"]
        self.data["d_ema"] = self.data["ema"].diff()
        self.data["d_sma"] = self.data["sma"].diff()

    def print_balance(self, price):
        est_value = (1 - self.commission) * self.base * price + self.quote
        print(f"{self.base:.8f} {self.base_symbol} + {self.quote} {self.quote_symbol} => {est_value} {self.quote_symbol}")

    def buy_in(self, itime, price):
        self.is_committed = True

        amount = self.quote
        bought = (1 - self.commission) * self.quote / price

        self.quote -= amount
        self.base += bought
        self.order_history.append((FlipSignals.BUY, itime, price))

        print(
            f"Bought {bought} {self.base_symbol} at {price} {self.quote_symbol} [{amount} {self.quote_symbol}]"
        )
        # self.print_balance(price)

    def sell_out(self, itime, price):
        self.is_committed = False

        sold = self.base
        amount = (1 - self.commission) * sold * price

        self.base -= sold
        self.quote += amount

        self.order_history.append((FlipSignals.SELL, itime, price))

        print(
            f" Sold  {sold} {self.base_symbol} at {price} {self.quote_symbol} [{amount} {self.quote_symbol}]"
        )
        # self.print_balance(price)

    def backtest(self):
        next_move = None
        for i, (_, row) in enumerate(self.data.iterrows()):
            bottom = Decimal(row["bottom"])
            top = Decimal(row["top"])
            if not self.is_committed:
                # look for a good entry point
                if next_move == FlipSignals.BUY and row["velocity"] >= 0:
                    self.buy_in(i, row["close"])
                    next_move = None
                elif next_move is None and row["low"].compare(bottom) in {Decimal("0"), Decimal("-1")}:
                    if row["velocity"] <= 0:
                        next_move = FlipSignals.BUY
                    else:
                        self.buy_in(i, row["close"])
            else:
                # look for the next exit point
                if next_move == FlipSignals.SELL and row["velocity"] <= 0:
                    self.sell_out(i, row["close"])
                    next_move = None
                elif next_move is None and row["high"].compare(top) in {Decimal("0"), Decimal("1")}:
                    if row["velocity"] >= 0:
                        next_move = FlipSignals.SELL
                    else:
                        self.sell_out(i, row["close"])

    def draw_chart(self):

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "top": "float",
                "bottom": "float",
            }
        )

        extras = [
            mpf.make_addplot(df["top"], color="olive"),
            mpf.make_addplot(df["sma"], color="blue"),
            mpf.make_addplot(df["ema"], color="red"),
            mpf.make_addplot(df["bottom"], color="brown"),
        ]

        fig, axes = mpf.plot(
            df,
            type="candle",
            addplot=extras,
            title=f"{self.base_symbol}/{self.quote_symbol}",
            # volume=True,
            figsize=(15.7, 5.5),
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
                xytext=((-25.0, +55.0) if signal == FlipSignals.SELL else (-25.0, -55.0)),
                textcoords="offset pixels",
                color="green" if signal == FlipSignals.SELL else "red",
                horizontalalignment="center",
                verticalalignment="center",
                arrowprops=dict(arrowstyle="->"),
            )

        mpf.show()
