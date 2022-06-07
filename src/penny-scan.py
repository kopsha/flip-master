#!/usr/bin/env python3
import os
import pickle
from argparse import ArgumentParser
from datetime import datetime, timedelta
from decimal import Decimal, getcontext

from trade_clients import make_binance_test_client, make_binance_client
from binance.spot import Spot
from binance.error import ClientError

from pinkybrain import PinkyTracker
from metaflip import FULL_CYCLE


def smart_read(client: Spot, symbol: str):
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
        missing_chunk = client.klines(symbol, "1h", startTime=since, limit=FULL_CYCLE)
        data += missing_chunk
        print(f"Read {len(missing_chunk)} records from client.")

        with open(cache_file, "wb") as data_file:
            useful_data = data[-FULL_CYCLE:-1]
            pickle.dump(useful_data, data_file, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"Cached {len(useful_data)} to {cache_file}")

    return data[-FULL_CYCLE:]


def run(client: Spot, symbol: str, budget: Decimal):

    try:
        account_data = client.account()
        exchage_data = client.exchange_info(symbol)
        serverTimestamp = int(exchage_data["serverTime"]) // 1000
        print("server time", datetime.utcfromtimestamp(serverTimestamp).isoformat())

        balances = account_data.pop("balances")
        assets = list(filter(lambda x: float(x["free"]) > 0, balances))
        own_symbols = {x["asset"] + "EUR" for x in assets}
        price_data = client.ticker_price()
        own_tickers = filter(lambda x: x["symbol"] in own_symbols, price_data)
        price_eur = {
            tick["symbol"][:-3]: Decimal(tick["price"]) for tick in own_tickers
        }

        symbol_data = exchage_data["symbols"][0]
        getcontext().prec = max(
            symbol_data["quoteAssetPrecision"], symbol_data["baseAssetPrecision"]
        )

    except ClientError as error:
        print("Client error:", error.error_message)
        return -1

    assert account_data["makerCommission"] == account_data["takerCommission"]
    commission = Decimal(account_data["makerCommission"] or 10) / 10000
    print(f"Commission: {commission * 100:.1f} %")
    print("Crypto wallet:")
    wallet_value = 0
    for balance in filter(lambda x: float(x["free"]) > 0, balances):
        amount = Decimal(balance["free"]) + Decimal(balance["locked"])
        name = balance["asset"]
        value = amount * price_eur.get(name, 0)
        print(f"{amount:18} {name}  =>  {value:7.2f} EUR")
        wallet_value += value
    print(f"               (value) {wallet_value:12.2f} EUR")

    os.makedirs(f"./{symbol}", exist_ok=True)
    try:
        data = smart_read(client, symbol)
    except ClientError as error:
        print("x: Cannot read klines:", error.error_message)
        return -1

    pair = (symbol_data["baseAsset"], symbol_data["quoteAsset"])
    flippy = PinkyTracker(pair, budget, commission, wix=5)
    flippy.feed(data)
    flippy.backtest()

    # flippy.draw_weekly_plus()


if __name__ == "__main__":

    args = ArgumentParser(description="Trading on the flip side")
    args.add_argument("--pair", required=True)
    args.add_argument("--budget", type=Decimal, required=True)
    args.add_argument("--go-live", action="store_const", const=True, default=False)

    actual = args.parse_args()

    if actual.go_live:
        print("- using live connector")
        client = make_binance_client()
    else:
        print("- using test connector")
        client = make_binance_test_client()

    ret_code = run(client, actual.pair, actual.budget)
    exit(ret_code)
