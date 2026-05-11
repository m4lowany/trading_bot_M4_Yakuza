def _body_size(candle):
    return abs(candle[4] - candle[1])


def _range_size(candle):
    return candle[2] - candle[3]


def analyze_market_structure(candles):
    if not candles or len(candles) < 6:
        return {
            "structure": "SIDEWAYS",
            "higher_high": False,
            "higher_low": False,
            "lower_high": False,
            "lower_low": False,
            "momentum": "WEAK",
            "reversal_chance": "LOW",
            "liquidity_event": False,
        }

    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    closes = [c[4] for c in candles]

    higher_high = highs[-1] > highs[-2]
    higher_low = lows[-1] > lows[-2]
    lower_high = highs[-1] < highs[-2]
    lower_low = lows[-1] < lows[-2]

    higher_high_series = highs[-1] > highs[-2] > highs[-3]
    lower_low_series = lows[-1] < lows[-2] < lows[-3]

    if higher_high_series and higher_low:
        structure = "BULLISH"
    elif lower_low_series and lower_high:
        structure = "BEARISH"
    else:
        structure = "SIDEWAYS"

    previous_bodies = [_body_size(c) for c in candles[-5:-1]]
    avg_prev_body = sum(previous_bodies) / len(previous_bodies) if previous_bodies else 0
    last_candle = candles[-1]
    prev_candle = candles[-2]
    last_body = _body_size(last_candle)

    strong_momentum = avg_prev_body > 0 and last_body > (avg_prev_body * 1.2)
    bearish_dump = prev_candle[4] < prev_candle[1] and _body_size(prev_candle) > (avg_prev_body * 1.5)
    weak_bounce_after_dump = (
        bearish_dump
        and last_candle[4] > last_candle[1]
        and _body_size(last_candle) < (_body_size(prev_candle) * 0.4)
    )

    momentum = "STRONG" if strong_momentum and not weak_bounce_after_dump else "WEAK"

    # Test poziomu: dotknięcie ostatniego wsparcia/oporu i reakcja zamknięciem.
    recent_support = min(lows[-6:-1])
    recent_resistance = max(highs[-6:-1])
    bullish_reaction = last_candle[3] <= recent_support and last_candle[4] > last_candle[1]
    bearish_reaction = last_candle[2] >= recent_resistance and last_candle[4] < last_candle[1]

    if (bullish_reaction or bearish_reaction) and momentum == "STRONG":
        reversal_chance = "HIGH"
    elif bullish_reaction or bearish_reaction:
        reversal_chance = "MEDIUM"
    else:
        reversal_chance = "LOW"

    last_range = _range_size(last_candle)
    close_position = (
        (last_candle[4] - last_candle[3]) / last_range if last_range > 0 else 0.5
    )

    huge_bearish_candle = last_candle[4] < last_candle[1] and (
        avg_prev_body > 0 and last_body > (avg_prev_body * 1.8)
    )
    support_breakdown = last_candle[3] < recent_support and last_candle[4] < recent_support
    no_buyer_reaction = close_position < 0.25
    high_bearish_momentum = momentum == "STRONG" and last_candle[4] < last_candle[1]

    liquidity_event = (
        huge_bearish_candle
        and support_breakdown
        and no_buyer_reaction
        and high_bearish_momentum
    )

    # Dodatkowy warunek: przebicie poziomu bez reakcji i mocny follow-through.
    if support_breakdown and no_buyer_reaction and lower_low_series and high_bearish_momentum:
        liquidity_event = True

    return {
        "structure": structure,
        "higher_high": higher_high,
        "higher_low": higher_low,
        "lower_high": lower_high,
        "lower_low": lower_low,
        "momentum": momentum,
        "reversal_chance": reversal_chance,
        "liquidity_event": liquidity_event,
    }
