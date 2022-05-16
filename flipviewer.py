#!/usr/bin/env python3

import pickle
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from statistics import mean, stdev
from metaflip import FlipSignals, KLinePoint, PricePoint


class FlipViewer:
    def __init__(self, symbol):
        self.symbol = symbol
        # self.factor = 1.61803398875
        self.factor = 2.2
        self.window = 14

        # load price history
        price_data = None
        prices_cache = f"{symbol}_price.dat"
        if os.path.isfile(prices_cache):
            print(f"Loading ({prices_cache})...")
            with open(prices_cache, "rb") as data_file:
                price_data = pickle.load(data_file)
        else:
            raise FileNotFoundError(f"Cannot open {prices_cache} for reading.")

        assert len(price_data) > self.window, "Data feed is shorter than the window"

        first = PricePoint(price_data[0])
        klines = [KLinePoint(*x) for x in price_data]

        cuttoff = 1652446800000
        klines = list(filter(lambda x: x.close_time >= cuttoff, klines))

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

        # load order history
        self.orders = None
        orders_cache = f"{symbol}_orders.dat"
        if os.path.isfile(orders_cache):
            print(f"Using local cache ({orders_cache})...")
            with open(orders_cache, "rb") as data_file:
                self.orders = pickle.load(data_file)

        # cutoff up to a timestamp
        self.orders = list(filter(lambda x: x["time"] >= cuttoff, self.orders))

    def draw_trading_chart(self):
        fig, axes = plt.subplots(1, 1, sharex=True)

        axes.plot(
            self.timeline,
            self.bb_high,
            "r,:",
            self.timeline,
            self.bb_low,
            "g,:",
            self.timeline,
            self.prices,
            "b,-",
            linewidth=0.5,
        )

        axes.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        axes.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        axes.xaxis.set_minor_locator(mdates.HourLocator())
        axes.grid(visible=True, which="both")
        axes.set_title(f"{self.symbol}")

        for label in axes.get_xticklabels(which="major"):
            label.set(rotation=45, horizontalalignment="right")

        for order in self.orders:
            signal, price, timestamp = order.values()
            mark_time = datetime.fromtimestamp(timestamp // 1000)
            axes.annotate(
                signal.name,
                xy=(mark_time, price),
                fontsize="large",
                xytext=((0.0, +34.0) if signal == FlipSignals.SELL else (0.0, -34.0)),
                textcoords="offset pixels",
                color="green" if signal == FlipSignals.SELL else "red",
                horizontalalignment="center",
                verticalalignment="center",
                arrowprops=dict(arrowstyle="->"),
            )

        # plt.savefig(f"{self.symbol}_chart_{timed}.png", dpi=600)
        plt.show()
        plt.close()

    def play_budget(self, quote_budget=1000.0, step=25.0):
        quote = quote_budget
        base = 0.0

        def buy(base, quote, step, price):
            if quote >= step:
                quote -= step
                bought = (step / price) * 0.999
                base += bought
                print(f"Bought {bought:.6f} BTC at {price:.6f} EUR.")
            else:
                print("Not enough quote currency", quote)

            return base, quote

        def sell(base, quote, step, price):
            sold = step / price
            if sold <= base:
                base -= sold
                quote += sold * price * 0.999
                print(f"Sold {sold:.6f} BTC at {price:.6f} EUR.")
            else:
                print(f"Not enough assets to sell {sold:.6f}, available {base:.6f}")

            return base, quote

        # on entry buy 50%
        entry = self.orders[0]
        assert entry["signal"] == FlipSignals.BUY
        print("== Entry ==")
        base, quote = buy(base, quote, quote / 2, entry["price"])
        entry_base = base
        entry_quote = quote
        entry_price = entry["price"]

        price = entry["price"]
        print(
            f"== {base:.6f} BTC -- {quote:.6f} EUR -- valued at {base * price * 0.999 + quote:.6f} EUR"
        )

        for order in self.orders[1:]:
            signal, price, _ = order.values()

            if signal == FlipSignals.BUY:
                base, quote = buy(base, quote, step, price)
            elif signal == FlipSignals.SELL:
                base, quote = sell(base, quote, step, price)

            print(
                f"{base:.6f} BTC -- {quote:.6f} EUR -- valued at {base * price * 0.999 + quote:.6f} EUR"
            )

        last_price = self.orders[-1]["price"]
        # compare just holding...
        print(f"Entry price {entry_price} vs {last_price}")
        print(
            f"Entry value: {entry_base:.6f} BTC -- {entry_quote:.6f} EUR -- valued at {entry_base * entry_price * 0.999 + entry_quote:.6f} EUR"
        )
        print(
            f"Hold value: {entry_base:.6f} BTC -- {entry_quote:.6f} EUR -- valued at {entry_base * last_price * 0.999 + entry_quote:.6f} EUR"
        )


def main():
    flippie = FlipViewer("BTCEUR")
    flippie.draw_trading_chart()
    flippie.play_budget(step=25)


if __name__ == "__main__":
    main()
