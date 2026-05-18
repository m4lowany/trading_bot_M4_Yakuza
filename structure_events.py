"""
Structure events from raw candles: swings, BOS, CHOCH, control shift.

OBSERVER ONLY — for logs and setup_history.jsonl.
Must not feed scoring, signals, setup_engine, risk_manager, or paper_trader.
"""

SWING_LOOKBACK = 2
MIN_CANDLES = 12


def _default_events():
    return {
        "bos": "NONE",
        "choch": "NONE",
        "last_swing_high": None,
        "last_swing_low": None,
        "broken_level": None,
        "buyers_take_control": False,
        "sellers_take_control": False,
        "control_shift": "NONE",
        "event_strength": "LOW",
        "event_reasons": [],
    }


def _body_size(candle):
    return abs(candle[4] - candle[1])


def _lower_wick(candle):
    body_bottom = min(candle[1], candle[4])
    return max(body_bottom - candle[3], 0.0)


def _upper_wick(candle):
    body_top = max(candle[1], candle[4])
    return max(candle[2] - body_top, 0.0)


def _find_swings(candles, lookback=SWING_LOOKBACK):
    swing_highs = []
    swing_lows = []
    n = len(candles)

    for i in range(lookback, n - lookback):
        high = candles[i][2]
        low = candles[i][3]
        window_highs = [candles[j][2] for j in range(i - lookback, i + lookback + 1)]
        window_lows = [candles[j][3] for j in range(i - lookback, i + lookback + 1)]

        if high == max(window_highs):
            swing_highs.append((i, high))
        if low == min(window_lows):
            swing_lows.append((i, low))

    return swing_highs, swing_lows


def _infer_prior_structure(swing_highs, swing_lows):
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "NEUTRAL"

    hh = swing_highs[-1][1] > swing_highs[-2][1]
    hl = swing_lows[-1][1] > swing_lows[-2][1]
    lh = swing_highs[-1][1] < swing_highs[-2][1]
    ll = swing_lows[-1][1] < swing_lows[-2][1]

    if hh and hl:
        return "BULLISH"
    if lh and ll:
        return "BEARISH"
    return "NEUTRAL"


def _detect_bos_choch(close, prior_structure, last_swing_high, last_swing_low):
    bos = "NONE"
    choch = "NONE"
    broken_level = None
    reasons = []

    if last_swing_high is not None and close > last_swing_high:
        if prior_structure == "BULLISH":
            bos = "BOS_BULLISH"
            broken_level = last_swing_high
            reasons.append("close above last swing high in bullish structure (BOS)")
        elif prior_structure == "BEARISH":
            choch = "CHOCH_BULLISH"
            broken_level = last_swing_high
            reasons.append("close above last lower high in bearish structure (CHoCH)")

    if last_swing_low is not None and close < last_swing_low:
        if prior_structure == "BEARISH":
            bos = "BOS_BEARISH"
            broken_level = last_swing_low
            reasons.append("close below last swing low in bearish structure (BOS)")
        elif prior_structure == "BULLISH":
            choch = "CHOCH_BEARISH"
            broken_level = last_swing_low
            reasons.append("close below last higher low in bullish structure (CHoCH)")

    return bos, choch, broken_level, reasons


def _detect_control_shift(candles):
    reasons = []
    buyers = False
    sellers = False

    if len(candles) < 2:
        return buyers, sellers, reasons

    prev = candles[-2]
    last = candles[-1]
    prev_bear = prev[4] < prev[1]
    prev_bull = prev[4] > prev[1]
    last_bull = last[4] > last[1]
    last_bear = last[4] < last[1]

    last_body = _body_size(last)
    lower_wick = _lower_wick(last)
    upper_wick = _upper_wick(last)

    if prev_bear and last_bull and last[4] > prev[1]:
        buyers = True
        reasons.append("bullish candle closed above prior bearish body")
        if lower_wick > last_body * 0.8:
            reasons.append("lower wick reaction (buyers defending)")

    if prev_bull and last_bear and last[4] < prev[1]:
        sellers = True
        reasons.append("bearish candle closed below prior bullish body")
        if upper_wick > last_body * 0.8:
            reasons.append("upper wick reaction (sellers rejecting)")

    return buyers, sellers, reasons


def _grade_event_strength(bos, choch, buyers, sellers):
    has_structure = bos != "NONE" or choch != "NONE"
    has_control = buyers or sellers

    if has_structure and has_control:
        return "HIGH"
    if has_structure or has_control:
        return "MEDIUM"
    return "LOW"


def analyze_structure_events(candles):
    """
    Detect BOS, CHoCH, swing levels and buyer/seller control from OHLCV candles.

    candles: list of [timestamp, open, high, low, close, volume]
    """
    if not candles or len(candles) < MIN_CANDLES:
        result = _default_events()
        result["event_reasons"] = ["insufficient candles for structure events"]
        return result

    swing_highs, swing_lows = _find_swings(candles)
    if not swing_highs or not swing_lows:
        result = _default_events()
        result["event_reasons"] = ["no swing highs/lows detected"]
        return result

    # Swings before the last candle (confirmed structure, not forming bar)
    confirmed_highs = [s for s in swing_highs if s[0] < len(candles) - 1]
    confirmed_lows = [s for s in swing_lows if s[0] < len(candles) - 1]

    if not confirmed_highs:
        confirmed_highs = swing_highs[:-1] if len(swing_highs) > 1 else swing_highs
    if not confirmed_lows:
        confirmed_lows = swing_lows[:-1] if len(swing_lows) > 1 else swing_lows

    last_swing_high = confirmed_highs[-1][1] if confirmed_highs else None
    last_swing_low = confirmed_lows[-1][1] if confirmed_lows else None

    prior_structure = _infer_prior_structure(confirmed_highs, confirmed_lows)
    close = candles[-1][4]

    bos, choch, broken_level, structure_reasons = _detect_bos_choch(
        close, prior_structure, last_swing_high, last_swing_low
    )
    buyers, sellers, control_reasons = _detect_control_shift(candles)

    reasons = [f"prior structure={prior_structure}"]
    reasons.extend(structure_reasons)
    reasons.extend(control_reasons)

    if bos == "NONE" and choch == "NONE" and not buyers and not sellers:
        reasons.append("no decisive structure event on last candle")

    control_shift = "NONE"
    if buyers and not sellers:
        control_shift = "BUYERS"
    elif sellers and not buyers:
        control_shift = "SELLERS"

    event_strength = _grade_event_strength(bos, choch, buyers, sellers)

    return {
        "bos": bos,
        "choch": choch,
        "last_swing_high": last_swing_high,
        "last_swing_low": last_swing_low,
        "broken_level": broken_level,
        "buyers_take_control": buyers,
        "sellers_take_control": sellers,
        "control_shift": control_shift,
        "event_strength": event_strength,
        "event_reasons": reasons,
    }
