#!/usr/bin/env python3
from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from decimal import Decimal
from statistics import mean


# for hourly candlesticks
HALF_DAY_CYCLE = 720
DAILY_CYCLE = 24
WEEKLY_CYCLE = 7 * DAILY_CYCLE
FULL_CYCLE = 4 * WEEKLY_CYCLE

FIBONACCI = [1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]


"""
Some background info:
Every trade has a buyer and a seller. A buyer can be a maker or a taker.
But when a buyer is a maker, the seller must be a taker, and vice versa.
That is,
taker_buy_base_asset_volume = maker_sell_base_asset_volume
taker_sell_base_asset_volume = maker_buy_base_asset_volume
and
total_volume = taker_buy_base_asset_volume + taker_sell_base_asset_volume
             = maker_buy_base_asset_volume + maker_sell_base_asset_volume
"""
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

    trades_count: int
    volume: Decimal
    maker_volume: Decimal
    taker_volume: Decimal

    def __init__(self, kline_data):
        kline = KLinePoint(*kline_data)
        self.open_time = datetime.utcfromtimestamp(int(kline.open_time) // 1000)
        self.open = Decimal(kline.open)
        self.high = Decimal(kline.high)
        self.low = Decimal(kline.low)
        self.close = Decimal(kline.close)
        self.close_time = datetime.utcfromtimestamp(int(kline.close_time) // 1000)

        # express volumes in base asset
        self.volume = Decimal(kline.volume)
        self.taker_volume = Decimal(kline.taker_buy_base_asset_volume)
        self.maker_volume = self.volume - self.taker_volume
        self.trades_count = int(kline.trades_count)


class FlipSignals(IntEnum):
    HOLD = 0
    BUY = 1
    SELL = 2
