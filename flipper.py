import pickle
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from binance.spot import Spot
from binance.error import ClientError
from datetime import datetime
from statistics import stdev, mean
from collections import deque
from decimal import Decimal
from heapq import heappush, heappop
from metaflip import FlipSignals, KLinePoint, PricePoint, AssetMeta


class Flipper:
    # TODO: remove client dependency
    def __init__(self, pair, budget, commission, split=10, window=28, factor=2):
        self.base_asset, self.quote_asset = pair
        self.symbol = "".join(pair)
        self.budget = Decimal(budget)
        self.split = Decimal(split)
        self.commission = Decimal(commission)

        self.quote = Decimal(budget)
        self.base = Decimal(0)
        self.window = window
        self.factor = Decimal(factor)

        self.prices = list()
        self.timeline = list()
        self.velocity = list()
        self.bb_mean = list()
        self.bb_stdev = list()
        self.bb_low = list()
        self.bb_high = list()

        self.buy_heap = list()
        self.order_history = list()
        self.profit_history = list()

        self.buyin = None
        self.buyin_price = None
        self.follow_up = None

        print(
            f".: {pair} trader created, budget {budget} {self.quote_asset}, in {split} splits, commission {commission * 100:.2f} %, {window} x {factor}"
        )

    def save_order_book(self):
        orders_cache = f"./{self.symbol}/order_history.dat"
        with open(orders_cache, "wb") as data_file:
            pickle.dump(self.order_history, data_file)
        print(f"Saved orders to {orders_cache}")


    @property
    def last_price(self):
        return self.prices[-1] if self.prices else None

    def show_me_the_money(self):
        print("")

        print(
            f".: Auto-flip strategy (after {len(self.order_history)} transactions) --"
        )

        valued = self.base * self.last_price * (1 - self.commission) + self.quote
        performance = (valued - self.budget) * 100 / self.budget
        print(
            f"   {self.base:} {self.base_asset} + {self.quote:} {self.quote_asset} \t\t\t==> {valued:} {self.quote_asset} : {performance:.2f} % <=="
        )
        return performance

    def draw_trading_chart(self, description):
        fig, axes = plt.subplots(1, 1, sharex=True, figsize=(15.7, 5.5), dpi=160)

        axes.plot(
            self.timeline,
            self.bb_high,
            "r,:",
            self.timeline,
            self.bb_low,
            "g,:",
            self.timeline,
            self.bb_mean,
            "y,:",
            self.timeline,
            self.prices,
            "b,-",
            linewidth=0.5,
        )

        axes.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        axes.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        axes.xaxis.set_minor_locator(mdates.HourLocator())
        axes.grid(visible=True, which="both")
        axes.set_title(f"{self.symbol}, using {description}")

        for label in axes.get_xticklabels(which="major"):
            label.set(rotation=45, horizontalalignment="right")

        balance = self.split // 2 - 1
        for order in self.order_history:
            signal, price, timestamp = order.values()
            if signal == FlipSignals.BUY:
                balance += 1
            else:
                balance -= 1
            axes.annotate(
                f"{balance}",
                xy=(timestamp, price),
                fontsize="small",
                xytext=((0.0, +75.0) if signal == FlipSignals.SELL else (0.0, -75.0)),
                textcoords="offset pixels",
                color="green" if signal == FlipSignals.SELL else "red",
                horizontalalignment="center",
                verticalalignment="center",
                arrowprops=dict(arrowstyle="->"),
            )

        # timed = self.timeline[-1].strftime("%Y-%m-%d_%H:%M:%S")
        plt.savefig(f"./{self.symbol}/{description}.png")
        plt.close()

    def _consume_first(self, kline_data):
        first = PricePoint(kline_data)
        self.prices.append(first.close)
        self.timeline.append(first.close_time)
        self.velocity.append(first.close - first.open)
        self.bb_mean.append(mean([first.open, first.close]))
        self.bb_stdev.append(stdev([first.open, first.close]))
        self.bb_low.append(min([first.open, first.close]))
        self.bb_high.append(max([first.open, first.close]))

    def consume(self, data):
        if not data:
            print(".: Provided feed seems empty, skipped.")
            return

        if len(self.prices) == 0:
            self._consume_first(data.popleft())

        start_at = len(self.prices)
        klines = [KLinePoint(*x) for x in data]

        self.prices.extend([Decimal(x.close) for x in klines])
        self.timeline.extend(
            [datetime.fromtimestamp(x.close_time // 1000) for x in klines]
        )

        for right in range(start_at, len(self.prices)):
            left = max(right - self.window, 0)
            mm = mean(self.prices[left : right + 1])
            std = stdev(self.prices[left : right + 1])

            self.bb_stdev.append(self.factor * std)
            self.bb_mean.append(mm)
            self.bb_high.append(mm + self.factor * std)
            self.bb_low.append(mm - self.factor * std)
            self.velocity.append(self.prices[right] - self.prices[right - 1])

    @property
    def last_price(self):
        return self.prices[-1] if self.prices else 0

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

    def fake_buy(self, amount):
        if not self.buyin:
            self.buyin = (1 - self.commission) * self.budget / self.last_price
            self.buyin_price = self.last_price
            amount = self.budget / 2
            for _ in range(int(self.split) // 2 - 1):
                heappush(self.buy_heap, self.last_price)

        bought = (1 - self.commission) * amount / self.last_price

        if self.quote < amount:
            # print(
            #     f"/x Cannot buy {bought} {self.base_asset}, available {self.quote} {self.quote_asset} is not enough."
            # )
            return

        self.quote -= amount
        self.base += bought
        self.order_history.append(
            dict(signal=FlipSignals.BUY, price=self.last_price, time=self.timeline[-1])
        )
        heappush(self.buy_heap, self.last_price)

        print(
            f"/: Bought {bought} {self.base_asset} at {self.last_price} {self.quote_asset} [{amount} {self.quote_asset}]"
        )
        return

    def fake_sell(self, amount):

        sold = amount / self.last_price
        # print("selling", amount, self.quote_asset, "available base", self.base, self.base_asset, "sold", sold)
        if not self.buy_heap:
            # print(f"/x Cannot sell outside buying heap")
            return

        cheapest = self.buy_heap[0] if self.buy_heap else 0
        if self.last_price <= (cheapest * (1 + self.commission)):
            # print(f"/x Cannot sell without profit, {self.last_price} < {cheapest}")
            return

        self.base -= sold
        self.quote += amount * (1 - self.commission)
        self.order_history.append(
            dict(signal=FlipSignals.SELL, price=self.last_price, time=self.timeline[-1])
        )
        heappop(self.buy_heap)

        print(
            f"/: Sold {sold} {self.base_asset} at {self.last_price} {self.quote_asset} [{amount} {self.quote_asset}]"
        )

    def buy(self, client, amount):

        if self.quote < amount:
            print(
                f"x: Cannot buy {amount} {self.base_asset}, available {self.quote} {self.quote_asset} is not enough."
            )
            return

        if not self.buyin:
            amount = self.budget / 2

        try:
            response = client.new_order(
                symbol=self.symbol,
                side="BUY",
                type="MARKET",
                quoteOrderQty=amount,
            )
        except ClientError as error:
            print("x: BUY order failed:", error.error_message)
            return

        bought = Decimal(response["executedQty"])
        for_quote = Decimal(response["cummulativeQuoteQty"])
        actual_price = for_quote / bought
        self.quote -= for_quote
        self.base += bought
        self.order_history.append(response)
        heappush(self.buy_heap, actual_price)

        if not self.buyin:
            self.buyin = bought
            self.buyin_price = actual_price
            for _ in range(int(self.split // 2) - 1):
                heappush(self.buy_heap, self.last_price)

        print(
            f".: Bought {bought} {self.base_asset} at {actual_price} {self.quote_asset} [{for_quote} {self.quote_asset}]"
        )
        self.show_me_the_money()
        self.save_order_book()

    def sell(self, client, amount):
        if not self.buy_heap:
            print(f"/x Cannot sell outside buying heap")
            return

        cheapest = self.buy_heap[0] if self.buy_heap else 0
        if self.last_price <= (cheapest * (1 + self.commission)):
            print(
                f"x: Cannot sell without profit, {self.last_price} < {cheapest * (1 + self.commission)}"
            )
            return

        try:
            response = client.new_order(
                symbol=self.symbol,
                side="SELL",
                type="MARKET",
                quoteOrderQty=amount,
            )
        except ClientError as error:
            print("x: SELL order failed:", error.error_message)
            return

        sold = Decimal(response["executedQty"])
        for_quote = Decimal(response["cummulativeQuoteQty"])
        actual_price = for_quote / sold
        self.base -= sold
        self.quote += for_quote
        self.order_history.append(response)
        heappop(self.buy_heap)

        print(
            f"   Sold {sold} {self.base_asset} at {actual_price} {self.quote_asset} [{for_quote} {self.quote_asset}]"
        )
        self.show_me_the_money()
        self.save_order_book()

        print(
            f"   -> last price {self.last_price} vs actual {actual_price} {self.quote_asset}"
        )
        if actual_price < cheapest:
            print(
                f"Oops, I've made a sell without profit, delta: {cheapest - actual_price}"
            )

    def feed(self, client, new_data):
        self.consume(deque(new_data))
        signal = self.compute_signal()

        amount = self.budget / self.split
        if signal == FlipSignals.BUY:
            self.buy(client, amount)
        elif signal == FlipSignals.SELL:
            self.sell(client, amount)

        print(".", end="", flush=True)

    def backtest(self, data, description):
        amount = self.budget / self.split
        for kline_data in data:
            self.consume(deque([kline_data]))
            signal = self.compute_signal()

            if signal == FlipSignals.BUY:
                self.fake_buy(amount)

            elif signal == FlipSignals.SELL:
                self.fake_sell(amount)

        self.draw_trading_chart(description)
        performance = self.show_me_the_money()
        return performance
