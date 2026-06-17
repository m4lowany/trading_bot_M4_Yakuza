"""
Structure event confluence filter for setup_engine.

Uses analyze_structure_events() output as context filter — never opens trades alone.
"""

from typing import Any, Dict, List, Optional

BLOCK_REASON = "structure confluence blocked setup"


def _is_unavailable(events: Optional[Dict[str, Any]]) -> bool:
    if not events:
        return False
    for reason in events.get("event_reasons") or []:
        if "insufficient" in reason:
            return True
    return False


def _blocked_setup(setup: Dict[str, Any], extra_reasons: List[str]) -> Dict[str, Any]:
    reasons = list(setup.get("setup_reasons", []))
    for item in extra_reasons:
        if item not in reasons:
            reasons.append(item)
    if BLOCK_REASON not in reasons:
        reasons.append(BLOCK_REASON)
    return {
        "setup_type": "NO_SETUP",
        "setup_direction": "WAIT",
        "setup_quality": "LOW",
        "setup_reasons": reasons,
    }


def _downgrade_quality(quality: str) -> str:
    if quality == "HIGH":
        return "MEDIUM"
    if quality == "MEDIUM":
        return "LOW"
    return "LOW"


def _bump_quality(quality: str) -> str:
    if quality == "MEDIUM":
        return "HIGH"
    if quality == "LOW":
        return "MEDIUM"
    return quality


def _apply_penalty(setup: Dict[str, Any], penalty_reasons: List[str]) -> Dict[str, Any]:
    adjusted = dict(setup)
    reasons = list(adjusted.get("setup_reasons", []))
    for item in penalty_reasons:
        if item not in reasons:
            reasons.append(item)
    adjusted["setup_reasons"] = reasons
    adjusted["setup_quality"] = _downgrade_quality(adjusted.get("setup_quality", "LOW"))
    adjusted["setup_confidence_penalty"] = int(adjusted.get("setup_confidence_penalty", 0)) + 1
    return adjusted


def _effective_bos(events: Dict[str, Any]) -> str:
    if events.get("break_validity") != "BOS":
        return "NONE"
    return events.get("bos", "NONE")


def _effective_choch(events: Dict[str, Any]) -> str:
    choch = events.get("choch", "NONE")
    if choch != "NONE":
        return choch
    if events.get("structure_phase") == "TRANSITION":
        state = events.get("choch_state", "NONE")
        if state != "NONE":
            return state
    return "NONE"


def _has_sweep(events: Dict[str, Any]) -> bool:
    if events.get("wick_only_break"):
        return True
    if events.get("break_validity") == "WICK_ONLY":
        return True
    return events.get("sweep_type") in ("SWEEP_HIGH", "SWEEP_LOW")


def _sweep_blocks_long(events: Dict[str, Any]) -> bool:
    if events.get("sweep_type") == "SWEEP_HIGH":
        return True
    return bool(events.get("wick_only_break") and events.get("wick_break_side") == "HIGH")


def _sweep_blocks_short(events: Dict[str, Any]) -> bool:
    if events.get("sweep_type") == "SWEEP_LOW":
        return True
    return bool(events.get("wick_only_break") and events.get("wick_break_side") == "LOW")


def _is_fake_reclaim(events: Dict[str, Any]) -> bool:
    return bool(
        events.get("fake_breakout") or events.get("break_validity") == "FAKE_RECLAIM"
    )


def apply_structure_confluence(
    setup: Dict[str, Any],
    structure_events: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Filter or strengthen an existing setup using BOS/CHOCH/sweep context.

    Fail-open when structure_events is None. Skip filtering when observer data
    is insufficient.
    """
    setup_type = setup.get("setup_type", "NO_SETUP")
    direction = setup.get("setup_direction", "WAIT")

    if setup_type == "NO_SETUP" or direction not in ("BUY", "SELL"):
        return setup

    if structure_events is None:
        return setup

    if _is_unavailable(structure_events):
        adjusted = dict(setup)
        reasons = list(adjusted.get("setup_reasons", []))
        msg = "structure events unavailable (observer skip)"
        if msg not in reasons:
            reasons.append(msg)
        adjusted["setup_reasons"] = reasons
        return adjusted

    events = structure_events
    penalty_reasons: List[str] = []

    if _has_sweep(events):
        sweep_msg = "sweep detected: no BOS confirmation"
        if setup_type == "TREND_CONTINUATION":
            if direction == "BUY" and _sweep_blocks_long(events):
                return _blocked_setup(setup, [sweep_msg, "SWEEP_HIGH blocks long"])
            if direction == "SELL" and _sweep_blocks_short(events):
                return _blocked_setup(setup, [sweep_msg, "SWEEP_LOW blocks short"])
        elif setup_type == "PULLBACK_ENTRY":
            if direction == "BUY" and _sweep_blocks_long(events):
                penalty_reasons.extend([sweep_msg, "SWEEP_HIGH penalizes long pullback"])
            elif direction == "SELL" and _sweep_blocks_short(events):
                penalty_reasons.extend([sweep_msg, "SWEEP_LOW penalizes short pullback"])
        elif direction == "BUY" and _sweep_blocks_long(events):
            penalty_reasons.append(sweep_msg)
        elif direction == "SELL" and _sweep_blocks_short(events):
            penalty_reasons.append(sweep_msg)

    if _is_fake_reclaim(events):
        fake_msg = "fake reclaim: no BOS confirmation"
        if setup_type == "TREND_CONTINUATION":
            return _blocked_setup(setup, [fake_msg])
        penalty_reasons.append(fake_msg)

    choch = _effective_choch(events)
    if setup_type in ("TREND_CONTINUATION", "PULLBACK_ENTRY"):
        if direction == "BUY" and choch == "CHOCH_BEARISH":
            return _blocked_setup(setup, ["CHOCH_BEARISH blocks long"])
        if direction == "SELL" and choch == "CHOCH_BULLISH":
            return _blocked_setup(setup, ["CHOCH_BULLISH blocks short"])

    bos = _effective_bos(events)
    if setup_type == "TREND_CONTINUATION":
        if direction == "BUY" and bos == "BOS_BEARISH":
            return _blocked_setup(setup, ["structure BOS_BEARISH opposes long TC"])
        if direction == "SELL" and bos == "BOS_BULLISH":
            return _blocked_setup(setup, ["structure BOS_BULLISH opposes short TC"])

    result = dict(setup)
    if penalty_reasons:
        result = _apply_penalty(result, penalty_reasons)

    reasons = list(result.get("setup_reasons", []))
    support_reasons: List[str] = []

    if setup_type == "REVERSAL_ATTEMPT":
        if direction == "BUY" and choch == "CHOCH_BULLISH":
            support_reasons.append("CHOCH_BULLISH supports reversal long")
        if direction == "SELL" and choch == "CHOCH_BEARISH":
            support_reasons.append("CHOCH_BEARISH supports reversal short")

    if setup_type == "TREND_CONTINUATION":
        if direction == "BUY" and bos == "BOS_BULLISH":
            support_reasons.append("structure BOS_BULLISH supports long")
        if direction == "SELL" and bos == "BOS_BEARISH":
            support_reasons.append("structure BOS_BEARISH supports short")

    for item in support_reasons:
        if item not in reasons:
            reasons.append(item)
    result["setup_reasons"] = reasons

    if support_reasons and setup_type == "TREND_CONTINUATION":
        result["setup_quality"] = _bump_quality(result.get("setup_quality", "LOW"))

    return result
