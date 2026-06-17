"""
Structure events from raw candles: swings, BOS, CHOCH, control shift.

OBSERVER ONLY — for logs and setup_history.jsonl.
Must not feed scoring, signals, setup_engine, risk_manager, or paper_trader.
"""

SWING_LOOKBACK = 3
SWING_REACTION_BARS = 2
SWING_REACTION_MIN_MOVE = 0.001  # 0.1% — ignore micro noise
MIN_CANDLES = SWING_LOOKBACK * 2 + SWING_REACTION_BARS + 5


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
        "wick_only_break": False,
        "wick_break_side": "NONE",
        "sweep_type": "NONE",
        "break_validity": "NONE",
        "fake_breakout": False,
        "structure_character": "NEUTRAL",
        "choch_state": "NONE",
        "choch_is_first_in_leg": False,
        "last_hl": None,
        "last_lh": None,
        "structure_phase": "CONTINUATION",
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


def _swing_has_reaction(candles, swing_idx, kind, level):
    """Swing is valid only if price reacted away after the extremum."""
    n = len(candles)
    reaction_end = swing_idx + SWING_REACTION_BARS + 1
    if swing_idx + 1 >= reaction_end or reaction_end > n:
        return False

    threshold_down = level * (1.0 - SWING_REACTION_MIN_MOVE)
    threshold_up = level * (1.0 + SWING_REACTION_MIN_MOVE)

    for j in range(swing_idx + 1, reaction_end):
        candle = candles[j]
        close = candle[4]
        if kind == "high":
            if close < threshold_down:
                return True
            if j > swing_idx + 1 and candle[3] < candles[j - 1][3]:
                return True
        else:
            if close > threshold_up:
                return True
            if j > swing_idx + 1 and candle[2] > candles[j - 1][2]:
                return True
    return False


def _filter_valid_swings(candles, swing_highs, swing_lows):
    """Keep swings with confirmed post-swing reaction, usable before the last bar."""
    n = len(candles)
    cutoff = n - 1
    valid_highs = []
    valid_lows = []

    for idx, price in swing_highs:
        if idx >= cutoff:
            continue
        if _swing_has_reaction(candles, idx, "high", price):
            valid_highs.append((idx, price))

    for idx, price in swing_lows:
        if idx >= cutoff:
            continue
        if _swing_has_reaction(candles, idx, "low", price):
            valid_lows.append((idx, price))

    return valid_highs, valid_lows


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


def _compute_leg_levels(valid_highs, valid_lows):
    """Last HL (higher low) and LH (lower high) from classified valid swings."""
    last_hl = None
    last_lh = None

    for i in range(1, len(valid_lows)):
        if valid_lows[i][1] > valid_lows[i - 1][1]:
            last_hl = valid_lows[i][1]

    for i in range(1, len(valid_highs)):
        if valid_highs[i][1] < valid_highs[i - 1][1]:
            last_lh = valid_highs[i][1]

    return last_hl, last_lh


def _detect_wick_only_break(candle, level, side):
    if level is None:
        return False, "NONE"
    high, low, close = candle[2], candle[3], candle[4]
    if side == "HIGH" and high > level and close <= level:
        return True, "HIGH"
    if side == "LOW" and low < level and close >= level:
        return True, "LOW"
    return False, "NONE"


def _is_fake_reclaim(candle, prev_candle, level, side):
    """Previous bar closed beyond level; current bar reclaimed inside (2-bar fake)."""
    if prev_candle is None or level is None:
        return False
    prev_close = prev_candle[4]
    close = candle[4]
    if side == "HIGH":
        return prev_close > level and close <= level
    if side == "LOW":
        return prev_close < level and close >= level
    return False


def _evaluate_break_attempt(candle, prev_candle, level, side):
    """
    Classify a single level test on the current bar.
    Returns dict with wick_only, fake_reclaim, close_break booleans.
    """
    if level is None:
        return {
            "wick_only": False,
            "wick_side": "NONE",
            "fake_reclaim": False,
            "close_break": False,
        }

    wick_only, wick_side = _detect_wick_only_break(candle, level, side)
    fake_reclaim = _is_fake_reclaim(candle, prev_candle, level, side)
    close = candle[4]

    close_break = False
    if side == "HIGH" and close > level and not wick_only and not fake_reclaim:
        close_break = True
    if side == "LOW" and close < level and not wick_only and not fake_reclaim:
        close_break = True

    return {
        "wick_only": wick_only,
        "wick_side": wick_side,
        "fake_reclaim": fake_reclaim,
        "close_break": close_break,
    }


class _StructureStateMachine:
    def __init__(self):
        self.character = "NEUTRAL"
        self.choch_fired_in_leg = False
        self.last_choch = "NONE"
        self.structure_phase = "CONTINUATION"

    def reset_leg(self, new_character):
        self.character = new_character
        self.choch_fired_in_leg = False
        self.structure_phase = "CONTINUATION"

    def apply_choch(self, choch):
        self.last_choch = choch
        self.choch_fired_in_leg = True
        self.structure_phase = "TRANSITION"
        if choch == "CHOCH_BULLISH":
            self.character = "BULLISH"
        elif choch == "CHOCH_BEARISH":
            self.character = "BEARISH"


