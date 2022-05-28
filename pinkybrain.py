from collections import deque
from decimal import Decimal
from heapq import heappush, heappop

import pandas as pd
import mplfinance as mpf

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

        df["stdev"] = df["typical_price"].rolling(8).std(ddof=0)
        df["sma"] = df["typical_price"].rolling(8).mean()
        df["top"] = df["sma"] + 2 * df["stdev"]
        df["bottom"] = df["sma"] - 2 * df["stdev"]
        df["velocity"] = df["sma"].diff()

        trends = dict(
            colors=["r", "g"],
            # linewidths=5,
            alpha=0.28,
            alines=[list(), list()]
        )
        for _, row in df.iterrows():
            if float(row["low"]) <= row["bottom"]:
                trends["alines"][0].append((row["close_time"], float(row["low"])))
            if float(row["high"]) >= row["top"]:
                trends["alines"][1].append((row["close_time"], float(row["high"])))

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
        extras = [
            mpf.make_addplot(df["typical_price"]),
            # mpf.make_addplot(df["top"], color="green"),
            # mpf.make_addplot(df["bottom"], color="red"),
        ]
        mpf.plot(
            df,
            type="candle",
            addplot=extras,
            alines=trends,
            volume=True,
            warn_too_much_data=1000,
        )
