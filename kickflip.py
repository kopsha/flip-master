#!/usr/bin/env python3
import schedule
import time
import os
import pickle
from argparse import ArgumentParser
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from collections import deque

from trade_clients import make_binance_test_client, make_binance_client
from binance.error import ClientError

from pinkybrain import PinkyTracker
from pprint import pprint


def smart_read(client, symbol):
    data = list()
    now = datetime.now()
    since = int((now - timedelta(minutes=1000)).timestamp()) * 1000
    enough = int((now - timedelta(minutes=1)).timestamp()) * 1000

    cache_file = f"./{symbol}/klines.dat"
    if os.path.isfile(cache_file):
        with open(cache_file, "rb") as data_file:
            data += pickle.load(data_file)
        print(f"Read {len(data)} records from {cache_file}")

    if data and data[-1][6] > since:
        # we only want the last 1000 minutes
        since = data[-1][6]

    if since < enough:
        missing_chunk = client.klines(symbol, "1m", startTime=since, limit=1000)
        data += missing_chunk
        print(f"Read {len(missing_chunk)} records from client.")

        with open(cache_file, "wb") as data_file:
            useful_data = data[-1000:]
            pickle.dump(useful_data, data_file, protocol=pickle.HIGHEST_PROTOCOL)
            print(f".: Cached {len(useful_data)} to {cache_file}")

    return data[-1000:]


def run(client, symbol, budget):

    try:
        account_data = client.account()
        exchage_data = client.exchange_info(symbol)
    except ClientError as error:
        print("x: Cannot get exchage info:", error.error_message)
        return -1

    balances = account_data.pop("balances")
    print("   Available assets:")
    for balance in filter(lambda x: float(x["free"]) > 0, balances):
        print("\t", balance["free"], balance["asset"])

    symbol_data = exchage_data["symbols"][0]
    getcontext().prec = max(
        symbol_data["quoteAssetPrecision"], symbol_data["baseAssetPrecision"]
    )

    assert account_data["makerCommission"] == account_data["takerCommission"]
    commission = Decimal(account_data["makerCommission"] or 10) / 10000
    pair = (symbol_data["baseAsset"], symbol_data["quoteAsset"])

    os.makedirs(f"./{symbol}", exist_ok=True)

    try:
        data = smart_read(client, symbol)
    except ClientError as error:
        print("x: Cannot read klines:", error.error_message)
        return -1

    flippy = PinkyTracker(pair, budget, commission, 13, 2)
    flippy.feed(data)
    flippy.backtest()
    flippy.draw_chart()

    # schedule.every().minute.at(":13").do(lambda: tick(client, symbol, data, flippy))
    # while True:
    #     schedule.run_pending()
    #     time.sleep(0.618033988749894)


if __name__ == "__main__":

    args = ArgumentParser(description="Trading on the flip side")
    args.add_argument("--pair", required=True)
    args.add_argument("--budget", type=Decimal, required=True)
    args.add_argument("--go-live", action="store_const", const=True, default=False)

    actual = args.parse_args()

    if actual.go_live:
        print(".: Using live connector.")
        client = make_binance_client()
    else:
        print(".: Using test connector.")
        client = make_binance_test_client()

    ret_code = run(client, actual.pair, actual.budget)

    time.sleep(0.5)
    exit(ret_code)
