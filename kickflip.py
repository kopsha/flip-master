#!/usr/bin/env python3
from argparse import ArgumentParser
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from collections import deque
from trade_clients import make_binance_test_client, make_binance_client
from flipper import Flipper
from binance.spot import Spot
from binance.error import ClientError
import schedule
import time
import os
import pickle

from pprint import pprint


def read_past_24h(client, symbol):
    cache_file = f"./{symbol}/klines.dat"
    data = list()
    now = datetime.now()
    recent = int((now - timedelta(minutes=1)).timestamp()) * 1000

    if os.path.isfile(cache_file):
        with open(cache_file, "rb") as data_file:
            data += pickle.load(data_file)
        print(f"Read {len(data)} records from {cache_file}")

    if data:
        since = data[-1][6]
    else:
        past = now - timedelta(days=1)
        since = int(past.timestamp() * 1000)

    while since < recent:
        chunk = client.klines(symbol, "1m", startTime=since, limit=1000)
        since = chunk[-1][6]  # ATTENTION: close_time
        data += chunk

        with open(cache_file, "wb") as data_file:
            pickle.dump(data, data_file, protocol=pickle.HIGHEST_PROTOCOL)
            print(f".: Cached {len(data)} to {cache_file}")

        time.sleep(1)

    return data


def backtest(client: Spot, symbol, budget):

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
        data = read_past_24h(client, symbol)
    except ClientError as error:
        print("x: Cannot read klines:", error.error_message)
        return -1

    window_perf = dict()
    for window in [5, 8]: #, 13, 21, 34, 55]:

        factor_results = dict()
        for iff in range(15, 21): # 28):
            factor = Decimal(iff) / 10
            flippy = Flipper(
                pair, budget, commission, split=10, window=window, factor=factor
            )
            # continue
            factor_results[factor] = flippy.backtest(
                data, f"backtest_{window}x{factor}"
            )

            # pprint(flippy.order_history[:3])
            # pprint(flippy.timeline[:10])
            # return

        fact_performance = list(
            sorted(factor_results.items(), key=lambda x: x[1], reverse=True)
        )
        window_perf[window] = fact_performance

    pprint(window_perf)

    together = list()
    for window in window_perf:
        for factor, performance in window_perf[window]:
            together.append((f"{window} x {factor}", performance))

    pprint(sorted(together, key=lambda x: x[1], reverse=True))

def tick(client, symbol, data, flippy):
    cache_file = f"./{symbol}/klines.dat"
    since = data[-1][6]
    chunk = client.klines(symbol, "1m", startTime=since)
    if chunk:
        data += chunk
        with open(cache_file, "wb") as data_file:
            pickle.dump(data, data_file, protocol=pickle.HIGHEST_PROTOCOL)

    flippy.feed(client, chunk)


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
        data = read_past_24h(client, symbol)
    except ClientError as error:
        print("x: Cannot read klines:", error.error_message)
        return -1

    flippy = Flipper(pair, budget, commission, split=10, window=13, factor=2.1)
    flippy.consume(deque(data))
    flippy.buy(client, Decimal(100))

    schedule.every().minute.at(":13").do(lambda: tick(client, symbol, data, flippy))
    while True:
        schedule.run_pending()
        time.sleep(0.618033988749894)


if __name__ == "__main__":

    args = ArgumentParser(description="Trading on the flip side")
    args.add_argument("--pair", required=True)
    args.add_argument("--budget", type=Decimal, required=True)
    args.add_argument("--go-live", action="store_const", const=True, default=False)
    args.add_argument("--backtest", action="store_const", const=True, default=False)

    actual = args.parse_args()

    if actual.go_live:
        print(".: Using live connector.")
        client = make_binance_client()
    else:
        print(".: Using test connector.")
        client = make_binance_test_client()

    if actual.backtest:
        ret_code = backtest(client, actual.pair, actual.budget)
    else:
        ret_code = run(client, actual.pair, actual.budget)

    exit(ret_code)