def _resolve_structure_event(
    *,
    character,
    choch_fired_in_leg,
    close_break_up,
    close_break_down,
    last_lh,
    last_hl,
    last_swing_high,
    last_swing_low,
):
    """
    Map close breaks to BOS or first CHOCH in the current structure leg.
    Yakuza: CHOCH breaks last LH (bear->bull) or last HL (bull->bear).
    BOS continues structure: close beyond last swing high/low in trend direction.
    """
    bos = "NONE"
    choch = "NONE"
    broken_level = None
    choch_is_first = False
    reasons = []

    if close_break_up:
        level = last_lh if character in ("BEARISH", "NEUTRAL") and last_lh is not None else None
        choch_level = last_lh
        bos_level = last_swing_high

        if character == "BEARISH" and choch_level is not None:
            if not choch_fired_in_leg:
                choch = "CHOCH_BULLISH"
                broken_level = choch_level
                choch_is_first = True
                reasons.append(
                    f"close above last LH={choch_level:.8f} in bearish structure (first CHOCH)"
                )
            else:
                reasons.append("bullish close break after CHOCH already fired in leg")
        elif character == "BULLISH" and bos_level is not None:
            bos = "BOS_BULLISH"
            broken_level = bos_level
            reasons.append(
                f"close above last swing high={bos_level:.8f} in bullish structure (BOS)"
            )
        elif level is not None and character == "NEUTRAL":
            choch = "CHOCH_BULLISH"
            broken_level = level
            choch_is_first = True
            reasons.append(f"close above last LH={level:.8f} (CHoCH from neutral)")

    if close_break_down:
        level = last_hl if character in ("BULLISH", "NEUTRAL") and last_hl is not None else None
        choch_level = last_hl
        bos_level = last_swing_low

        if character == "BULLISH" and choch_level is not None:
            if not choch_fired_in_leg:
                choch = "CHOCH_BEARISH"
                broken_level = choch_level
                choch_is_first = True
                reasons.append(
                    f"close below last HL={choch_level:.8f} in bullish structure (first CHOCH)"
                )
            else:
                reasons.append("bearish close break after CHOCH already fired in leg")
        elif character == "BEARISH" and bos_level is not None:
            bos = "BOS_BEARISH"
            broken_level = bos_level
            reasons.append(
                f"close below last swing low={bos_level:.8f} in bearish structure (BOS)"
            )
        elif level is not None and character == "NEUTRAL":
            choch = "CHOCH_BEARISH"
            broken_level = level
            choch_is_first = True
            reasons.append(f"close below last HL={level:.8f} (CHoCH from neutral)")

    if bos != "NONE" and choch != "NONE":
        # Prefer CHOCH when both fire (character change dominates).
        bos = "NONE"
        reasons.append("CHOCH takes priority over BOS on same bar")

    return bos, choch, broken_level, choch_is_first, reasons


