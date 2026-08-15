"""
MTF setup classifier: bias (30m) + context (15m) + entry trigger (5m).

Sits above the legacy alignment filter; does not replace scoring/signals.
"""

from typing import Any, Dict, Optional

from structure_confluence import apply_structure_confluence


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


def _macro_bias(tf_data):
    """
    Bias oparty na strukturze i wskaźnikach kierunkowych.

    To jest bliższe logice z Twojego bota testowego: najpierw kontekst wyższego TF,
    potem dopiero wejście z niższego TF.
    """
    structure_data = tf_data.get("structure_data", {})
    indicator_status = tf_data.get("indicator_status", {})
    structure_bias = _structure_bias(structure_data)

    bullish_votes = 0
    bearish_votes = 0
    for key in ("MA60", "EMA238", "RSI"):
        value = indicator_status.get(key, "WAIT")
        if value in ("BUY", "BULLISH"):
            bullish_votes += 1
        elif value in ("SELL", "BEARISH"):
            bearish_votes += 1

    if structure_bias == "BULLISH" and bullish_votes >= 2:
        return "BULLISH"
    if structure_bias == "BEARISH" and bearish_votes >= 2:
        return "BEARISH"
    if bullish_votes >= 2 and bullish_votes > bearish_votes:
        return "BULLISH"
    if bearish_votes >= 2 and bearish_votes > bullish_votes:
        return "BEARISH"
    if structure_bias != "NEUTRAL":
        return structure_bias
    return _tf_bias(tf_data)


def _rsi_allows_direction(tf_data, direction):
    rsi_signal = tf_data.get("indicator_status", {}).get("RSI", "WAIT")
    if direction == "BUY":
        return rsi_signal in ("BUY", "WAIT")
    if direction == "SELL":
        return rsi_signal in ("SELL", "WAIT")
    return True


def _msb_context_ok(structure_data):
    """
    Prosty proxy na MSB: struktura nie może być SIDEWAYS, a kontekst musi mieć
    przynajmniej średnią siłę albo momentum.
    """
    structure = structure_data.get("structure", "SIDEWAYS")
    strength = structure_data.get("structure_strength", "WEAK")
    momentum = structure_data.get("momentum", "WEAK")
    if structure == "SIDEWAYS":
        return False
    return strength in ("MEDIUM", "STRONG") or momentum == "STRONG"


def _fibo_context(tf_data):
    fibo = tf_data.get("indicator_status", {}).get("FIBO", {})
    if not isinstance(fibo, dict):
        return {}
    return fibo


def _fibo_supports_direction(tf_data, direction):
    fibo = _fibo_context(tf_data)
    if not fibo:
        return True

    fibo_signal = fibo.get("fibo_signal", "WAIT")
    fibo_direction = fibo.get("fibo_direction", "NEUTRAL")
    fibo_zone = fibo.get("fibo_zone", "NONE")

    if fibo_direction == "NEUTRAL" or fibo_zone == "NONE":
        return True

    if fibo_signal == direction:
        return True

    if direction == "BUY" and fibo_direction == "BULLISH":
        return fibo_zone in ("ENTRY_ZONE", "WATCH_ZONE")
    if direction == "SELL" and fibo_direction == "BEARISH":
        return fibo_zone in ("ENTRY_ZONE", "WATCH_ZONE")

    return False


def _fibo_context_label(tf_data):
    fibo = _fibo_context(tf_data)
    if not fibo:
        return "FIBO=NA"
    return (
        f"FIBO={fibo.get('fibo_signal', 'WAIT')}"
        f"|dir={fibo.get('fibo_direction', 'NEUTRAL')}"
        f"|zone={fibo.get('fibo_zone', 'NONE')}"
        f"|retr={fibo.get('retracement', 0.0)}"
    )


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


