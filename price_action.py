def _body_size(candle):
    return abs(candle[4] - candle[1])


def _candle_range(candle):
    return max(candle[2] - candle[3], 0.0)


def _upper_wick(candle):
    body_top = max(candle[1], candle[4])
    return max(candle[2] - body_top, 0.0)


def _lower_wick(candle):
    body_bottom = min(candle[1], candle[4])
    return max(body_bottom - candle[3], 0.0)


def _direction(candle):
    if candle[4] > candle[1]:
        return "BULL"
    if candle[4] < candle[1]:
        return "BEAR"
    return "NEUTRAL"


def analyze_candles(candles):
    default_response = {
        "candle_strength": "WEAK",
        "wick_rejection": "NONE",
        "fake_breakout": False,
        "support_reaction": False,
        "resistance_reaction": False,
        "momentum_shift": False,
    }
    if not candles or len(candles) < 8:
        return default_response

    last = candles[-1]
    prev = candles[-2]
    recent = candles[-7:-1]

    last_body = _body_size(last)
    prev_body = _body_size(prev)
    recent_bodies = [_body_size(c) for c in recent]
    avg_recent_body = sum(recent_bodies) / len(recent_bodies) if recent_bodies else 0.0

    # Siła świecy: duża świeca kierunkowa większa od poprzednich.
    candle_strength = "WEAK"
    large_vs_recent = avg_recent_body > 0 and last_body > avg_recent_body * 1.25
    large_vs_prev = last_body > prev_body * 1.15 if prev_body > 0 else last_body > 0
    if large_vs_recent and large_vs_prev:
        if last[4] > last[1]:
            candle_strength = "STRONG_BULL"
        elif last[4] < last[1]:
            candle_strength = "STRONG_BEAR"

    # Długość knotów i odrzucenie.
    upper_wick = _upper_wick(last)
    lower_wick = _lower_wick(last)
    wick_rejection = "NONE"
    if last_body > 0:
        if lower_wick > last_body * 1.4 and lower_wick > upper_wick * 1.1:
            wick_rejection = "DOWN"
        elif upper_wick > last_body * 1.4 and upper_wick > lower_wick * 1.1:
            wick_rejection = "UP"

    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    recent_resistance = max(highs[-8:-1])
    recent_support = min(lows[-8:-1])

    # Reakcja po dotknięciu poziomu.
    support_reaction = (
        last[3] <= recent_support
        and last[4] > last[1]
        and (last_body > avg_recent_body * 0.9 if avg_recent_body > 0 else True)
    )
    resistance_reaction = (
        last[2] >= recent_resistance
        and last[4] < last[1]
        and (last_body > avg_recent_body * 0.9 if avg_recent_body > 0 else True)
    )

    # Fake breakout: wybicie poziomu i szybki powrót (na 1-2 świecach).
    broke_resistance = prev[2] > recent_resistance and prev[4] > recent_resistance
    returned_below_resistance = last[4] < recent_resistance and _direction(last) == "BEAR"
    broke_support = prev[3] < recent_support and prev[4] < recent_support
    returned_above_support = last[4] > recent_support and _direction(last) == "BULL"
    fake_breakout = (broke_resistance and returned_below_resistance) or (
        broke_support and returned_above_support
    )

    # Momentum: seria coraz mocniejszych świec jednego kierunku.
    recent_three = candles[-3:]
    dirs = [_direction(c) for c in recent_three]
    bodies = [_body_size(c) for c in recent_three]
    same_direction = dirs[0] == dirs[1] == dirs[2] and dirs[2] in ("BULL", "BEAR")
    increasing_power = bodies[2] > bodies[1] > bodies[0] and bodies[2] > 0
    momentum_shift = same_direction and increasing_power

    return {
        "candle_strength": candle_strength,
        "wick_rejection": wick_rejection,
        "fake_breakout": fake_breakout,
        "support_reaction": support_reaction,
        "resistance_reaction": resistance_reaction,
        "momentum_shift": momentum_shift,
    }
