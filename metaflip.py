#!/usr/bin/env python3
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


# Binance API response kline format
KLinePoint = namedtuple(
    "KLinePoint",
    [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "trades_count",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
        "ignore",
    ],
)

AssetMeta = namedtuple("AssetMeta", ["symbol", "precision"])


@dataclass
class PricePoint:
    """Main flippie data structure"""

    open_time: datetime
    open: float
    close: float
    close_time: datetime

    def __init__(self, kline_data):
        kpoint = KLinePoint(*kline_data)
        self.open_time = datetime.fromtimestamp(kpoint.open_time // 1000)
        self.open = float(kpoint.open)
        self.close = float(kpoint.low)
        self.close_time = datetime.fromtimestamp(kpoint.close_time // 1000)


class FlipSignals(Enum):
    HOLD = 0
    ENTRY = 1
    SELL = 2
    BUY = 3
    EXIT = 4

    AS_STR = {
        0: "hold",
        1: "entry",
        2: "sell",
        3: "buy",
        4: "exit",
    }
