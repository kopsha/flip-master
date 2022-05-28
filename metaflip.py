#!/usr/bin/env python3
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from decimal import Decimal
from statistics import mean
from math import copysign


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


@dataclass
class CandleStick:

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    close_time: datetime
    typical_price: float
    volume: float

    def __init__(self, kline_data):
        kpoint = KLinePoint(*kline_data)
        self.open = Decimal(kpoint.open)
        self.high = Decimal(kpoint.high)
        self.low = Decimal(kpoint.low)
        self.close = Decimal(kpoint.close)
        self.close_time = datetime.fromtimestamp(int(kpoint.close_time) // 1000)
        self.typical_price = float(mean([self.open, self.high, self.low, self.close]))
        self.volume = float(kpoint.volume)


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
