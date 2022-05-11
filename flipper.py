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
import schedule
import time


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
        self.follow_up = None

        # self.factor = 2.61803398875
        # self.factor = 2.3
        self.factor = 1.61803398875

        self.window = 7

        assert len(data) > self.window, "Data feed is shorter than the window"

        first = PricePoint(data[0])
        klines = [KLinePoint(*x) for x in data]
        self.prices = [float(x.close) for x in klines]
        self.timeline = [datetime.fromtimestamp(x.close_time // 1000) for x in klines]
        self.velocity = [first.close - first.open]

        self.bb_mean = [mean([first.open, first.close])]
        self.bb_stdev = [stdev([first.open, first.close])]
        self.bb_low = [min([first.open, first.close])]
        self.bb_high = [max([first.open, first.close])]

        for right in range(1, len(self.prices)):
            left = max(right - self.window, 0)
            mm = mean(self.prices[left : right + 1])
            std = stdev(self.prices[left : right + 1])

            self.bb_stdev.append(self.factor * std)
            self.bb_mean.append(mm)
            self.bb_high.append(mm + self.factor * std)
            self.bb_low.append(mm - self.factor * std)
            self.velocity.append(self.prices[right] - self.prices[right - 1])

        self.last_kline = klines[-1]


    def draw_trading_chart(self, limit=1000):
        since = len(self.prices) - limit
        fig, axes = plt.subplots(1, 1, sharex=True)

        axes.plot(
            self.timeline[since:], self.bb_high[since:], "r,:",
            self.timeline[since:], self.bb_low[since:], "g,:",
            self.timeline[since:], self.bb_mean[since:], "y,:",
            self.timeline[since:], self.prices[since:], "b,-",
            linewidth=0.5,
        )

        axes.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        axes.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        axes.xaxis.set_minor_locator(mdates.HourLocator())
        axes.grid(visible=True, which="both")
        axes.set_title(f"{self.symbol}")

        for label in axes.get_xticklabels(which="major"):
            label.set(rotation=45, horizontalalignment="right")

        timed = self.timeline[-1].strftime("%Y-%m-%d_%H:%M:%S")
        plt.savefig(f"{self.symbol}_chart_{timed}.png", dpi=600)
        plt.close()

    @property
    def last_price(self):
        return float(self.last_kline.close)

    @property
    def last_timestamp(self):
        return self.last_kline.close_time

    def feed_klines(self, data):
        if not data:
            print("provided data seems empty, feeding skipped.")
            return

        start_at = len(self.prices)
        klines = [KLinePoint(*x) for x in data]
        self.prices.extend([float(x.close) for x in klines])
        self.timeline.extend([datetime.fromtimestamp(x.close_time // 1000) for x in klines])

        cnt = 0
        for right in range(start_at, len(self.prices)):
            left = max(right - self.window, 0)
            mm = mean(self.prices[left : right + 1])
            std = stdev(self.prices[left : right + 1])

            self.bb_stdev.append(self.factor * std)
            self.bb_mean.append(mm)
            self.bb_high.append(mm + self.factor * std)
            self.bb_low.append(mm - self.factor * std)
            self.velocity.append(self.prices[right] - self.prices[right - 1])
            cnt += 1

        self.last_kline = klines[-1]

        # trigger signal base on last point only
        price = self.prices[-1]
        mm = self.bb_mean[-1]
        mdev = self.bb_stdev[-1]
        velocity = self.velocity[-1]
        dist = price - mm

        signal = FlipSignals.HOLD
        if self.follow_up in {FlipSignals.ENTRY, FlipSignals.BUY}:
            if velocity >= 0:
                signal = FlipSignals.BUY
                self.follow_up = None
        elif self.follow_up in {FlipSignals.SELL}:
            if velocity <= 0:
                signal = FlipSignals.SELL
                self.follow_up = None
        else:
            if dist >= mdev:
                if velocity >= 0:
                    self.follow_up = FlipSignals.SELL
                else:
                    signal = FlipSignals.SELL
            elif dist <= -mdev:
                if velocity <= 0:
                    self.follow_up = FlipSignals.BUY
                else:
                    signal = FlipSignals.BUY

        return signal


def magic_graphs(data, symbol):
    klines = [KLinePoint(*x) for x in data]
    timeline = [datetime.fromtimestamp(x.close_time // 1000) for x in klines]
    price = [float(x.close) for x in klines]
    bb_mean, bb_high, bb_low, bb_stdev = bollinger_bands(price)

    fig, axes = plt.subplots(2, 1, sharex=True)

    axes[0].plot(
        timeline, price, "b.-",
        # timeline, bb_high, "r,-",
        # timeline, bb_low, "g,-",
        timeline, bb_mean, "y,-",
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
        timeline, distance, "m.:",
        timeline, bb_stdev, "g,--",
        timeline, bb_stdev_opp, "r,--",
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


symbol = "BTCEUR"
price_cache = f"{symbol}_price.dat"
orders_cache = f"{symbol}_orders.dat"
data = None
flippy = None
order_history = list()
holdings = 0.003521
currency = 0.0

def tick():
    global currency
    global holdings
    global order_history

    since = flippy.last_timestamp
    new_data = client.klines(symbol=symbol, interval="1m", startTime=since)
    print(f"Got {len(new_data)} {symbol} entries")

    if (new_data):
        signal = flippy.feed_klines(new_data)
        print(f"Flippy recommends {signal}")

        if signal == FlipSignals.BUY and currency >= 25:
            bought = (25.0 / flippy.last_price) * 0.999
            currency -= 25.0
            holdings += bought
            print(f"Bought {bought:.6f} at {flippy.last_price:.6f}.")
            total = holdings * flippy.last_price + currency
            print(f"\t .. Wallet .. {holdings:.6f} and {currency:.6f}, valued at {total:.6f}")
        elif signal == FlipSignals.SELL and holdings > 0:
            sold = (25.0 / flippy.last_price)
            if (sold <= holdings):
                holdings -= sold
                currency += sold * flippy.last_price * 0.999
                print(f"Sold {sold:.6f} at {flippy.last_price:.6f}.")
            else:
                print(f"cannot sell {sold:.6f}, current holdings {holdings:.6f}")
            total = holdings * flippy.last_price + currency
            print(f"\t .. Wallet .. {holdings:.6f} and {currency:.6f}, valued at {total:.6f}")


        data.extend(new_data)
        with open(price_cache, "wb") as data_file:
            pickle.dump(data, data_file)

        if signal != FlipSignals.HOLD:

            order = dict(signal=signal, price=flippy.last_price, time=flippy.last_timestamp)
            order_history.append(order)
            with open(orders_cache, "wb") as data_file:
                pickle.dump(order_history, data_file)

    flippy.draw_trading_chart(limit=200)


def main(client):
    global flippy  ## horrible I know
    global data
    global order_history

    # load price history
    if os.path.isfile(price_cache):
        print(f"Using local cache ({price_cache})...")
        with open(price_cache, "rb") as data_file:
            data = pickle.load(data_file)
    else:
        print("Reading last 24h")
        data = load_last_24h(client, symbol)
        with open(price_cache, "wb") as data_file:
            pickle.dump(data, data_file)
            print("cached to", price_cache)

    # load order history
    if os.path.isfile(orders_cache):
        print(f"Using local cache ({orders_cache})...")
        with open(orders_cache, "rb") as data_file:
            order_history = pickle.load(data_file)

    budget = "0.002"
    flippy = Flipper(symbol, budget, data)

    schedule.every().minute.at(":13").do(tick)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    client = init()
    main(client)
