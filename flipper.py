import pickle
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from binance.spot import Spot
from binance.error import ClientError
from datetime import datetime
from statistics import stdev, mean
from collections import deque
from heapq import heappush, heappop
from metaflip import FlipSignals, KLinePoint, PricePoint


class Flipper:
    def __init__(self, client: Spot, symbol, budget):
        self.client = client
        self.symbol = symbol
        self.budget = budget
        self.quote = budget
        self.base = 0
        self.buy_heap = list()
        self.buyin_price = None
        self.follow_up = None

        self.window = 21
        self.factor = 1.9

        self.order_history = list()
        self.prices = list()
        self.timeline = list()
        self.velocity = list()
        self.bb_mean = list()
        self.bb_stdev = list()
        self.bb_low = list()
        self.bb_high = list()

        self.last_kline = None

        account_data = self.client.account()
        self.commission = account_data["makerCommission"]
        assert account_data["takerCommission"] == self.commission

        info_data = client.exchange_info(symbol)
        assert len(info_data["symbols"]) == 1
        info = info_data["symbols"].pop()
        self.base_symbol = info["baseAsset"]
        self.quote_symbol = info["quoteAsset"]

    def _consume_first(self, kline_data):
        self.last_kline = KLinePoint(*kline_data)
        first = PricePoint(kline_data)
        self.prices.append(first.close)
        self.timeline.append(first.close_time)
        self.velocity.append(first.close - first.open)
        self.bb_mean.append(mean([first.open, first.close]))
        self.bb_stdev.append(stdev([first.open, first.close]))
        self.bb_low.append(min([first.open, first.close]))
        self.bb_high.append(max([first.open, first.close]))

    def feed_klines(self, data):
        if not data:
            print("provided data seems empty, feeding skipped.")
            return

        if len(self.prices) == 0:
            self._consume_first(data.popleft())

        start_at = len(self.prices)

        klines = [KLinePoint(*x) for x in data]
        if klines:
            self.last_kline = klines[-1]

        self.prices.extend([float(x.close) for x in klines])
        self.timeline.extend([datetime.fromtimestamp(x.close_time // 1000) for x in klines])

        for right in range(start_at, len(self.prices)):
            left = max(right - self.window, 0)
            mm = mean(self.prices[left : right + 1])
            std = stdev(self.prices[left : right + 1])

            self.bb_stdev.append(self.factor * std)
            self.bb_mean.append(mm)
            self.bb_high.append(mm + self.factor * std)
            self.bb_low.append(mm - self.factor * std)
            self.velocity.append(self.prices[right] - self.prices[right - 1])

    def draw_trading_chart(self, limit=1000):
        since = max(len(self.prices) - limit, 0)
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

        for order in self.order_history:
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

        # timed = self.timeline[-1].strftime("%Y-%m-%d_%H:%M:%S")
        # plt.savefig(f"{self.symbol}_chart_{timed}.png", dpi=600)
        plt.show()
        plt.close()

    @property
    def last_price(self):
        return self.prices[-1]

    @property
    def last_timestamp(self):
        return self.last_kline.close_time

    def compute_signal(self):
        """trigger signal base on last point only"""

        if len(self.prices) < self.window:
            # print(f"{len(self.prices)} datapoints are not enough for a {self.window} window.")
            return FlipSignals.HOLD

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

    def buy(self, amount):

        if self.quote < (amount * 0.99):
            print(f"Cannot buy, {self.quote:.8f} {self.quote_symbol} is not enough to buy {amount:.8f} {self.base_symbol}")
            return

        if not self.buyin_price:
            self.buyin_price = self.last_price

        try:
            response = self.client.new_order(
                symbol=self.symbol,
                side="BUY",
                type="MARKET",
                quoteOrderQty=amount,
            )
        except ClientError as error:
            print("BUY order failed:", error.error_message)
            return

        bought = float(response["executedQty"])
        for_quote = float(response["cummulativeQuoteQty"])
        actual_price = for_quote / bought
        self.quote -= for_quote
        self.base += bought
        self.order_history.append(response)
        heappush(self.buy_heap, actual_price*0.8)

        print(f"Bought {bought:.8f} {self.base_symbol} at {actual_price:.8f} {self.quote_symbol} [{for_quote:.8f} {self.quote_symbol}]")

    def sell(self, amount):
        est_sold = 0.99 * amount / self.last_price
        if (est_sold > self.base):
            print(f"Cannot sell {est_sold:.8f} {self.base_symbol}, when only {self.base:.8f} is available")
            return

        cheapest = self.buy_heap[0]
        if self.last_price <= (cheapest * 1.001):
            print(f"Cannot sell without profit, {self.last_price} < {cheapest}")
            return

        try:
            response = self.client.new_order(
                symbol=self.symbol,
                side="SELL",
                type="MARKET",
                quoteOrderQty=amount,
            )
        except ClientError as error:
            print("SELL order failed:", error.error_message)
            return

        sold = float(response["executedQty"])
        for_quote = float(response["cummulativeQuoteQty"])
        actual_price = for_quote / sold
        self.base -= sold
        self.quote += for_quote
        self.order_history.append(response)
        heappop(self.buy_heap)

        print(f"Sold {sold:.8f} {self.base_symbol} at {actual_price:.8f} {self.quote_symbol} [{for_quote:.8f} {self.quote_symbol}]")

    def preload(self, limit=1000):
        data = self.client.klines(self.symbol, "1m", limit=limit)
        price_cache = f"{self.symbol}_price.dat"
        with open(price_cache, "wb") as data_file:
            pickle.dump(data, data_file)

        self.feed_klines(deque(data))

    def show_me_the_money(self):
        print("\n")
        if self.order_history:
            initial_buyin = (self.budget / self.buyin_price) * 0.999
            buyin_value = initial_buyin * self.last_price * 0.999
            print(" -- BUY and HOLD (entry vs exit price) --")
            print(f" {self.buyin_price:.8f} {self.quote_symbol} -:- {self.last_price:.8f} {self.quote_symbol} \t\t==> {buyin_value:.8f} {self.quote_symbol} <==")
        print(f" -- ALGO strategy (after {len(self.order_history)} transactions) --")
        print(f" {self.base:.8f} {self.base_symbol} + {self.quote:.8f} {self.quote_symbol} \t\t\t==> {self.base * self.last_price * 0.999 + self.quote:.8f} {self.quote_symbol} <==")


    def tick(self):
        data = self.client.klines(self.symbol, "1m", startTime=self.last_timestamp)
        self.feed_klines(deque(data))
        signal = self.compute_signal()

        amount = self.budget / 10
        if signal == FlipSignals.BUY:
            self.buy(amount)
            self.show_me_the_money()
        elif signal == FlipSignals.SELL:
            self.sell(amount)
            self.show_me_the_money()

        print(".", end="", flush=True)


    def backtest(self, amount):
        price_cache = f"{self.symbol}_price.dat"
        if os.path.isfile(price_cache):
            print(f"Reading {price_cache}...")
            with open(price_cache, "rb") as data_file:
                data = pickle.load(data_file)

        for kline_data in data:
            self.feed_klines(deque([kline_data]))
            signal = self.compute_signal()

            if signal == FlipSignals.BUY:
                self.buy(amount)
            elif signal == FlipSignals.SELL:
                self.sell(amount)

        print(self.buy_heap)

        self.show_me_the_money()
        self.draw_trading_chart()
