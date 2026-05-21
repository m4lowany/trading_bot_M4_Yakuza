from config import FVG_MIN_GAP_PERCENT
from utils import validate_candles


def get_ma60(data):
    period = 60

    if not validate_candles(data, min_length=period):
        return "WAIT"

    candles = data
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


def get_ema238(data):
    period = 238

    if not validate_candles(data, min_length=period):
        return "WAIT"

    candles = data
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


def get_rsi(data):
    period = 14

    if not validate_candles(data, min_length=period + 1):
        return "WAIT"

    candles = data
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


def get_fvg(data):
    default_response = {
        "fvg_signal": "WAIT",
        "fvg_type": "NONE",
        "gap_size_percent": 0.0,
        "fvg_touched": False,
        "rejection_after_touch": False,
    }
    if not validate_candles(data, min_length=5):
        return default_response

    candles = data
    if len(candles) < 5:
        return default_response

    best_fvg = None
    best_gap_percent = 0.0

    for idx in range(2, len(candles)):
        candle_1 = candles[idx - 2]
        candle_3 = candles[idx]

        bullish_gap = candle_3[3] - candle_1[2]
        bearish_gap = candle_1[3] - candle_3[2]

        if bullish_gap > 0 and candle_1[2] > 0:
            gap_percent = (bullish_gap / candle_1[2]) * 100
            if gap_percent > best_gap_percent:
                best_gap_percent = gap_percent
                best_fvg = {
                    "fvg_type": "BULLISH",
                    "gap_low": candle_1[2],
                    "gap_high": candle_3[3],
                    "created_idx": idx,
                    "gap_size_percent": round(gap_percent, 4),
                }

        if bearish_gap > 0 and candle_1[3] > 0:
            gap_percent = (bearish_gap / candle_1[3]) * 100
            if gap_percent > best_gap_percent:
                best_gap_percent = gap_percent
                best_fvg = {
                    "fvg_type": "BEARISH",
                    "gap_low": candle_3[2],
                    "gap_high": candle_1[3],
                    "created_idx": idx,
                    "gap_size_percent": round(gap_percent, 4),
                }

    if not best_fvg or best_fvg["gap_size_percent"] < FVG_MIN_GAP_PERCENT:
        return default_response

    fvg_touched = False
    rejection_after_touch = False
    last_candle = candles[-1]
    check_from = best_fvg["created_idx"] + 1

    for candle in candles[check_from:]:
        touched = candle[3] <= best_fvg["gap_high"] and candle[2] >= best_fvg["gap_low"]
        if touched:
            fvg_touched = True

            body = abs(candle[4] - candle[1])
            upper_wick = candle[2] - max(candle[1], candle[4])
            lower_wick = min(candle[1], candle[4]) - candle[3]

            if best_fvg["fvg_type"] == "BULLISH":
                # Reakcja po touch: odrzucenie dolem i domknięcie bycze.
                if candle[4] > candle[1] and lower_wick > body * 1.2:
                    rejection_after_touch = True
            else:
                # Reakcja po touch: odrzucenie górą i domknięcie niedźwiedzie.
                if candle[4] < candle[1] and upper_wick > body * 1.2:
                    rejection_after_touch = True

    fvg_signal = "WAIT"
    if best_fvg["fvg_type"] == "BULLISH" and fvg_touched and rejection_after_touch:
        fvg_signal = "BUY"
    elif best_fvg["fvg_type"] == "BEARISH" and fvg_touched and rejection_after_touch:
        fvg_signal = "SELL"
    elif not fvg_touched:
        if best_fvg["fvg_type"] == "BULLISH" and last_candle[4] > last_candle[1]:
            fvg_signal = "BUY"
        elif best_fvg["fvg_type"] == "BEARISH" and last_candle[4] < last_candle[1]:
            fvg_signal = "SELL"

    return {
        "fvg_signal": fvg_signal,
        "fvg_type": best_fvg["fvg_type"],
        "gap_size_percent": best_fvg["gap_size_percent"],
        "fvg_touched": fvg_touched,
        "rejection_after_touch": rejection_after_touch,
    }


def get_bag(data):
    return "WAIT"


