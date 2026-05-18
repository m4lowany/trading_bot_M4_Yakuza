"""
MTF setup classifier: bias (30m) + context (15m) + entry trigger (5m).

Sits above the legacy alignment filter; does not replace scoring/signals.
"""


def _default_setup():
    return {
        "setup_type": "NO_SETUP",
        "setup_direction": "WAIT",
        "setup_quality": "LOW",
        "setup_reasons": [],
    }


def _structure_bias(structure_data):
    structure = structure_data.get("structure", "SIDEWAYS")
    if structure == "BULLISH":
        return "BULLISH"
    if structure == "BEARISH":
        return "BEARISH"
    return "NEUTRAL"


def _tf_bias(tf_data):
    """Higher-TF bias from market structure, with signal as fallback."""
    structure_data = tf_data.get("structure_data", {})
    signal = tf_data.get("signal", "WAIT")
    struct_bias = _structure_bias(structure_data)

    if struct_bias != "NEUTRAL":
        return struct_bias
    if signal == "BUY":
        return "BULLISH"
    if signal == "SELL":
        return "BEARISH"
    return "NEUTRAL"


def _is_bullish_tf(tf_data):
    structure_data = tf_data.get("structure_data", {})
    return (
        structure_data.get("structure") == "BULLISH"
        or tf_data.get("signal") == "BUY"
    )


def _is_bearish_tf(tf_data):
    structure_data = tf_data.get("structure_data", {})
    return (
        structure_data.get("structure") == "BEARISH"
        or tf_data.get("signal") == "SELL"
    )


def _signal_alignment(trend_signal, confirm_signal, entry_signal):
    bullish = {"BUY"}
    bearish = {"SELL"}
    if (
        trend_signal in bullish
        and confirm_signal in bullish
        and entry_signal in bullish
    ):
        return "FULL_BULLISH"
    if (
        trend_signal in bearish
        and confirm_signal in bearish
        and entry_signal in bearish
    ):
        return "FULL_BEARISH"
    return "MIXED"


def _bullish_entry_triggers(price_action_data, fvg_data):
    reasons = []
    if fvg_data.get("fvg_type") == "BULLISH" and fvg_data.get("rejection_after_touch"):
        reasons.append("bullish FVG rejection_after_touch")
    if price_action_data.get("support_reaction"):
        reasons.append("support reaction on entry TF")
    if price_action_data.get("candle_strength") == "STRONG_BULL":
        reasons.append("strong bull candle on entry TF")
    if price_action_data.get("wick_rejection") == "DOWN":
        reasons.append("wick rejection down (bullish)")
    if price_action_data.get("momentum_shift") and not price_action_data.get(
        "fake_breakout", False
    ):
        cs = price_action_data.get("candle_strength", "WEAK")
        if cs in ("STRONG_BULL", "WEAK"):
            reasons.append("bullish momentum shift")
    return reasons


def _bearish_entry_triggers(price_action_data, fvg_data):
    reasons = []
    if fvg_data.get("fvg_type") == "BEARISH" and fvg_data.get("rejection_after_touch"):
        reasons.append("bearish FVG rejection_after_touch")
    if price_action_data.get("resistance_reaction"):
        reasons.append("resistance reaction on entry TF")
    if price_action_data.get("candle_strength") == "STRONG_BEAR":
        reasons.append("strong bear candle on entry TF")
    if price_action_data.get("wick_rejection") == "UP":
        reasons.append("wick rejection up (bearish)")
    if price_action_data.get("momentum_shift") and not price_action_data.get(
        "fake_breakout", False
    ):
        cs = price_action_data.get("candle_strength", "WEAK")
        if cs in ("STRONG_BEAR", "WEAK"):
            reasons.append("bearish momentum shift")
    return reasons


def _has_liquidity_event(*structure_datas):
    for sd in structure_datas:
        if sd.get("liquidity_event"):
            return True
    return False


def _confirm_not_opposing_trend(trend_bias, confirm_bias):
    if trend_bias == "BULLISH" and confirm_bias == "BEARISH":
        return False
    if trend_bias == "BEARISH" and confirm_bias == "BULLISH":
        return False
    return True


