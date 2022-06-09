#!/usr/bin/env python3
import os
import pickle
import time
from argparse import ArgumentParser
from datetime import datetime, timedelta
from decimal import Decimal, getcontext

import schedule
from binance.spot import Spot

from metaflip import FULL_CYCLE
from trade_clients import (
    make_binance_client,
    make_binance_test_client,
    make_telegram_client,
)


def set_decimal_precison_context(symbol_data):
    getcontext().prec = max(
        symbol_data["quoteAssetPrecision"], symbol_data["baseAssetPrecision"]
    )

    # prepare cache folder
    # os.makedirs(f"./{symbol}", exist_ok=True)

    # try:
    #     # read initial data
    #     data = smart_read(client, symbol)
    # except ClientError as error:
    #     print("x: Cannot read klines:", error.error_message)
    #     return -1

    # pair = (symbol_data["baseAsset"], symbol_data["quoteAsset"])
    # flippy = PinkyTracker(pair, budget, commission, wix=5)
    # flippy.feed(data)

    # flippy.draw_chart("show.png")

    # TODO: start a monitoring loop that catches opportunities


class PennyHunter:
    def __init__(self, client, notifier):
        self.client = client
        self.notifie = notifier

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
        schedule.every().minute.at(":05").do(lambda: self.tick())
        while True:
            schedule.run_pending()
            time.sleep(0.618033988749894)

    def tick(self):
        print(".", end="", flush=True)

    def smart_read(self, symbol: str):
        data = list()
        this_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        start_at = this_hour - timedelta(hours=FULL_CYCLE)
        since = int(start_at.timestamp()) * 1000
        enough = int(this_hour.timestamp()) * 1000

        cache_file = f"./{symbol}/klines.dat"
        if os.path.isfile(cache_file):
            with open(cache_file, "rb") as data_file:
                data += pickle.load(data_file)
            print(f"Read {len(data)} records from {cache_file}")

        if data and data[-1][6] > since:
            since = data[-1][6]

        if since < enough:
            missing_chunk = client.klines(
                symbol, "1h", startTime=since, limit=FULL_CYCLE
            )
            data += missing_chunk
            print(f"Read {len(missing_chunk)} records from client.")

            with open(cache_file, "wb") as data_file:
                useful_data = data[-FULL_CYCLE:-1]
                pickle.dump(useful_data, data_file, protocol=pickle.HIGHEST_PROTOCOL)
                print(f"Cached {len(useful_data)} to {cache_file}")

        return data[-FULL_CYCLE:]


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
