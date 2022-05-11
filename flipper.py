#!/usr/bin/env python3

import pickle
import os
import configparser
from binance.spot import Spot
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import namedtuple
from statistics import stdev, mean
from enum import Enum
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


CREDENTIALS_CACHE = "credentials.ini"


def init():
    credentials = configparser.ConfigParser()
    if os.path.isfile(CREDENTIALS_CACHE):
        credentials.read(CREDENTIALS_CACHE)
    else:
        empty = dict(api_key="", secret="")
        with open(CREDENTIALS_CACHE, "wt") as storage:
            credentials["binance"] = empty
            credentials.write(storage)
        raise RuntimeError(
            f"Created empty {CREDENTIALS_CACHE}, please fill in and run again."
        )

    assert "binance" in credentials.sections()
    client = Spot(**dict(credentials.items("binance")))

    return client


KLinePoint = namedtuple(
    "KLinePoint",
    [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "trades_count",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
        "ignore",
    ],
)


@dataclass
class PricePoint:
    open_time: datetime
    open: float
    close: float
    close_time: datetime

    def __init__(self, kline_data):
        kpoint = KLinePoint(*kline_data)
        self.open_time = datetime.fromtimestamp(kpoint.open_time // 1000)
        self.open = float(kpoint.open)
        self.close = float(kpoint.low)
        self.close_time = datetime.fromtimestamp(kpoint.close_time // 1000)


def load_last_24h(client, symbol):
    time_data = client.time()
    data = client.klines(symbol, "1m", limit=1000)
    return data


def discrete_derivatives(y, open):
    yy = [open] + y
    length = len(yy)
    first = [yy[i1] - yy[i0] for i0, i1 in zip(range(length - 1), range(1, length))]
    return first


def bollinger_bands(samples, window=7):
    # factor = 2.61803398875
    factor = 2.3
    # factor = 1.61803398875
    roll_mean = [samples[0]]
    low = [samples[0]]
    high = [samples[0]]
    roll_stdev = [0.0]

    for right in range(1, len(samples)):
        left = max(right - 20, 0)
        mm = mean(samples[left : right + 1])
        std = stdev(samples[left : right + 1])
        roll_mean.append(mm)
        low.append(mm - factor * std)
        high.append(mm + factor * std)
        roll_stdev.append(factor * std)
    return (roll_mean, low, high, roll_stdev)


def digest_signals(timeline, price, distance, bb_stdev):
    markers = []
    length = len(timeline)
    for i in range(length):
        if distance[i] >= bb_stdev[i]:
            markers.append((timeline[i], price[i], "SELL"))
        elif distance[i] <= -bb_stdev[i]:
            markers.append((timeline[i], price[i], "BUY"))

    return markers


class FlipSignals(Enum):
    HOLD = 0
    ENTRY = 1
    SELL = 2
    BUY = 3
    EXIT = 4


class Flipper:
    def __init__(self, symbol, budget, data):
        self.symbol = symbol
        self.budget = budget
        self.next_move = FlipSignals.ENTRY

        self.factor = 2.3
        self.window = 21

        assert len(data) > self.window, "Data feed is shorter than the window"

        first = PricePoint(data[0])
        klines = [KLinePoint(*x) for x in data]
        self.prices = [float(x.close) for x in klines]
        self.timeline = [datetime.fromtimestamp(x.close_time // 1000) for x in klines]

        self.bb_mean = [mean([first.open, first.close])]
        self.bb_stdev = [stdev([first.open, first.close])]
        self.bb_low = [min([first.open, first.close])]
        self.bb_high = [max([first.open, first.close])]
        self.bb_dist = [first.open - self.bb_mean[0]]

        for right in range(1, len(self.prices)):
            left = max(right - self.window, 0)
            mm = mean(self.prices[left : right + 1])
            std = stdev(self.prices[left : right + 1])

            self.bb_stdev.append(self.factor * std)
            self.bb_dist.append(self.prices[right] - mm)
            self.bb_mean.append(mm)
            self.bb_high.append(mm + self.factor * std)
            self.bb_low.append(mm - self.factor * std)

    def draw_trading_chart(self, limit=1000):
        since = len(self.prices) - limit
        fig, axes = plt.subplots(2, 1, sharex=True)

        axes[0].plot(
            self.timeline[since:], self.bb_high[since:], "r,:",
            self.timeline[since:], self.bb_low[since:], "g,:",
            self.timeline[since:], self.bb_mean[since:], "y,:",
            self.timeline[since:], self.prices[since:], "b,-",
            linewidth=0.5,
        )

        axes[0].xaxis.set_major_locator(mdates.HourLocator(interval=3))
        axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        axes[0].xaxis.set_minor_locator(mdates.HourLocator())
        axes[0].grid(visible=True, which="both")
        axes[0].set_title(self.symbol)

        for label in axes[0].get_xticklabels(which="major"):
            label.set(rotation=45, horizontalalignment="right")

        bb_stdev_opp = [-x for x in self.bb_stdev[since:]]
        axes[1].plot(
            self.timeline[since:], self.bb_stdev[since:], "r,:",
            self.timeline[since:], bb_stdev_opp,  "g,:",
            self.timeline[since:], self.bb_dist[since:], "m,-",
            linewidth=0.5,
        )
        axes[1].set_ylabel("distance")
        axes[1].grid(visible=True, which="both")

        timed = self.timeline[-1].strftime("%Y-%m-%d_%H:%M:%S")
        plt.savefig(f"{self.symbol}_chart_{timed}.png", dpi=600)

    def feed_ticker(self, data):
        # takes in a new kline, updates stats and returns a signal
        return FlipSignals.HOLD


def magic_graphs(data, symbol):
    klines = [KLinePoint(*x) for x in data]
    timeline = [datetime.fromtimestamp(x.close_time // 1000) for x in klines]
    price = [float(x.close) for x in klines]
    bb_mean, bb_high, bb_low, bb_stdev = bollinger_bands(price)

    fig, axes = plt.subplots(2, 1, sharex=True)

    axes[0].plot(
        timeline,
        price,
        "b.-",
        # timeline, bb_high, "r,-",
        # timeline, bb_low, "g,-",
        timeline,
        bb_mean,
        "y,-",
    )
    axes[0].xaxis.set_major_locator(mdates.HourLocator(interval=2))
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[0].xaxis.set_minor_locator(mdates.MinuteLocator(interval=10))
    axes[0].grid(visible=True, which="both")
    axes[0].set_title(symbol)

    for label in axes[0].get_xticklabels(which="major"):
        label.set(rotation=45, horizontalalignment="right")

    distance = [p - m for p, m in zip(price, bb_mean)]
    bb_stdev_opp = [-x for x in bb_stdev]
    axes[1].plot(
        timeline,
        distance,
        "m.:",
        timeline,
        bb_stdev,
        "g,--",
        timeline,
        bb_stdev_opp,
        "r,--",
    )
    axes[1].set_ylabel("distance")
    axes[1].grid(visible=True, which="both")

    signals = digest_signals(timeline, price, distance, bb_stdev)
    for sig in signals:
        x, y, msg = sig

        axes[0].annotate(
            msg,
            xy=(x, y),
            fontsize="large",
            xytext=((0.0, +34.0) if msg == "SELL" else (0.0, -34.0)),
            textcoords="offset pixels",
            color="green" if msg == "SELL" else "red",
            horizontalalignment="center",
            verticalalignment="center",
            arrowprops=dict(arrowstyle="->"),
        )

    plt.show()


def main(client):

    symbol = "ETHBTC"
    cache_file = f"{symbol}.dat"
    data = None

    if os.path.isfile(cache_file):
        print("Using local cache...")
        with open(cache_file, "rb") as data_file:
            data = pickle.load(data_file)
    else:
        print("Reading last 24h")
        data = load_last_24h(client, symbol)
        with open(cache_file, "wb") as data_file:
            pickle.dump(data, data_file)
            print("cached to", cache_file)

    # magic_graphs(data, symbol)
    budget = "0.002"
    flippy = Flipper(symbol, budget, data)
    flippy.draw_trading_chart(limit=1000)


if __name__ == "__main__":
    client = init()
    main(client)
