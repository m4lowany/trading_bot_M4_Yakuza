def _extract_indicator_signal(value):
    if isinstance(value, dict):
        for key in ("signal", "fvg_signal", "fibo_signal", "setup_signal"):
            signal = value.get(key)
            if signal:
                return signal
        return "WAIT"
    return value


def calculate_score(indicators):
    score = 0

    for name, value in indicators.items():
        value = _extract_indicator_signal(value)
        if value in ("BUY", "BULLISH"):
            score += 1

        elif value in ("SELL", "BEARISH"):
            score -= 1

    return score


def calculate_confidence(
    score,
    signal,
    structure_data,
    price_action_data,
    fvg_data,
    fibo_data=None,
):
    """
    Yakuza-style ocena jakości setupu.

    score / get_signal decydują o kierunku (BUY/SELL/WAIT).
    calculate_confidence decyduje czy w ogóle warto siadać przy stole:
        - confidence  : 0..5
        - entry_quality: LOW / MEDIUM / HIGH
        - confidence_reasons: list[str] (po co/dlaczego)

    Reguły (krótko):
    - baza = abs(score), capowane do 0..5
    - mocna struktura zgodna z sygnałem = +1
    - sideways / weak structure = -1
    - mocne momentum zgodne z sygnałem = +1
    - wick rejection zgodny z sygnałem = +1
    - reakcja na support/resistance zgodna z sygnałem = +1
    - FVG rejection_after_touch zgodne z sygnałem = +1
    - FVG przeciwnego kierunku już dotknięte = -2
    - fake_breakout = -1
    - liquidity_event = HARD OVERRIDE: confidence = 0, entry_quality = LOW
    """
    reasons = []

    confidence = max(0, min(5, abs(int(score))))
    reasons.append(f"base abs(score) = {confidence}")

    structure = structure_data.get("structure", "SIDEWAYS")
    structure_strength = structure_data.get("structure_strength", "WEAK")
    momentum = structure_data.get("momentum", "WEAK")
    liquidity_event = bool(structure_data.get("liquidity_event", False))

    wick_rejection = price_action_data.get("wick_rejection", "NONE")
    fake_breakout = bool(price_action_data.get("fake_breakout", False))
    support_reaction = bool(price_action_data.get("support_reaction", False))
    resistance_reaction = bool(price_action_data.get("resistance_reaction", False))

    fvg_type = fvg_data.get("fvg_type", "NONE")
    fvg_touched = bool(fvg_data.get("fvg_touched", False))
    rejection_after_touch = bool(fvg_data.get("rejection_after_touch", False))

    fibo_data = fibo_data or {}
    fibo_signal = fibo_data.get("fibo_signal", "WAIT")
    fibo_direction = fibo_data.get("fibo_direction", "NEUTRAL")
    fibo_zone = fibo_data.get("fibo_zone", "NONE")
    fibo_retracement = float(fibo_data.get("retracement", 0.0) or 0.0)

    if signal == "BUY":
        if structure == "BULLISH" and structure_strength == "STRONG":
            confidence += 1
            reasons.append("+ structure STRONG bullish aligned")
        if momentum == "STRONG" and structure == "BULLISH":
            confidence += 1
            reasons.append("+ strong momentum bullish")
        if wick_rejection == "DOWN":
            confidence += 1
            reasons.append("+ wick rejection DOWN aligned with BUY")
        if support_reaction:
            confidence += 1
            reasons.append("+ support reaction aligned with BUY")
        if fvg_type == "BULLISH" and rejection_after_touch:
            confidence += 1
            reasons.append("+ FVG bullish rejection_after_touch")
        if fvg_type == "BEARISH" and fvg_touched:
            confidence -= 2
            reasons.append("- BEARISH FVG already touched (against BUY)")
        if fibo_direction == "BULLISH" and fibo_zone in ("ENTRY_ZONE", "WATCH_ZONE"):
            confidence += 1
            reasons.append("+ fibo bullish zone supports BUY")
        if fibo_direction == "BEARISH" and fibo_zone == "ENTRY_ZONE":
            confidence -= 1
            reasons.append("- fibo bearish entry zone against BUY")

    elif signal == "SELL":
        if structure == "BEARISH" and structure_strength == "STRONG":
            confidence += 1
            reasons.append("+ structure STRONG bearish aligned")
        if momentum == "STRONG" and structure == "BEARISH":
            confidence += 1
            reasons.append("+ strong momentum bearish")
        if wick_rejection == "UP":
            confidence += 1
            reasons.append("+ wick rejection UP aligned with SELL")
        if resistance_reaction:
            confidence += 1
            reasons.append("+ resistance reaction aligned with SELL")
        if fvg_type == "BEARISH" and rejection_after_touch:
            confidence += 1
            reasons.append("+ FVG bearish rejection_after_touch")
        if fvg_type == "BULLISH" and fvg_touched:
            confidence -= 2
            reasons.append("- BULLISH FVG already touched (against SELL)")
        if fibo_direction == "BEARISH" and fibo_zone in ("ENTRY_ZONE", "WATCH_ZONE"):
            confidence += 1
            reasons.append("+ fibo bearish zone supports SELL")
        if fibo_direction == "BULLISH" and fibo_zone == "ENTRY_ZONE":
            confidence -= 1
            reasons.append("- fibo bullish entry zone against SELL")

    if structure == "SIDEWAYS":
        confidence -= 1
        reasons.append("- sideways structure (trap risk)")
    if structure_strength == "WEAK":
        confidence -= 1
        reasons.append("- weak structure")
    if fake_breakout:
        confidence -= 1
        reasons.append("- fake breakout risk")

    if liquidity_event:
        confidence = 0
        reasons.append("!! liquidity event -> confidence forced to 0")

    if signal == "WAIT":
        confidence = 0
        reasons.append("signal=WAIT -> confidence 0")

    confidence = max(0, min(5, confidence))

    if fibo_signal in ("BUY", "SELL") and signal != "WAIT":
        if fibo_signal == signal:
            confidence += 1
            reasons.append("+ fibo signal aligned with trade direction")
        else:
            confidence -= 1
            reasons.append("- fibo signal opposite to trade direction")
    elif fibo_retracement >= 0.786 and fibo_direction in ("BULLISH", "BEARISH"):
        reasons.append("fibo deep pullback zone -> wait for better reaction")

    if liquidity_event or signal == "WAIT":
        entry_quality = "LOW"
    elif (
        confidence >= 4
        and structure_strength == "STRONG"
        and not fake_breakout
    ):
        entry_quality = "HIGH"
    elif confidence >= 2:
        entry_quality = "MEDIUM"
    else:
        entry_quality = "LOW"

    return {
        "confidence": confidence,
        "entry_quality": entry_quality,
        "confidence_reasons": reasons,
    }
