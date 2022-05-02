#!/usr/bin/env python3

import os
import configparser


CREDENTIALS_CACHE = "credentials.ini"


def init():
    credentials = configparser.ConfigParser()
    if os.path.isfile(CREDENTIALS_CACHE):
        credentials.read(CREDENTIALS_CACHE)
    else:
        empty = dict(api_key="", secret="")
        with open(CREDENTIALS_CACHE, "wt") as storage:
            credentials["binance"] = empty
            credentials.write(storage)
        raise RuntimeError(
            f"Created empty {CREDENTIALS_CACHE}, please fill in and run again."
        )

    accounts = dict()
    for network in credentials.sections():
        accounts[network] = dict(credentials.items(network))
        print(f"Read {network} credentials")

    assert "binance" in accounts
    return accounts["binance"]


def main(auth):
    print("flipper is on", auth)


if __name__ == "__main__":
    auth = init()
    main(auth)