def _default_fibo_response():
    return {
        "fibo_signal": "WAIT",
        "fibo_direction": "NEUTRAL",
        "fibo_zone": "NONE",
        "retracement": 0.0,
        "swing_low": None,
        "swing_high": None,
        "level_0_382": None,
        "level_0_5": None,
        "level_0_618": None,
        "level_0_786": None,
        "level_1_272": None,
    }


def get_fibo(data):
    """
    Prosty fibo context:
    - wyznacza swing low/high na ostatnim oknie danych,
    - ocenia, czy cena jest w strefie 0.5-0.786,
    - zwraca BUY/SELL tylko gdy retracement i świeca wejściowa są zgodne.
    """
    default_response = _default_fibo_response()
    if not validate_candles(data, min_length=20):
        return default_response

    candles = data
    lookback = min(len(candles), 80)
    recent = candles[-lookback:]

    highs = [candle[2] for candle in recent]
    lows = [candle[3] for candle in recent]
    opens = [candle[1] for candle in recent]
    closes = [candle[4] for candle in recent]

    swing_high = max(highs)
    swing_low = min(lows)
    swing_range = swing_high - swing_low
    if swing_range <= 0:
        return default_response

    current_price = closes[-1]
    mid_price = swing_low + (swing_range * 0.5)
    lookback_anchor = closes[0]
    recent_trend = current_price - lookback_anchor
    last_bullish = closes[-1] > opens[-1]
    last_bearish = closes[-1] < opens[-1]

    level_0_382 = swing_low + (swing_range * 0.382)
    level_0_5 = swing_low + (swing_range * 0.5)
    level_0_618 = swing_low + (swing_range * 0.618)
    level_0_786 = swing_low + (swing_range * 0.786)
    level_1_272 = swing_low + (swing_range * 1.272)

    fibo_direction = "NEUTRAL"
    fibo_zone = "NONE"
    retracement = 0.0
    fibo_signal = "WAIT"

    bullish_bias = recent_trend >= 0 and current_price >= mid_price
    bearish_bias = recent_trend < 0 and current_price <= mid_price
    if not bullish_bias and not bearish_bias:
        bullish_bias = current_price > mid_price
        bearish_bias = current_price < mid_price

    if bullish_bias:
        fibo_direction = "BULLISH"
        retracement = (swing_high - current_price) / swing_range
        if retracement < 0.382:
            fibo_zone = "EXTENDED"
        elif retracement < 0.5:
            fibo_zone = "WATCH_ZONE"
        elif retracement <= 0.786:
            fibo_zone = "ENTRY_ZONE"
        else:
            fibo_zone = "DEEP_PULLBACK"

        if fibo_zone == "ENTRY_ZONE" and last_bullish:
            fibo_signal = "BUY"
        elif fibo_zone == "WATCH_ZONE" and last_bullish:
            fibo_signal = "BUY"

    elif bearish_bias:
        fibo_direction = "BEARISH"
        retracement = (current_price - swing_low) / swing_range
        if retracement < 0.382:
            fibo_zone = "EXTENDED"
        elif retracement < 0.5:
            fibo_zone = "WATCH_ZONE"
        elif retracement <= 0.786:
            fibo_zone = "ENTRY_ZONE"
        else:
            fibo_zone = "DEEP_PULLBACK"

        if fibo_zone == "ENTRY_ZONE" and last_bearish:
            fibo_signal = "SELL"
        elif fibo_zone == "WATCH_ZONE" and last_bearish:
            fibo_signal = "SELL"

    return {
        "fibo_signal": fibo_signal,
        "fibo_direction": fibo_direction,
        "fibo_zone": fibo_zone,
        "retracement": round(retracement, 4),
        "swing_low": round(swing_low, 8),
        "swing_high": round(swing_high, 8),
        "level_0_382": round(level_0_382, 8),
        "level_0_5": round(level_0_5, 8),
        "level_0_618": round(level_0_618, 8),
        "level_0_786": round(level_0_786, 8),
        "level_1_272": round(level_1_272, 8),
    }
def get_all_indicators(data):
    return {
        "MA60": get_ma60(data),
        "EMA238": get_ema238(data),
        "RSI": get_rsi(data),
        "FVG": get_fvg(data),
        "BAG": get_bag(data),
        "FIBO": get_fibo(data),
    }