def _grade_setup_quality(
    *,
    trend_strength,
    confirm_strength,
    entry_strength,
    trigger_count,
    setup_type,
    fake_breakout,
    alignment,
):
    score = 0

    for strength in (trend_strength, confirm_strength, entry_strength):
        if strength == "STRONG":
            score += 2
        elif strength == "MEDIUM":
            score += 1

    score += min(trigger_count, 2)

    if setup_type == "TREND_CONTINUATION":
        score += 1
    if alignment in ("FULL_BULLISH", "FULL_BEARISH"):
        score += 1
    if setup_type == "PULLBACK_ENTRY":
        score += 0  # neutral; quality from structure + triggers
    if setup_type == "REVERSAL_ATTEMPT":
        score -= 1

    if fake_breakout:
        score -= 2

    if score >= 5:
        return "HIGH"
    if score >= 2:
        return "MEDIUM"
    return "LOW"


def detect_setup(
    trend_tf_data,
    confirm_tf_data,
    entry_tf_data,
    price_action_data,
    fvg_data,
):
    """
    Classify trade setup from MTF data and entry-level price action / FVG.

    trend_tf_data / confirm_tf_data / entry_tf_data: output of analyze_timeframe().
    """
    reasons = []

    trend_s = trend_tf_data.get("structure_data", {})
    confirm_s = confirm_tf_data.get("structure_data", {})
    entry_s = entry_tf_data.get("structure_data", {})

    if _has_liquidity_event(trend_s, confirm_s, entry_s):
        return {
            "setup_type": "NO_SETUP",
            "setup_direction": "WAIT",
            "setup_quality": "LOW",
            "setup_reasons": ["liquidity event -> NO_SETUP"],
        }

    trend_bias = _tf_bias(trend_tf_data)
    confirm_bias = _tf_bias(confirm_tf_data)
    trend_signal = trend_tf_data.get("signal", "WAIT")
    confirm_signal = confirm_tf_data.get("signal", "WAIT")
    entry_signal = entry_tf_data.get("signal", "WAIT")

    alignment = _signal_alignment(trend_signal, confirm_signal, entry_signal)
    reasons.append(f"signal alignment={alignment}")
    reasons.append(f"trend bias={trend_bias} | confirm bias={confirm_bias}")

    bull_triggers = _bullish_entry_triggers(price_action_data, fvg_data)
    bear_triggers = _bearish_entry_triggers(price_action_data, fvg_data)
    has_bull_trigger = len(bull_triggers) > 0
    has_bear_trigger = len(bear_triggers) > 0
    fake_breakout = bool(price_action_data.get("fake_breakout", False))

    if fake_breakout:
        reasons.append("fake breakout on entry TF (quality penalty)")

    entry_weak = entry_s.get("structure_strength") == "WEAK"
    if entry_weak and not has_bull_trigger and not has_bear_trigger:
        return {
            "setup_type": "NO_SETUP",
            "setup_direction": "WAIT",
            "setup_quality": "LOW",
            "setup_reasons": reasons
            + ["entry structure WEAK and no entry trigger -> NO_SETUP"],
        }

    # TREND_CONTINUATION: 30m + 15m aligned with trend, entry confirms or triggers
    if _is_bullish_tf(trend_tf_data) and _is_bullish_tf(confirm_tf_data):
        if entry_signal == "BUY" or (entry_signal == "WAIT" and has_bull_trigger):
            setup_reasons = list(reasons)
            setup_reasons.append("30m+15m bullish; entry BUY or bullish trigger")
            setup_reasons.extend(bull_triggers)
            quality = _grade_setup_quality(
                trend_strength=trend_s.get("structure_strength", "WEAK"),
                confirm_strength=confirm_s.get("structure_strength", "WEAK"),
                entry_strength=entry_s.get("structure_strength", "WEAK"),
                trigger_count=len(bull_triggers),
                setup_type="TREND_CONTINUATION",
                fake_breakout=fake_breakout,
                alignment=alignment,
            )
            return {
                "setup_type": "TREND_CONTINUATION",
                "setup_direction": "BUY",
                "setup_quality": quality,
                "setup_reasons": setup_reasons,
            }

    if _is_bearish_tf(trend_tf_data) and _is_bearish_tf(confirm_tf_data):
        if entry_signal == "SELL" or (entry_signal == "WAIT" and has_bear_trigger):
            setup_reasons = list(reasons)
            setup_reasons.append("30m+15m bearish; entry SELL or bearish trigger")
            setup_reasons.extend(bear_triggers)
            quality = _grade_setup_quality(
                trend_strength=trend_s.get("structure_strength", "WEAK"),
                confirm_strength=confirm_s.get("structure_strength", "WEAK"),
                entry_strength=entry_s.get("structure_strength", "WEAK"),
                trigger_count=len(bear_triggers),
                setup_type="TREND_CONTINUATION",
                fake_breakout=fake_breakout,
                alignment=alignment,
            )
            return {
                "setup_type": "TREND_CONTINUATION",
                "setup_direction": "SELL",
                "setup_quality": quality,
                "setup_reasons": setup_reasons,
            }

    # --- PULLBACK_ENTRY: MIXED alignment but pullback with trend + entry trigger ---

    if alignment == "MIXED" and trend_bias in ("BULLISH", "BEARISH"):
        if not _confirm_not_opposing_trend(trend_bias, confirm_bias):
            return {
                "setup_type": "NO_SETUP",
                "setup_direction": "WAIT",
                "setup_quality": "LOW",
                "setup_reasons": reasons
                + ["MIXED: 15m opposes 30m trend -> NO_SETUP"],
            }

        if trend_bias == "BULLISH" and has_bull_trigger:
            if entry_signal in ("WAIT", "BUY") and not has_bear_trigger:
                setup_reasons = list(reasons)
                setup_reasons.append(
                    "MIXED pullback: 30m bullish, 15m not opposing, 5m bullish trigger"
                )
                setup_reasons.extend(bull_triggers)
                quality = _grade_setup_quality(
                    trend_strength=trend_s.get("structure_strength", "WEAK"),
                    confirm_strength=confirm_s.get("structure_strength", "WEAK"),
                    entry_strength=entry_s.get("structure_strength", "WEAK"),
                    trigger_count=len(bull_triggers),
                    setup_type="PULLBACK_ENTRY",
                    fake_breakout=fake_breakout,
                    alignment=alignment,
                )
                return {
                    "setup_type": "PULLBACK_ENTRY",
                    "setup_direction": "BUY",
                    "setup_quality": quality,
                    "setup_reasons": setup_reasons,
                }

        if trend_bias == "BEARISH" and has_bear_trigger:
            if entry_signal in ("WAIT", "SELL") and not has_bull_trigger:
                setup_reasons = list(reasons)
                setup_reasons.append(
                    "MIXED pullback: 30m bearish, 15m not opposing, 5m bearish trigger"
                )
                setup_reasons.extend(bear_triggers)
                quality = _grade_setup_quality(
                    trend_strength=trend_s.get("structure_strength", "WEAK"),
                    confirm_strength=confirm_s.get("structure_strength", "WEAK"),
                    entry_strength=entry_s.get("structure_strength", "WEAK"),
                    trigger_count=len(bear_triggers),
                    setup_type="PULLBACK_ENTRY",
                    fake_breakout=fake_breakout,
                    alignment=alignment,
                )
                return {
                    "setup_type": "PULLBACK_ENTRY",
                    "setup_direction": "SELL",
                    "setup_quality": quality,
                    "setup_reasons": setup_reasons,
                }

    # --- REVERSAL_ATTEMPT: elevated reversal chance + entry trigger against weak trend ---

    reversal_chance = entry_s.get("reversal_chance", "LOW")
    if reversal_chance in ("MEDIUM", "HIGH"):
        if (
            trend_bias == "BEARISH"
            and has_bull_trigger
            and not _is_bullish_tf(confirm_tf_data)
        ):
            setup_reasons = list(reasons)
            setup_reasons.append(
                f"reversal attempt: entry reversal_chance={reversal_chance}, bullish triggers vs bearish trend"
            )
            setup_reasons.extend(bull_triggers)
            quality = _grade_setup_quality(
                trend_strength=trend_s.get("structure_strength", "WEAK"),
                confirm_strength=confirm_s.get("structure_strength", "WEAK"),
                entry_strength=entry_s.get("structure_strength", "WEAK"),
                trigger_count=len(bull_triggers),
                setup_type="REVERSAL_ATTEMPT",
                fake_breakout=fake_breakout,
                alignment=alignment,
            )
            if quality == "HIGH":
                quality = "MEDIUM"
            return {
                "setup_type": "REVERSAL_ATTEMPT",
                "setup_direction": "BUY",
                "setup_quality": quality,
                "setup_reasons": setup_reasons,
            }

        if (
            trend_bias == "BULLISH"
            and has_bear_trigger
            and not _is_bearish_tf(confirm_tf_data)
        ):
            setup_reasons = list(reasons)
            setup_reasons.append(
                f"reversal attempt: entry reversal_chance={reversal_chance}, bearish triggers vs bullish trend"
            )
            setup_reasons.extend(bear_triggers)
            quality = _grade_setup_quality(
                trend_strength=trend_s.get("structure_strength", "WEAK"),
                confirm_strength=confirm_s.get("structure_strength", "WEAK"),
                entry_strength=entry_s.get("structure_strength", "WEAK"),
                trigger_count=len(bear_triggers),
                setup_type="REVERSAL_ATTEMPT",
                fake_breakout=fake_breakout,
                alignment=alignment,
            )
            if quality == "HIGH":
                quality = "MEDIUM"
            return {
                "setup_type": "REVERSAL_ATTEMPT",
                "setup_direction": "SELL",
                "setup_quality": quality,
                "setup_reasons": setup_reasons,
            }

    # Full signal alignment with entry trigger only (edge: entry WAIT but triggers)
    if alignment == "FULL_BULLISH" and entry_signal == "WAIT" and has_bull_trigger:
        setup_reasons = list(reasons) + ["FULL_BULLISH signals; entry WAIT + bullish trigger"]
        setup_reasons.extend(bull_triggers)
        quality = _grade_setup_quality(
            trend_strength=trend_s.get("structure_strength", "WEAK"),
            confirm_strength=confirm_s.get("structure_strength", "WEAK"),
            entry_strength=entry_s.get("structure_strength", "WEAK"),
            trigger_count=len(bull_triggers),
            setup_type="TREND_CONTINUATION",
            fake_breakout=fake_breakout,
            alignment=alignment,
        )
        return {
            "setup_type": "TREND_CONTINUATION",
            "setup_direction": "BUY",
            "setup_quality": quality,
            "setup_reasons": setup_reasons,
        }

    if alignment == "FULL_BEARISH" and entry_signal == "WAIT" and has_bear_trigger:
        setup_reasons = list(reasons) + ["FULL_BEARISH signals; entry WAIT + bearish trigger"]
        setup_reasons.extend(bear_triggers)
        quality = _grade_setup_quality(
            trend_strength=trend_s.get("structure_strength", "WEAK"),
            confirm_strength=confirm_s.get("structure_strength", "WEAK"),
            entry_strength=entry_s.get("structure_strength", "WEAK"),
            trigger_count=len(bear_triggers),
            setup_type="TREND_CONTINUATION",
            fake_breakout=fake_breakout,
            alignment=alignment,
        )
        return {
            "setup_type": "TREND_CONTINUATION",
            "setup_direction": "SELL",
            "setup_quality": quality,
            "setup_reasons": setup_reasons,
        }

    return {
        "setup_type": "NO_SETUP",
        "setup_direction": "WAIT",
        "setup_quality": "LOW",
        "setup_reasons": reasons
        + ["no qualifying bias/context/trigger combination"],
    }


