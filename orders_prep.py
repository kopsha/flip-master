#!/usr/bin/env python3
from datetime import datetime
from trade_clients import make_binance_test_client
from flipper import Flipper
from binance.spot import Spot
import schedule
import time


def main(client: Spot):

    symbol = "XRPBUSD"

    flippy = Flipper(client, symbol, 1000)
    flippy.preload()

    flippy.show_me_the_money()

    schedule.every().minute.at(":33").do(lambda: flippy.tick())
    while True:
        schedule.run_pending()
        time.sleep(0.618033988749894)


if __name__ == "__main__":
    client = make_binance_test_client()
    data = client.account()
    for x in data["balances"]:
        print("\t --", x["free"], x["asset"])
    main(client)
