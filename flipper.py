#!/usr/bin/env python3

import os
import configparser
from binance.spot import Spot
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import namedtuple
from statistics import stdev, mean
import pickle
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
class CoinPoint:
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
    # load the last 24h
    time_data = client.time()
    since = time_data["serverTime"] - 4 * 60 * 60 * 1000  # 24h ago

    # pick the first 1000 points batch
    klines = client.klines(symbol, "1m", startTime=since, limit=1000)
    data = [CoinPoint(x) for x in klines]

    # pick the remaining 440 points batch
    last_kpoint = KLinePoint(*klines[-1])
    klines_partial = client.klines(symbol, "1m", startTime=last_kpoint.close_time)
    data.extend([CoinPoint(x) for x in klines_partial])
    print("got", len(data), "datapoints")

    # assert len(data) == 1440

    return data


def discrete_derivatives(y, open):
    yy = [open] + y
    length = len(yy)
    first = [yy[i1] - yy[i0] for i0, i1 in zip(range(length - 1), range(1, length))]
    return first


def bollinger_bands(samples, window=7, factor=2.4):
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


def magic_graphs(data, symbol):
    timeline = [x.open_time for x in data]
    price = [x.close for x in data]
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

    symbol = "LUNABTC"
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

    magic_graphs(data, symbol)


if __name__ == "__main__":
    client = init()
    main(client)
