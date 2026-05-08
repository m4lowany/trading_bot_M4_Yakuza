import ccxt

from config import CONFIRM_TIMEFRAME, TREND_TIMEFRAME


exchange = ccxt.mexc()


def get_ma60(data):
    symbol = "BTC/USDT"
    limit = 100
    period = 60

    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=TREND_TIMEFRAME, limit=limit)
        closes = [candle[4] for candle in candles]
        if len(closes) < period:
            return "WAIT"

        ma60 = sum(closes[-period:]) / period
        current_price = closes[-1]

        if current_price > ma60:
            return "BUY"
        if current_price < ma60:
            return "SELL"
        return "WAIT"
    except Exception:
        return "WAIT"


def get_ema238(data):
    symbol = "BTC/USDT"
    limit = 300
    period = 238

    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=TREND_TIMEFRAME, limit=limit)
        closes = [candle[4] for candle in candles]
        if len(closes) < period:
            return "WAIT"

        multiplier = 2 / (period + 1)
        ema = sum(closes[:period]) / period

        for close in closes[period:]:
            ema = ((close - ema) * multiplier) + ema

        current_price = closes[-1]
        if current_price > ema:
            return "BUY"
        if current_price < ema:
            return "SELL"
        return "WAIT"
    except Exception:
        return "WAIT"


def get_rsi(data):
    symbol = "BTC/USDT"
    limit = 100
    period = 14

    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=CONFIRM_TIMEFRAME, limit=limit)
        closes = [candle[4] for candle in candles]
        if len(closes) < period + 1:
            return "WAIT"

        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent_deltas = deltas[-period:]
        gains = [delta for delta in recent_deltas if delta > 0]
        losses = [-delta for delta in recent_deltas if delta < 0]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        if rsi > 70:
            return "SELL"
        if rsi < 30:
            return "BUY"
        return "WAIT"
    except Exception:
        return "WAIT"


def get_fvg(data):
    return "WAIT"


def get_bag(data):
    return "WAIT"


def get_fibo(data):
    return "WAIT"


def get_all_indicators(data):
    return {
        "MA60": get_ma60(data),
        "EMA238": get_ema238(data),
        "RSI": get_rsi(data),
        "FVG": get_fvg(data),
        "BAG": get_bag(data),
        "FIBO": get_fibo(data),
    }
