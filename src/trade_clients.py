import os
import configparser
from binance.spot import Spot


CREDENTIALS_CACHE = "credentials.ini"


def make_binance_client():
    credentials = configparser.ConfigParser()
    if os.path.isfile(CREDENTIALS_CACHE):
        credentials.read(CREDENTIALS_CACHE)
    else:
        empty = dict(key="", secret="")
        with open(CREDENTIALS_CACHE, "wt") as storage:
            credentials["binance"] = empty
            credentials.write(storage)
        raise RuntimeError(
            f"Created empty {CREDENTIALS_CACHE}, please fill in and run again."
        )

    assert "binance" in credentials.sections()
    client = Spot(**dict(credentials.items("binance")))

    return client


def make_binance_test_client():
    credentials = configparser.ConfigParser()
    if os.path.isfile(CREDENTIALS_CACHE):
        credentials.read(CREDENTIALS_CACHE)
    else:
        empty = dict(api_key="", secret="")
        with open(CREDENTIALS_CACHE, "wt") as storage:
            credentials["binance-test"] = empty
            credentials.write(storage)
        raise RuntimeError(
            f"Created empty {CREDENTIALS_CACHE}, please fill in and run again."
        )

    assert "binance-test" in credentials.sections()
    client = Spot(
        **dict(credentials.items("binance-test")),
        base_url="https://testnet.binance.vision",
    )

    return client