def _run_state_machine(candles, valid_highs, valid_lows):
    sm = _StructureStateMachine()
    last_bar = {
        "bos": "NONE",
        "choch": "NONE",
        "broken_level": None,
        "wick_only_break": False,
        "wick_break_side": "NONE",
        "sweep_type": "NONE",
        "break_validity": "NONE",
        "fake_breakout": False,
        "choch_is_first_in_leg": False,
        "reasons": [],
    }

    for i in range(1, len(candles)):
        highs_before = [(idx, price) for idx, price in valid_highs if idx < i]
        lows_before = [(idx, price) for idx, price in valid_lows if idx < i]
        if len(highs_before) < 2 or len(lows_before) < 2:
            continue

        prior = _infer_prior_structure(highs_before, lows_before)
        if sm.character == "NEUTRAL" and prior in ("BULLISH", "BEARISH"):
            sm.character = prior

        last_hl, last_lh = _compute_leg_levels(highs_before, lows_before)
        last_swing_high = highs_before[-1][1]
        last_swing_low = lows_before[-1][1]

        candle = candles[i]
        prev = candles[i - 1]

        up_level = last_lh if sm.character in ("BEARISH", "NEUTRAL") else last_swing_high
        down_level = last_hl if sm.character in ("BULLISH", "NEUTRAL") else last_swing_low
        if up_level is None:
            up_level = last_swing_high
        if down_level is None:
            down_level = last_swing_low

        up_attempt = _evaluate_break_attempt(candle, prev, up_level, "HIGH")
        down_attempt = _evaluate_break_attempt(candle, prev, down_level, "LOW")

        bar_result = dict(last_bar)
        bar_result["reasons"] = []

        wick_only = up_attempt["wick_only"] or down_attempt["wick_only"]
        fake_reclaim = up_attempt["fake_reclaim"] or down_attempt["fake_reclaim"]

        if wick_only:
            side = up_attempt["wick_side"] if up_attempt["wick_only"] else down_attempt["wick_side"]
            level = up_level if up_attempt["wick_only"] else down_level
            bar_result["wick_only_break"] = True
            bar_result["wick_break_side"] = side
            bar_result["sweep_type"] = "SWEEP_HIGH" if side == "HIGH" else "SWEEP_LOW"
            bar_result["break_validity"] = "WICK_ONLY"
            bar_result["reasons"].append(
                f"wick-only break {'above' if side == 'HIGH' else 'below'} "
                f"level={level:.8f} (sweep, not BOS)"
            )
        elif fake_reclaim:
            bar_result["fake_breakout"] = True
            bar_result["break_validity"] = "FAKE_RECLAIM"
            if up_attempt["fake_reclaim"]:
                bar_result["reasons"].append(
                    f"fake reclaim above level={up_level:.8f} (prev close broke, reclaimed)"
                )
            if down_attempt["fake_reclaim"]:
                bar_result["reasons"].append(
                    f"fake reclaim below level={down_level:.8f} (prev close broke, reclaimed)"
                )
        else:
            bos, choch, broken_level, choch_first, struct_reasons = _resolve_structure_event(
                character=sm.character,
                choch_fired_in_leg=sm.choch_fired_in_leg,
                close_break_up=up_attempt["close_break"],
                close_break_down=down_attempt["close_break"],
                last_lh=last_lh,
                last_hl=last_hl,
                last_swing_high=last_swing_high,
                last_swing_low=last_swing_low,
            )
            bar_result["bos"] = bos
            bar_result["choch"] = choch
            bar_result["broken_level"] = broken_level
            bar_result["choch_is_first_in_leg"] = choch_first
            bar_result["reasons"].extend(struct_reasons)
            if bos != "NONE":
                bar_result["break_validity"] = "BOS"
            elif choch != "NONE":
                bar_result["break_validity"] = "CHOCH"

        if bar_result["choch"] != "NONE":
            sm.apply_choch(bar_result["choch"])
        elif bar_result["bos"] != "NONE":
            sm.structure_phase = "CONTINUATION"
            if bar_result["bos"] == "BOS_BULLISH":
                sm.character = "BULLISH"
            elif bar_result["bos"] == "BOS_BEARISH":
                sm.character = "BEARISH"

        if i == len(candles) - 1:
            last_bar = bar_result

    return sm, last_bar


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


def _grade_event_strength(bos, choch, buyers, sellers, break_validity):
    if break_validity in ("WICK_ONLY", "FAKE_RECLAIM"):
        return "LOW"

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

    valid_highs, valid_lows = _filter_valid_swings(candles, swing_highs, swing_lows)
    if len(valid_highs) < 2 or len(valid_lows) < 2:
        result = _default_events()
        result["event_reasons"] = [
            "insufficient valid swings with reaction",
            f"raw_swings high={len(swing_highs)} low={len(swing_lows)}",
            f"valid_swings high={len(valid_highs)} low={len(valid_lows)}",
        ]
        return result

    last_swing_high = valid_highs[-1][1]
    last_swing_low = valid_lows[-1][1]
    last_hl, last_lh = _compute_leg_levels(valid_highs, valid_lows)
    prior_structure = _infer_prior_structure(valid_highs, valid_lows)

    sm, last_bar = _run_state_machine(candles, valid_highs, valid_lows)

    bos = last_bar["bos"]
    choch = last_bar["choch"]
    broken_level = last_bar["broken_level"]
    buyers, sellers, control_reasons = _detect_control_shift(candles)

    reasons = [
        f"prior structure={prior_structure}",
        f"valid_swings high={len(valid_highs)} low={len(valid_lows)}",
        f"last_HL={last_hl}",
        f"last_LH={last_lh}",
        f"structure_character={sm.character}",
        f"structure_phase={sm.structure_phase}",
    ]
    reasons.extend(last_bar.get("reasons", []))
    reasons.extend(control_reasons)

    if (
        bos == "NONE"
        and choch == "NONE"
        and not buyers
        and not sellers
        and last_bar.get("break_validity") == "NONE"
    ):
        reasons.append("no decisive structure event on last candle")

    control_shift = "NONE"
    if buyers and not sellers:
        control_shift = "BUYERS"
    elif sellers and not buyers:
        control_shift = "SELLERS"

    choch_state = choch if choch != "NONE" else sm.last_choch if sm.structure_phase == "TRANSITION" else "NONE"

    event_strength = _grade_event_strength(
        bos, choch, buyers, sellers, last_bar.get("break_validity", "NONE")
    )

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
        "wick_only_break": last_bar.get("wick_only_break", False),
        "wick_break_side": last_bar.get("wick_break_side", "NONE"),
        "sweep_type": last_bar.get("sweep_type", "NONE"),
        "break_validity": last_bar.get("break_validity", "NONE"),
        "fake_breakout": last_bar.get("fake_breakout", False),
        "structure_character": sm.character,
        "choch_state": choch_state,
        "choch_is_first_in_leg": last_bar.get("choch_is_first_in_leg", False),
        "last_hl": last_hl,
        "last_lh": last_lh,
        "structure_phase": sm.structure_phase,
    }
