from collections import deque
from decimal import Decimal
from heapq import heappush, heappop

import pandas as pd
import mplfinance as mpf
from matplotlib import pyplot as plt
from matplotlib import ticker

from metaflip import CandleStick


class PinkyBrain:
    def __init__(self, trading_pair, budget, commission):
        self.base_symbol, self.quote_symbol = trading_pair
        self.commission = Decimal(commission)
        self.budget = Decimal(budget)
        self.quote = Decimal(budget)
        self.base = Decimal(0)

    def __repr__(self) -> str:
        return f"{self.base} {self.base_symbol} on {self.quote} {self.quote_symbol}"

    def feed(self, kline_data):
        if not kline_data:
            print(".: Provided feed seems empty, skipped.")
            return

        klines = [CandleStick(x) for x in kline_data]
        df = pd.DataFrame(klines)
        df.index = pd.DatetimeIndex(df["close_time"])

        window = 13
        factor = 2

        df["stdev"] = df["typical_price"].rolling(window).std(ddof=0)
        df["sma"] = df["typical_price"].rolling(window).mean()
        df["top"] = df["sma"] + factor * df["stdev"]
        df["bottom"] = df["sma"] - factor * df["stdev"]
        df["diff"] = df["close"].diff()

        df = df.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "top": "float",
                "bottom": "float",
            }
        )


        trend_roots = dict(
            alines=[list(), list()],
            colors=["r", "g"],
            linewidths=1,
            alpha=0.21,
        )

        for (_, previous), (_, current) in zip(df[:-1].iterrows(),df[1:].iterrows()):
            if previous["diff"] < 0 and current["diff"] > 0:
                trend_roots["alines"][0].append((current["close_time"], current["low"]))
            elif previous["diff"] > 0 and current["diff"] < 0:
                trend_roots["alines"][1].append((current["close_time"], current["high"]))

        extras = [
            # mpf.make_addplot(df["typical_price"]),
            mpf.make_addplot(df["top"], color="olive"),
            mpf.make_addplot(df["bottom"], color="brown"),
            # mpf.make_addplot(df["diff"], color="green", panel=1),
        ]

        fig, axes = mpf.plot(
            df,
            type="candle",
            addplot=extras,
            alines=trend_roots,
            title=f"{self.base_symbol}/{self.quote_symbol}",
            volume=True,
            figsize=(15.7, 5.5),
            tight_layout=True,
            style="yahoo",
            warn_too_much_data=1000,
            returnfig=True,
        )
        # axes[0].set_yscale("log")
        # axes[0].yaxis.set_major_formatter(ticker.ScalarFormatter())
        # axes[0].yaxis.set_minor_formatter(ticker.ScalarFormatter())
        plt.show()
