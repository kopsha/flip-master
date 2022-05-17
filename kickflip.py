#!/usr/bin/env python3
from argparse import ArgumentParser
from datetime import datetime
from trade_clients import make_binance_test_client, make_binance_client
from flipper import Flipper
from binance.spot import Spot
from binance.error import ClientError
import schedule
import time

from pprint import pprint


def main(client: Spot, symbol, budget):

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
    assert account_data["makerCommission"] == account_data["takerCommission"]
    commission = (account_data["makerCommission"] or 10) / 10000
    pair = (symbol_data["baseAsset"], symbol_data["quoteAsset"])

    data1 = client.klines(symbol, "1m", startTime=1652734800000)
    data2 = client.klines(symbol, "1m", startTime=data1[-1][6])
    # data = client.klines(symbol, "1m")
    data = data1 + data2

    window_perf = dict()
    for window in [5, 8, 13, 21, 34, 55]:

        factor_results = dict()
        for iff in range(16, 28):
            factor = iff / 10
            flippy = Flipper(pair, budget,commission, split=10, window=window, factor=factor)
            factor_results[factor] = flippy.backtest(data, f"{window}x{factor}")

        fact_performance = list(sorted(factor_results.items(), key=lambda x: x[1], reverse=True))
        window_perf[window] = fact_performance

    pprint(window_perf)

    # schedule.every().minute.at(":33").do(lambda: flippy.tick())
    # while True:
    #     schedule.run_pending()
    #     time.sleep(0.618033988749894)


if __name__ == "__main__":

    args = ArgumentParser(description="Trading on the flip side")
    args.add_argument("--pair", required=True, help="Indicate which trading pair")
    args.add_argument(
        "--budget", type=float, required=True, help="Allocatted budget for quote asset"
    )
    args.add_argument("--go-live", action="store_const", const=True, default=False)

    actual = args.parse_args()

    if actual.go_live:
        print(".: Using live connector.")
        client = make_binance_client()
    else:
        print(".: Using test connector.")
        client = make_binance_test_client()

    exit(main(client, actual.pair, actual.budget))