def resolve_paper_from_setup(
    *,
    signal,
    trade_allowed,
    entry_quality,
    signal_confidence,
    setup,
    liquidity_event,
):
    """
    When legacy signal is WAIT, allow paper layer to use setup_engine suggestion.
    Does not change the displayed SIGNAL (MTF filter preserved).
    """
    paper_signal = signal
    paper_trade_allowed = trade_allowed
    paper_entry_quality = entry_quality
    paper_confidence = signal_confidence
    paper_source = "signal"

    setup_type = setup.get("setup_type", "NO_SETUP")
    setup_direction = setup.get("setup_direction", "WAIT")
    setup_quality = setup.get("setup_quality", "LOW")

    if liquidity_event or setup_type == "NO_SETUP":
        return {
            "paper_signal": paper_signal,
            "paper_trade_allowed": paper_trade_allowed,
            "paper_entry_quality": paper_entry_quality,
            "paper_confidence": paper_confidence,
            "paper_source": paper_source,
        }

    if (
        signal == "WAIT"
        and setup_quality in ("MEDIUM", "HIGH")
        and setup_direction in ("BUY", "SELL")
    ):
        paper_signal = setup_direction
        paper_source = f"setup_engine:{setup_type}"
        paper_entry_quality = setup_quality
        if setup_quality == "HIGH":
            paper_confidence = max(signal_confidence, 4)
        else:
            paper_confidence = max(signal_confidence, 3)
        if not liquidity_event:
            paper_trade_allowed = True

    return {
        "paper_signal": paper_signal,
        "paper_trade_allowed": paper_trade_allowed,
        "paper_entry_quality": paper_entry_quality,
        "paper_confidence": paper_confidence,
        "paper_source": paper_source,
    }
