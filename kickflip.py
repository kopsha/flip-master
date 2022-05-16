#!/usr/bin/env python3
from argparse import ArgumentParser
from datetime import datetime
from trade_clients import make_binance_test_client, make_binance_client
from flipper import Flipper
from binance.spot import Spot
from binance.error import ClientError
import schedule
import time


def main(client: Spot, pair, budget):

    try:
        flippy = Flipper(client, pair, budget)
    except ClientError as error:
        print("x: Cannot create trader instance:", error.error_message)
        return -1

    # flippy.preload()
    flippy.show_me_the_money()

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
        print(".:  Using live connector.")
        client = make_binance_client()
    else:
        print(".: Using test connector.")
        client = make_binance_test_client()

    data = client.account()
    print("   Available assets:")
    for balance in filter(lambda x: float(x["free"]) > 0, data["balances"]):
        print("\t", balance["free"], balance["asset"])

    exit(main(client, actual.pair, actual.budget))
