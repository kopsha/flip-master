#!/usr/bin/env python3
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from decimal import Decimal
from statistics import mean


FULL_CYCLE = 672
WEEKLY_CYCLE = 168
DAILY_CYCLE = 24

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

    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    close_time: datetime
    typical_price: float
    volume: float

    def __init__(self, kline_data):
        kpoint = KLinePoint(*kline_data)
        self.open_time = (
            datetime.utcfromtimestamp(int(kpoint.open_time) // 1000)
            # .replace(tzinfo=timezone.utc)
            # .astimezone()
        )
        self.open = Decimal(kpoint.open)
        self.high = Decimal(kpoint.high)
        self.low = Decimal(kpoint.low)
        self.close = Decimal(kpoint.close)
        self.close_time = (
            datetime.utcfromtimestamp(int(kpoint.close_time) // 1000)
            # .replace(tzinfo=timezone.utc)
            # .astimezone()
        )
        self.typical_price = float(mean([self.open, self.high, self.low, self.close]))
        self.volume = float(kpoint.volume)


class FlipSignals(IntEnum):
    HOLD = 0
    BUY = 1
    SELL = 2
