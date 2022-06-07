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
    buy_volume: Decimal
    sell_volume: Decimal

    def __init__(self, kline_data):
        kline = KLinePoint(*kline_data)
        self.open_time = datetime.utcfromtimestamp(int(kline.open_time) // 1000)
        self.open = Decimal(kline.open)
        self.high = Decimal(kline.high)
        self.low = Decimal(kline.low)
        self.close = Decimal(kline.close)
        self.close_time = datetime.utcfromtimestamp(int(kline.close_time) // 1000)

        self.trades_count = kline.trades_count
        self.volume = Decimal(kline.quote_asset_volume)
        self.sell_volume = Decimal(kline.taker_buy_quote_asset_volume)
        self.buy_volume = self.volume - Decimal(kline.taker_buy_quote_asset_volume)
        self.volume_per_trade = self.volume / self.trades_count


class FlipSignals(IntEnum):
    HOLD = 0
    BUY = 1
    SELL = 2
