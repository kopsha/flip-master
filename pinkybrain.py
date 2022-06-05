from decimal import Decimal
import pandas as pd
import mplfinance as mpf
from matplotlib import pyplot as plt
from ta.volatility import BollingerBands
from ta.trend import ADXIndicator, PSARIndicator, stc
from ta.volume import money_flow_index
from metaflip import CandleStick, FlipSignals, MAX_CANDLESTICKS


class PinkyTracker:
    FF = [
        2,
        3,
        5,
        8,
        13,
        21,
        34,
        55,
        89,
        144,
    ]
    SIGNAL_TTL = 3
    MFI_HIGH = 65
    MFI_LOW = 35

    def __init__(self, trading_pair, budget, commission, wix):
        self.base_symbol, self.quote_symbol = trading_pair
        self.commission = Decimal(commission)
        self.quote = Decimal(budget)
        self.base = Decimal("0")
        self.is_committed = False

        # some parameters
        self.stop_loss_factor = 0.05
        self.wix = wix

        # running data
        self.data = pd.DataFrame()
        self.order_history = list()
        self.commit_price = None
        self.stop_loss = None

    def __repr__(self) -> str:
        last_price = self.data["close"].iloc[-1]
        est_value = (1 - self.commission) * self.base * last_price + self.quote
        return f"{self.base:.8f} {self.base_symbol} + {self.quote} {self.quote_symbol} => {est_value} {self.quote_symbol}"

    @property
    def window(self):
        return self.FF[self.wix]

    @property
    def faster_window(self):
        return self.FF[self.wix - 1]

    @property
    def fast_window(self):
        return self.FF[self.wix - 1]

    @property
    def slow_window(self):
        return self.FF[self.wix + 1]

    @property
    def slower_window(self):
        return self.FF[self.wix + 1]

    def feed(self, kline_data):
        if not kline_data:
            print("Provided feed seems empty, skipped.")
            return

        if len(kline_data) > MAX_CANDLESTICKS:
            kline_data = kline_data[-MAX_CANDLESTICKS:]
            print(f"Provided feed was truncated to last {len(kline_data)}.")

        klines = [CandleStick(x) for x in kline_data]
        new_df = pd.DataFrame(klines)
        new_df.index = pd.DatetimeIndex(new_df["close_time"])

        self.data = pd.concat([self.data.tail(MAX_CANDLESTICKS - new_df.size), new_df])

        # add indicators to dataframe
        self.data["slope"] = self.data["close"].diff()

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
            }
        )

        self.data["mfi"] = money_flow_index(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            volume=df["volume"],
            window=self.fast_window,
        )

        bb = BollingerBands(close=df["close"], window=self.window)
        self.data["bb_ma"] = bb.bollinger_mavg()
        self.data["bb_high"] = bb.bollinger_hband()
        self.data["bb_low"] = bb.bollinger_lband()

        adx = ADXIndicator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=self.faster_window,
        )
        self.data["adx"] = adx.adx()
        self.data["adx_plus"] = adx.adx_pos()
        self.data["adx_minus"] = adx.adx_neg()

        psar = PSARIndicator(high=df["high"], low=df["low"], close=df["close"], step=0.01)
        self.data["psar_up"] = psar.psar_up()
        self.data["psar_down"] = psar.psar_down()
        self.data["psar_up_sig"] = psar.psar_up_indicator()
        self.data["psar_down_sig"] = psar.psar_down_indicator()

        self.data["stc"] = stc(
            self.data["close"],
            window_slow=self.slower_window,
            window_fast=self.window,
            cycle=self.window,
        )
        self.data["stc_slope"] = self.data["stc"].diff()


    def buy_in(self, itime, price):
        spent = self.quote
        bought = (1 - self.commission) * self.quote / price

        self.quote -= spent
        self.base += bought
        self.order_history.append((FlipSignals.BUY, itime, price))

        self.spent = spent
        self.is_committed = True
        self.commit_price = Decimal(price)

        print(
            f"Bought {bought} {self.base_symbol} at {price} {self.quote_symbol}, spent {spent} {self.quote_symbol}]"
        )

    def sell_out(self, itime, price):
        sold = self.base
        amount = (1 - self.commission) * sold * price
        profit = amount - self.spent
        # if profit < 0:
        #     print("Not selling without profit", profit, self.quote_symbol)
        #     return

        self.base -= sold
        self.quote += amount
        self.order_history.append((FlipSignals.SELL, itime, price))

        self.is_committed = False
        self.commit_price = None

        print(
            f" Sold  {sold} {self.base_symbol} at {price} {self.quote_symbol} for {profit} {self.quote_symbol} profit [Wallet: {self.quote} {self.quote_symbol}]"
        )

    def age_meta_signals(self, meta_signals):
        aged_meta_signals = dict()
        for key in meta_signals:
            ms, ttl = meta_signals[key]
            if ms != FlipSignals.HOLD:
                ttl -= 1
                if ttl == 0:
                    ms = FlipSignals.HOLD
                    ttl = None
            aged_meta_signals[key] = (ms, ttl)
        return aged_meta_signals

    def apply_money_flow(self, row, previous):
        if row["mfi"] >= self.MFI_HIGH:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif row["mfi"] <= self.MFI_LOW:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def apply_bollinger_bands(self, row, previous):
        tolerance = 0.001
        bb_high = row["bb_high"] * (1 - tolerance)
        bb_low = row["bb_low"] * (1 + tolerance)

        if float(row["high"]) >= bb_high and row["slope"] < 0:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif float(row["low"]) <= bb_low and row["slope"] > 0:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def apply_psar_signals(self, row, previous):
        if row.isna()["psar_up"]:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif row.isna()["psar_down"]:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def apply_stc_signals(self, row, previous):
        if row["stc"] < 25:
            ms, ttl = FlipSignals.SELL, self.SIGNAL_TTL
        elif row["stc"] > 75:
            ms, ttl = FlipSignals.BUY, self.SIGNAL_TTL
        else:
            ms, ttl = previous or (FlipSignals.HOLD, None)
        return ms, ttl

    def pick_dominant_signal(self, meta_signals):
        mss = [ms for ms, _ in meta_signals.values()]
        bears = mss.count(FlipSignals.SELL)
        bulls = mss.count(FlipSignals.BUY)

        if bears > bulls and bears >= 3:
            signal = FlipSignals.SELL
        elif bulls > bears and bulls >= 3:
            signal = FlipSignals.BUY
        else:
            signal = FlipSignals.HOLD

        return signal

    def backtest(self):

        previous_meta = dict()

        for i, (_, row) in enumerate(self.data.iterrows()):
            if row.isna()["stc"]:
                continue

            meta_signals = dict(
                mfi=self.apply_money_flow(row, previous_meta.get("mfi")),
                bb=self.apply_bollinger_bands(row, previous_meta.get("bb")),
                psar=self.apply_psar_signals(row, previous_meta.get("psar")),
                stc=self.apply_stc_signals(row, previous_meta.get("stc")),
            )

            aligned = self.pick_dominant_signal(meta_signals)
            if self.is_committed and aligned == FlipSignals.SELL:
                self.sell_out(i, row["close"])
            elif not self.is_committed and aligned == FlipSignals.BUY:
                self.buy_in(i, row["close"])

            previous_meta = self.age_meta_signals(meta_signals)

    def draw_chart(self):

        df = self.data.astype(
            {
                "open": "float",
                "high": "float",
                "low": "float",
                "close": "float",
            }
        )

        df["mfi-high"] = self.MFI_HIGH
        df["mfi-low"] = self.MFI_LOW

        extras = [
            mpf.make_addplot(
                df["bb_high"], color="seagreen", secondary_y=False, alpha=0.35
            ),
            mpf.make_addplot(df["bb_ma"], color="dodgerblue", secondary_y=False, alpha=0.35),
            mpf.make_addplot(
                df["bb_low"], color="tomato", secondary_y=False, alpha=0.35
            ),

            mpf.make_addplot(df["psar_up"], color="dodgerblue", secondary_y=False, panel=0),
            mpf.make_addplot(df["psar_down"], color="darkorange", secondary_y=False, panel=0),

            mpf.make_addplot(df["mfi"], color="blueviolet", secondary_y=False, panel=1),
            mpf.make_addplot(
                df["mfi-high"], color="seagreen", alpha=0.35, secondary_y=False, panel=1
            ),
            mpf.make_addplot(
                df["mfi-low"], color="tomato", alpha=0.35, secondary_y=False, panel=1
            ),

            mpf.make_addplot(df["stc"], color="royalblue", panel=2),
            # mpf.make_addplot(df["stc_slope"], color="darkorange", secondary_y=False, panel=2),
            # mpf.make_addplot(df["adx_plus"], color="dodgerblue", secondary_y=False, panel=2),
            # mpf.make_addplot(df["adx_minus"], color="darkorange", secondary_y=False, panel=2),
        ]

        fig, axes = mpf.plot(
            df,
            type="candle",
            addplot=extras,
            title=f"{self.base_symbol}/{self.quote_symbol}",
            # volume=True,
            figsize=(13, 8),
            tight_layout=True,
            style="yahoo",
            warn_too_much_data=MAX_CANDLESTICKS,
            returnfig=True,
        )

        for ax in axes:
            ax.yaxis.tick_left()
            ax.yaxis.label.set_visible(False)
            ax.margins(x=0.1, y=0.1, tight=False)

        for signal, time, price in self.order_history:
            fig.axes[0].annotate(
                signal.name,
                xy=(time, price),
                fontsize="small",
                xytext=((-0, +55.0) if signal == FlipSignals.SELL else (-0, -55.0)),
                textcoords="offset pixels",
                color="green" if signal == FlipSignals.SELL else "red",
                horizontalalignment="center",
                verticalalignment="center",
                arrowprops=dict(arrowstyle="->"),
            )

        fig.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)
        # plt.savefig('image.png', bbox_inches='tight', pad_inches = 0.3)
        plt.show()