def _apply_sideways_continuation_penalty(
    setup: Dict[str, Any], entry_structure_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Soft filter: weak continuation in sideways entry structure.
    Only TREND_CONTINUATION; does not affect PULLBACK_ENTRY or REVERSAL_ATTEMPT.
    """
    if setup.get("setup_type") != "TREND_CONTINUATION":
        return setup

    structure = entry_structure_data.get("structure", "SIDEWAYS")
    strength = entry_structure_data.get("structure_strength", "WEAK")
    if structure != "SIDEWAYS" or strength != "WEAK":
        return setup

    adjusted = dict(setup)
    reasons = list(adjusted.get("setup_reasons", []))
    if "sideways continuation penalty" not in reasons:
        reasons.append("sideways continuation penalty")
    adjusted["setup_reasons"] = reasons

    quality = adjusted.get("setup_quality", "LOW")
    if quality == "HIGH":
        adjusted["setup_quality"] = "MEDIUM"
    adjusted["setup_confidence_penalty"] = int(adjusted.get("setup_confidence_penalty", 0)) + 1

    return adjusted


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
    structure_events: Optional[Dict[str, Any]] = None,
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

    trend_bias = _macro_bias(trend_tf_data)
    confirm_bias = _macro_bias(confirm_tf_data)
    trend_signal = trend_tf_data.get("signal", "WAIT")
    confirm_signal = confirm_tf_data.get("signal", "WAIT")
    entry_signal = entry_tf_data.get("signal", "WAIT")
    entry_rsi_signal = entry_tf_data.get("indicator_status", {}).get("RSI", "WAIT")
    entry_fibo_label = _fibo_context_label(entry_tf_data)
    trend_msb_ok = _msb_context_ok(trend_s)
    confirm_msb_ok = _msb_context_ok(confirm_s)
    entry_msb_ok = _msb_context_ok(entry_s)

    alignment = _signal_alignment(trend_signal, confirm_signal, entry_signal)
    reasons.append(f"signal alignment={alignment}")
    reasons.append(f"trend bias={trend_bias} | confirm bias={confirm_bias}")
    reasons.append(f"entry RSI={entry_rsi_signal}")
    reasons.append(f"entry {entry_fibo_label}")
    reasons.append(
        f"MSB_CONTEXT trend={trend_msb_ok} confirm={confirm_msb_ok} entry={entry_msb_ok}"
    )

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

    # TREND_CONTINUATION: FULL MTF signal alignment only; MIXED -> PULLBACK below.
    if trend_bias == "BULLISH" and confirm_bias != "BEARISH" and trend_msb_ok and confirm_msb_ok and alignment in ("FULL_BULLISH", "FULL_BEARISH"):
        if (
            (entry_signal == "BUY" or (entry_signal == "WAIT" and has_bull_trigger))
            and _rsi_allows_direction(entry_tf_data, "BUY")
            and _fibo_supports_direction(entry_tf_data, "BUY")
        ):
            setup_reasons = list(reasons)
            setup_reasons.append("bullish bias + MSB context; entry BUY or bullish trigger")
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
            return apply_structure_confluence(
                _apply_sideways_continuation_penalty(
                    {
                        "setup_type": "TREND_CONTINUATION",
                        "setup_direction": "BUY",
                        "setup_quality": quality,
                        "setup_reasons": setup_reasons,
                    },
                    entry_s,
                ),
                structure_events,
            )

    if trend_bias == "BEARISH" and confirm_bias != "BULLISH" and trend_msb_ok and confirm_msb_ok and alignment in ("FULL_BULLISH", "FULL_BEARISH"):
        if (
            (entry_signal == "SELL" or (entry_signal == "WAIT" and has_bear_trigger))
            and _rsi_allows_direction(entry_tf_data, "SELL")
            and _fibo_supports_direction(entry_tf_data, "SELL")
        ):
            setup_reasons = list(reasons)
            setup_reasons.append("bearish bias + MSB context; entry SELL or bearish trigger")
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
            return apply_structure_confluence(
                _apply_sideways_continuation_penalty(
                    {
                        "setup_type": "TREND_CONTINUATION",
                        "setup_direction": "SELL",
                        "setup_quality": quality,
                        "setup_reasons": setup_reasons,
                    },
                    entry_s,
                ),
                structure_events,
            )

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
            if (
                entry_signal in ("WAIT", "BUY")
                and not has_bear_trigger
                and _rsi_allows_direction(entry_tf_data, "BUY")
                and _fibo_supports_direction(entry_tf_data, "BUY")
                and trend_msb_ok
            ):
                setup_reasons = list(reasons)
                setup_reasons.append(
                    "MIXED pullback: bullish bias, MSB context, confirm not opposing, bullish trigger"
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
                return apply_structure_confluence(
                    {
                        "setup_type": "PULLBACK_ENTRY",
                        "setup_direction": "BUY",
                        "setup_quality": quality,
                        "setup_reasons": setup_reasons,
                    },
                    structure_events,
                )

        bullish_fvg_pb_short = (
            fvg_data.get("fvg_type") == "BULLISH"
            and fvg_data.get("rejection_after_touch")
        )
        bearish_pb_short_trigger = has_bear_trigger or (
            confirm_bias == "BEARISH" and bullish_fvg_pb_short
        )
        bull_trigger_blocks_pb_short = has_bull_trigger and not (
            confirm_bias == "BEARISH" and bullish_fvg_pb_short
        )

        if trend_bias == "BEARISH" and bearish_pb_short_trigger:
            if (
                entry_signal in ("WAIT", "SELL")
                and not bull_trigger_blocks_pb_short
                and _rsi_allows_direction(entry_tf_data, "SELL")
                and _fibo_supports_direction(entry_tf_data, "SELL")
                and trend_msb_ok
            ):
                setup_reasons = list(reasons)
                setup_reasons.append(
                    "MIXED pullback: bearish bias, MSB context, confirm not opposing, bearish or bullish-FVG pullback trigger"
                )
                pb_short_triggers = list(bear_triggers)
                if bullish_fvg_pb_short and confirm_bias == "BEARISH":
                    pb_short_triggers.append(
                        "bullish FVG rejection_after_touch (pullback short)"
                    )
                setup_reasons.extend(pb_short_triggers)
                quality = _grade_setup_quality(
                    trend_strength=trend_s.get("structure_strength", "WEAK"),
                    confirm_strength=confirm_s.get("structure_strength", "WEAK"),
                    entry_strength=entry_s.get("structure_strength", "WEAK"),
                    trigger_count=len(pb_short_triggers),
                    setup_type="PULLBACK_ENTRY",
                    fake_breakout=fake_breakout,
                    alignment=alignment,
                )
                return apply_structure_confluence(
                    {
                        "setup_type": "PULLBACK_ENTRY",
                        "setup_direction": "SELL",
                        "setup_quality": quality,
                        "setup_reasons": setup_reasons,
                    },
                    structure_events,
                )

    # --- REVERSAL_ATTEMPT: elevated reversal chance + entry trigger against weak trend ---

    reversal_chance = entry_s.get("reversal_chance", "LOW")
    if reversal_chance in ("MEDIUM", "HIGH"):
        if (
            trend_bias == "BEARISH"
            and has_bull_trigger
            and not _is_bullish_tf(confirm_tf_data)
            and _rsi_allows_direction(entry_tf_data, "BUY")
            and _fibo_supports_direction(entry_tf_data, "BUY")
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
            return apply_structure_confluence(
                {
                    "setup_type": "REVERSAL_ATTEMPT",
                    "setup_direction": "BUY",
                    "setup_quality": quality,
                    "setup_reasons": setup_reasons,
                },
                structure_events,
            )

        if (
            trend_bias == "BULLISH"
            and has_bear_trigger
            and not _is_bearish_tf(confirm_tf_data)
            and _rsi_allows_direction(entry_tf_data, "SELL")
            and _fibo_supports_direction(entry_tf_data, "SELL")
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
            return apply_structure_confluence(
                {
                    "setup_type": "REVERSAL_ATTEMPT",
                    "setup_direction": "SELL",
                    "setup_quality": quality,
                    "setup_reasons": setup_reasons,
                },
                structure_events,
            )

    # Full signal alignment with entry trigger only (edge: entry WAIT but triggers)
    if (
        alignment == "FULL_BULLISH"
        and entry_signal == "WAIT"
        and has_bull_trigger
        and _rsi_allows_direction(entry_tf_data, "BUY")
        and _fibo_supports_direction(entry_tf_data, "BUY")
    ):
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
        return apply_structure_confluence(
            _apply_sideways_continuation_penalty(
                {
                    "setup_type": "TREND_CONTINUATION",
                    "setup_direction": "BUY",
                    "setup_quality": quality,
                    "setup_reasons": setup_reasons,
                },
                entry_s,
            ),
            structure_events,
        )

    if (
        alignment == "FULL_BEARISH"
        and entry_signal == "WAIT"
        and has_bear_trigger
        and _rsi_allows_direction(entry_tf_data, "SELL")
        and _fibo_supports_direction(entry_tf_data, "SELL")
    ):
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
        return apply_structure_confluence(
            _apply_sideways_continuation_penalty(
                {
                    "setup_type": "TREND_CONTINUATION",
                    "setup_direction": "SELL",
                    "setup_quality": quality,
                    "setup_reasons": setup_reasons,
                },
                entry_s,
            ),
            structure_events,
        )

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
    Resolve paper-layer decision fields separately from the displayed MTF SIGNAL.

    Dual path (observability — both sides should be logged in setup snapshots):
    - signal path: signal / signal_confidence / entry_quality / trade_allowed
    - paper path: paper_signal / paper_confidence / paper_entry_quality /
      paper_trade_allowed / paper_source

    When setup_type is NO_SETUP (or liquidity_event), paper_* passthrough equals
    the signal path and paper_source="signal". Paper open is still allowed if
    signal-path gates pass — NO_SETUP does not by itself block opens.

    When SIGNAL==WAIT and setup quality is MEDIUM/HIGH with BUY/SELL direction,
    paper may override: paper_signal=setup_direction, paper_entry_quality=
    setup_quality, paper_confidence boosted to at least 3 (MEDIUM) or 4 (HIGH),
    paper_source="setup_engine:{setup_type}".

    TREND_CONTINUATION respects trade_allowed (e.g. MIXED alignment blocks paper).
    Other setup types keep prior override behavior when setup quality passes.

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
        confidence_penalty = int(setup.get("setup_confidence_penalty", 0))
        if setup_quality == "HIGH":
            paper_confidence = max(signal_confidence, 4) - confidence_penalty
        else:
            paper_confidence = max(signal_confidence, 3) - confidence_penalty
        paper_confidence = max(0, min(5, paper_confidence))
        if not liquidity_event:
            if setup_type == "TREND_CONTINUATION":
                paper_trade_allowed = bool(trade_allowed)
            else:
                paper_trade_allowed = True

    return {
        "paper_signal": paper_signal,
        "paper_trade_allowed": paper_trade_allowed,
        "paper_entry_quality": paper_entry_quality,
        "paper_confidence": paper_confidence,
        "paper_source": paper_source,
    }
