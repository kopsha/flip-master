#!/usr/bin/env python3

from collections import defaultdict
import os
import pickle
import time
import schedule
from argparse import ArgumentParser
from datetime import datetime, timedelta
from decimal import Decimal, getcontext

from metaflip import FULL_CYCLE, HALF_DAY_CYCLE, FlipSignals
from trade_clients import (
    make_binance_client,
    make_binance_test_client,
    make_telegram_client,
    Spot,
    TelegramNotifier,
)
from pinkybrain import PinkyTracker


def set_decimal_precison_context(symbol_data):
    getcontext().prec = max(
        symbol_data["quoteAssetPrecision"], symbol_data["baseAssetPrecision"]
    )


class PennyHunter:
    def __init__(self, client: Spot, notifier: TelegramNotifier):
        self.client = client
        self.notifier = notifier

        watchlist = [("BTC", "EUR"), ("ETH", "EUR"), ("LTC", "EUR")]
        self.watchdogs = {"".join(pair): PinkyTracker(pair) for pair in watchlist}
        self.sniffers = {"".join(pair): PinkyTracker(pair) for pair in watchlist}
        self.last_signals = dict()

        # prepare cache folder
        for symbol in self.watchdogs:
            os.makedirs(f"./{symbol}", exist_ok=True)

    def post_init(self):
        account_data = self.client.account()
        balances = list(
            filter(
                lambda x: float(x["free"]) + float(x["locked"]) > 0,
                account_data.pop("balances"),
            )
        )
        symbols = {x["asset"] + "EUR" for x in balances if x["asset"] != "EUR"}

        exchage_data = self.client.exchange_info(symbols=sorted(symbols))
        serverTimestamp = int(exchage_data["serverTime"]) // 1000

        symbol_data = exchage_data["symbols"][0]
        set_decimal_precison_context(symbol_data)

        assert account_data["makerCommission"] == account_data["takerCommission"]
        commission = Decimal(account_data["makerCommission"] or 10) / 10000
        print(f"Commission: {commission * 100:.1f} %")

        price_list = self.get_price_ticker(symbols=sorted(symbols))
        print("Wallet:")
        wallet_value = 0
        for balance in balances:
            amount = Decimal(balance["free"]) + Decimal(balance["locked"])
            name = balance["asset"]
            value = amount * price_list.get(name, 1)
            print(f"{amount:18} {name}   ->  {value:9.2f} EUR")
            wallet_value += value
        print(f"               (value) {wallet_value:15.2f} EUR")

    def get_price_ticker(self, symbols):
        """All prices are quoted in EUR"""
        price_data = self.client.ticker_price(symbols=symbols)
        pennies = {tick["symbol"][:-3]: Decimal(tick["price"]) for tick in price_data}
        return pennies

    def start(self):
        print("running as service")

        for symbol, dog in self.watchdogs.items():
            data = self.cached_read(symbol)
            dog.feed(data)
            dog.run_indicators()
            # dog.draw_chart(f"./{symbol}/hourly_chart.png")

        for symbol, dog in self.sniffers.items():
            data = self.live_read(symbol)
            dog.feed(data, limit=HALF_DAY_CYCLE)
            dog.run_indicators()
            # dog.draw_chart(f"./{symbol}/fast_chart.png", limit=HALF_DAY_CYCLE)

        schedule.every().minute.at(":07").do(lambda: self.tick())

        while True:
            schedule.run_pending()
            time.sleep(0.618033988749894)

    def tick(self):
        print(".", end="", flush=True)
        for symbol, dog in self.sniffers.items():
            data = self.live_read(symbol, since=dog.pop_close_time())
            dog.feed(data)
            dog.run_indicators()

            current = dog.apply_triggers()
            previous = self.last_signals.get(symbol, FlipSignals.HOLD)

            if current != previous and current != FlipSignals.HOLD:
                diagnosis = "overbought" if current == FlipSignals.SELL else "oversold"
                message = (
                    "{base} is {status} at {price} EUR."
                    "Maybe we can {action}."
                    "[trade](https://www.binance.com/en/trade/{base}_{quote}?type=spot)"
                ).format(
                    base=dog.base_symbol,
                    quote=dog.quote_symbol,
                    status=diagnosis,
                    price=dog.price,
                    action=current.name,
                )
                self.notifier.say(message)
                dog.draw_chart(f"./{symbol}/fast_chart.png", limit=HALF_DAY_CYCLE)

                long_data = self.cached_read(symbol)
                watchdog = self.watchdogs[symbol]
                watchdog.feed(long_data)
                watchdog.run_indicators()
                watchdog.draw_chart(f"./{symbol}/hourly_chart.png")

            self.last_signals[symbol] = current

    def cached_read(self, symbol: str, limit=FULL_CYCLE):
        this_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        start_at = this_hour - timedelta(hours=limit)
        since = int(start_at.timestamp()) * 1000
        enough = int(this_hour.timestamp()) * 1000

        cache_file = f"./{symbol}/klines.dat"

        data = list()
        if os.path.isfile(cache_file):
            with open(cache_file, "rb") as data_file:
                data += pickle.load(data_file)
            print(f"Read {len(data)} records from {cache_file}")

        if data and data[-1][6] > since:
            since = data[-1][6]

        if since < enough:
            missing_chunk = client.klines(symbol, "1h", startTime=since, limit=limit)
            data += missing_chunk
            print(f"Read {len(missing_chunk)} {symbol} records from client.")

            with open(cache_file, "wb") as data_file:
                useful_data = data[-limit:-1]
                pickle.dump(useful_data, data_file, protocol=pickle.HIGHEST_PROTOCOL)
                print(f"Cached {len(useful_data)} to {cache_file}")

        return data[-limit:]

    def live_read(self, symbol: str, limit=HALF_DAY_CYCLE, since=None):
        return client.klines(symbol, "1m", limit=limit, startTime=since)


if __name__ == "__main__":

    args = ArgumentParser(description="Trading on the flip side")
    args.add_argument("--go-live", action="store_const", const=True, default=False)

    actual = args.parse_args()
    print("--- action! ---")

    if actual.go_live:
        print(". using live connector")
        client = make_binance_client()
    else:
        print(". using test connector")
        client = make_binance_test_client()

    notifier = make_telegram_client()

    penny = PennyHunter(client, notifier)
    penny.post_init()
    penny.start()

    print("--- the end ---")
