# flip-master

A simple python bot that watches over your binance crypto wallet and notifies you when it's time to sell or buy.

_NB:_ The strategy does not work when market is trending down.


## Features

* determine the trading pairs to watch from your binance wallet
* estimate suggested trade value based on available coins, trade history and current price
* track oversold and overbought states every minute
* send telegram notification whenever overbought and oversold signals are triggered
* ~~draws trading chart with technical analysis~~ disabled to reduce docker size
* dockerized


## Setup

First, build and run the docker locally with the [./go](./go) shell script,
which will create an empty `credentials.ini` file inside the `./src` folder.

Then, you need to enable binance api access (`api_key` and `secret`) and update
the missing binance credentials.

Create your own telegram bot [@botfather](https://t.me/botfather) and copy the
bot token into the credentials file.

```ini
[binance]
key = go_to_https://www.binance.com/_and_create_one
secret = keep_this_secret_really_I_mean_it

[binance-test]
key = go_to_https://testnet.binance.vision/_and_create_one
secret = keep_this_secret_really_I_mean_it

[telegram]
token = #########:XXXXXXXXX-yyyyyyyy-Zzzzzzzzz
chat_id = #where#to#send#notifications#
```
