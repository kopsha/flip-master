import pandas as pd
from ta.volatility import BollingerBands
from ta.trend import ADXIndicator
from ta.volume import money_flow_index

from metaflip import (
    CandleStick,
    MarketSignal,
    FULL_CYCLE,
    FIBONACCI,
)


class PinkyTracker:
    def __init__(self, trading_pair, wix=6):
        self.base_symbol, self.quote_symbol = trading_pair
        self.wix = wix

        self.data = pd.DataFrame(
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
            ]
        )

        self.pre_signal = None

    @property
    def faster_window(self):
        return FIBONACCI[self.wix - 1]

    @property
    def fast_window(self):
        return FIBONACCI[self.wix - 1]

    @property
    def window(self):
        return FIBONACCI[self.wix]

    @property
    def slow_window(self):
        return FIBONACCI[self.wix + 1]

    @property
    def slower_window(self):
        return FIBONACCI[self.wix + 1]

    @property
    def price(self):
        return float(self.data["close"].iloc[-1])

    def pop_close_time(self):
        self.data.drop(self.data.tail(1).index, inplace=True)
        close_time = int(self.data["close_time"].iloc[-1].timestamp()) * 1000
        return close_time

    def feed(self, kline_data, limit=FULL_CYCLE):
        if not kline_data:
            print("Provided feed seems empty, skipped.")
            return

        if len(kline_data) > limit:
            kline_data = kline_data[-limit:]
            print(f"Provided feed was truncated to last {len(kline_data)}.")

        klines = [CandleStick(x) for x in kline_data]
        new_df = pd.DataFrame(klines)
        new_df.index = pd.DatetimeIndex(new_df["open_time"])

        self.data = pd.concat([self.data.tail(limit - new_df.size), new_df])

    def run_indicators(self):
        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
                "volume": "float",
            }
        )

        # self.data["velocity"] = self.data["close"].diff()
        self.data["high_velocity"] = self.data["high"].diff()
        self.data["low_velocity"] = self.data["low"].diff()

        adx = ADXIndicator(
            high=df["high"], low=df["low"], close=df["close"], window=self.faster_window
        )
        self.data["adx_pos"] = adx.adx_pos()
        self.data["adx_neg"] = adx.adx_neg()

        bb = BollingerBands(close=df["close"], window=self.window)
        self.data["bb_high"] = bb.bollinger_hband()
        self.data["bb_low"] = bb.bollinger_lband()

        self.data["mfi"] = money_flow_index(
            df["high"], df["low"], df["close"], df["volume"], window=self.faster_window
        )

    def compute_triggers(self):
        price = self.price
        high = self.data["bb_high"].iloc[-1]
        low = self.data["bb_low"].iloc[-1]
        high_velocity = self.data["high_velocity"].iloc[-1]
        low_velocity = self.data["low_velocity"].iloc[-1]

        if self.pre_signal == MarketSignal.SELL and high_velocity <= 0:
            self.pre_signal = None
            return MarketSignal.SELL
        elif self.pre_signal == MarketSignal.BUY and low_velocity >= 0:
            self.pre_signal = None
            return MarketSignal.BUY

        if price >= high:
            if high_velocity > 0:
                self.pre_signal = MarketSignal.SELL
            else:
                self.pre_signal = None
                return MarketSignal.SELL
        elif price <= low:
            if low_velocity < 0:
                self.pre_signal = MarketSignal.BUY
            else:
                self.pre_signal = None
                return MarketSignal.BUY

        return MarketSignal.HOLD

    def backtest(self):
        pre_signal = None
        for i, row in self.data.iterrows():
            price = float(row["close"])
            high = row["bb_high"]
            low = row["bb_low"]
            high_velocity = row["high_velocity"]
            low_velocity = row["low_velocity"]

            signal = None
            if pre_signal == MarketSignal.SELL and high_velocity <= 0:
                pre_signal = None
                signal = MarketSignal.SELL
            elif pre_signal == MarketSignal.BUY and low_velocity >= 0:
                pre_signal = None
                signal = MarketSignal.BUY

            if price >= high:
                if high_velocity > 0:
                    pre_signal = MarketSignal.SELL
                else:
                    pre_signal = None
                    signal = MarketSignal.SELL
            elif price <= low:
                if low_velocity < 0:
                    pre_signal = MarketSignal.BUY
                else:
                    pre_signal = None
                    signal = MarketSignal.BUY

            print(
                row["close_time"].isoformat(),
                pre_signal,
                signal,
                price,
                low_velocity,
                row["low"],
            )
