from indicators import get_all_indicators
from market_structure import analyze_market_structure
from scoring import calculate_score
from signals import get_signal


def _default_fvg():
    return {
        "fvg_signal": "WAIT",
        "fvg_type": "NONE",
        "gap_size_percent": 0.0,
        "fvg_touched": False,
        "rejection_after_touch": False,
    }


def compute_timeframe_signal(indicator_status, structure_data):
    """Score + structure bonuses for a single timeframe -> BUY/SELL/WAIT."""
    fvg_data = indicator_status.get("FVG", _default_fvg())
    score = calculate_score(indicator_status)

    if fvg_data["fvg_type"] == "BULLISH" and fvg_data["rejection_after_touch"]:
        score += 1
    elif fvg_data["fvg_type"] == "BEARISH" and fvg_data["rejection_after_touch"]:
        score -= 1

    if (
        structure_data["structure"] == "BULLISH"
        and structure_data["structure_strength"] == "STRONG"
        and structure_data["momentum"] == "STRONG"
    ):
        score += 1
    elif (
        structure_data["structure"] == "BEARISH"
        and structure_data["structure_strength"] == "STRONG"
        and structure_data["momentum"] == "STRONG"
    ):
        score -= 1

    return get_signal(score)


def analyze_timeframe(candles):
    """Run indicators + market structure and return per-TF analysis."""
    indicator_status = get_all_indicators(candles)
    structure_data = analyze_market_structure(candles)
    signal = compute_timeframe_signal(indicator_status, structure_data)
    return {
        "indicator_status": indicator_status,
        "structure_data": structure_data,
        "signal": signal,
    }


def analyze_timeframe_alignment(
    trend_tf_signal,
    confirm_tf_signal,
    entry_tf_signal,
    *,
    trend_structure_strength="WEAK",
    confirm_structure_strength="WEAK",
    entry_structure_strength="WEAK",
):
    """
    Compare BUY/SELL/WAIT across trend, confirm and entry timeframes.
    """
    bullish = {"BUY"}
    bearish = {"SELL"}

    if (
        trend_tf_signal in bullish
        and confirm_tf_signal in bullish
        and entry_tf_signal in bullish
    ):
        alignment = "FULL_BULLISH"
    elif (
        trend_tf_signal in bearish
        and confirm_tf_signal in bearish
        and entry_tf_signal in bearish
    ):
        alignment = "FULL_BEARISH"
    else:
        alignment = "MIXED"

    strengths = [
        trend_structure_strength,
        confirm_structure_strength,
        entry_structure_strength,
    ]

    if alignment == "MIXED":
        alignment_strength = "WEAK"
    elif all(s == "STRONG" for s in strengths):
        alignment_strength = "STRONG"
    elif sum(1 for s in strengths if s == "STRONG") >= 2 or all(
        s in ("STRONG", "MEDIUM") for s in strengths
    ):
        alignment_strength = "MEDIUM"
    else:
        alignment_strength = "WEAK"

    return {
        "trend_tf_signal": trend_tf_signal,
        "confirm_tf_signal": confirm_tf_signal,
        "entry_tf_signal": entry_tf_signal,
        "alignment": alignment,
        "alignment_strength": alignment_strength,
    }


def apply_alignment_to_confidence(
    confidence_data,
    alignment_data,
    signal,
    structure_data,
    *,
    fake_breakout=False,
    liquidity_event=False,
):
    """
    Adjust confidence and entry_quality based on multi-timeframe alignment.
    """
    confidence = confidence_data["confidence"]
    entry_quality = confidence_data["entry_quality"]
    reasons = list(confidence_data["confidence_reasons"])

    alignment = alignment_data["alignment"]
    alignment_strength = alignment_data["alignment_strength"]
    structure_strength = structure_data.get("structure_strength", "WEAK")

    if alignment == "FULL_BULLISH" and signal == "BUY":
        confidence += 1
        reasons.append("+ FULL_BULLISH alignment with BUY")
    elif alignment == "FULL_BEARISH" and signal == "SELL":
        confidence += 1
        reasons.append("+ FULL_BEARISH alignment with SELL")
    elif alignment == "MIXED":
        confidence -= 1
        reasons.append("- MIXED timeframe alignment")

    confidence = max(0, min(5, confidence))

    if alignment == "MIXED" and entry_quality == "HIGH":
        entry_quality = "MEDIUM"
        reasons.append("MIXED alignment -> entry_quality capped at MEDIUM")
    elif (
        alignment in ("FULL_BULLISH", "FULL_BEARISH")
        and alignment_strength == "STRONG"
        and confidence >= 3
        and structure_strength in ("STRONG", "MEDIUM")
        and not fake_breakout
        and not liquidity_event
        and signal != "WAIT"
    ):
        if entry_quality != "HIGH":
            entry_quality = "HIGH"
            reasons.append("+ STRONG TF alignment supports HIGH entry")

    return {
        "confidence": confidence,
        "entry_quality": entry_quality,
        "confidence_reasons": reasons,
    }


def apply_alignment_final_filter(signal, confidence_data, alignment_data):
    """
    Final gate after calculate_confidence / alignment confidence tweaks.
    Enforces signal and trade rules from TF alignment without touching scoring.
    """
    alignment = alignment_data["alignment"]
    confidence = confidence_data["confidence"]
    entry_quality = confidence_data["entry_quality"]
    reasons = list(confidence_data["confidence_reasons"])
    trade_allowed = True

    if alignment == "MIXED":
        if signal != "WAIT":
            reasons.append("final filter: MIXED alignment -> SIGNAL forced to WAIT")
        signal = "WAIT"
        trade_allowed = False
        confidence = min(confidence, 2)
        if entry_quality == "HIGH":
            entry_quality = "MEDIUM"
            reasons.append("final filter: MIXED -> entry_quality capped (no HIGH)")
        reasons.append("final filter: MIXED -> confidence max 2, trade blocked")

    elif alignment == "FULL_BULLISH":
        if signal == "SELL":
            signal = "WAIT"
            reasons.append("final filter: FULL_BULLISH -> only BUY allowed, SELL blocked")
        if signal != "BUY":
            trade_allowed = False

    elif alignment == "FULL_BEARISH":
        if signal == "BUY":
            signal = "WAIT"
            reasons.append("final filter: FULL_BEARISH -> only SELL allowed, BUY blocked")
        if signal != "SELL":
            trade_allowed = False

    return {
        "signal": signal,
        "confidence_data": {
            "confidence": confidence,
            "entry_quality": entry_quality,
            "confidence_reasons": reasons,
        },
        "trade_allowed": trade_allowed,
    }
