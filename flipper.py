#!/usr/bin/env python3

import os
import configparser
from binance.spot import Spot
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import namedtuple
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
    since = time_data["serverTime"] - 24 * 60 * 60 * 1000  # 24h ago

    # pick the first 1000 points batch
    klines = client.klines(symbol, "1m", startTime=since, limit=1000)
    data = [CoinPoint(x) for x in klines]

    # pick the remaining 440 points batch
    last_kpoint = KLinePoint(*klines[-1])
    klines_partial = client.klines(symbol, "1m", startTime=last_kpoint.close_time)
    data.extend([CoinPoint(x) for x in klines_partial])
    assert len(data) == 1440

    return data


def magic_graphs(data, symbol):
    fig, ax = plt.subplots()

    timeline = [x.open_time for x in data]
    price = [x.open for x in data]

    ax.plot(timeline, price, linewidth=2.0)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_locator(mdates.HourLocator())
    # ax.xaxis.set_minor_formatter(mdates.DateFormatter('%H:%M'))
    ax.grid(visible=True, which="both")

    ax.set_ylabel("Price")
    ax.set_title(symbol)

    for label in ax.get_xticklabels(which="major"):
        label.set(rotation=45, horizontalalignment="right")

    plt.show()


def main(client):

    symbol = "ETHBTC"
    cache_file = "test.dat"
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
