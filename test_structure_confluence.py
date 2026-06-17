#!/usr/bin/env python3
"""Tests for structure_confluence filter (ETAP 2)."""

from structure_confluence import apply_structure_confluence


def _setup(setup_type, direction, quality="MEDIUM", reasons=None):
    return {
        "setup_type": setup_type,
        "setup_direction": direction,
        "setup_quality": quality,
        "setup_reasons": list(reasons or ["base reason"]),
    }


def _events(**kwargs):
    base = {
        "bos": "NONE",
        "choch": "NONE",
        "break_validity": "NONE",
        "wick_only_break": False,
        "wick_break_side": "NONE",
        "sweep_type": "NONE",
        "fake_breakout": False,
        "structure_phase": "CONTINUATION",
        "choch_state": "NONE",
        "event_reasons": [],
    }
    base.update(kwargs)
    return base


def test_none_events_fail_open():
    setup = _setup("TREND_CONTINUATION", "BUY", "HIGH")
    result = apply_structure_confluence(setup, None)
    assert result["setup_type"] == "TREND_CONTINUATION"
    assert result["setup_direction"] == "BUY"


def test_bos_bullish_supports_long_tc():
    setup = _setup("TREND_CONTINUATION", "BUY", "MEDIUM")
    events = _events(bos="BOS_BULLISH", break_validity="BOS")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "TREND_CONTINUATION"
    assert result["setup_quality"] == "HIGH"
    assert "structure BOS_BULLISH supports long" in result["setup_reasons"]


def test_bos_bearish_opposes_long_tc():
    setup = _setup("TREND_CONTINUATION", "BUY", "HIGH")
    events = _events(bos="BOS_BEARISH", break_validity="BOS")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "NO_SETUP"
    assert "structure BOS_BEARISH opposes long TC" in result["setup_reasons"]


def test_bos_bullish_opposes_short_tc():
    setup = _setup("TREND_CONTINUATION", "SELL", "HIGH")
    events = _events(bos="BOS_BULLISH", break_validity="BOS")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "NO_SETUP"
    assert "structure BOS_BULLISH opposes short TC" in result["setup_reasons"]


def test_choch_bearish_blocks_long():
    setup = _setup("TREND_CONTINUATION", "BUY", "HIGH")
    events = _events(choch="CHOCH_BEARISH", break_validity="CHOCH")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "NO_SETUP"
    assert "CHOCH_BEARISH blocks long" in result["setup_reasons"]


def test_choch_bullish_blocks_short():
    setup = _setup("PULLBACK_ENTRY", "SELL", "HIGH")
    events = _events(choch="CHOCH_BULLISH", break_validity="CHOCH")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "NO_SETUP"
    assert "CHOCH_BULLISH blocks short" in result["setup_reasons"]


def test_sweep_high_hard_blocks_tc_long():
    setup = _setup("TREND_CONTINUATION", "BUY", "HIGH")
    events = _events(
        wick_only_break=True,
        wick_break_side="HIGH",
        sweep_type="SWEEP_HIGH",
        break_validity="WICK_ONLY",
    )
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "NO_SETUP"
    assert "sweep detected: no BOS confirmation" in result["setup_reasons"]
    assert "SWEEP_HIGH blocks long" in result["setup_reasons"]


def test_sweep_high_soft_penalty_pb_long():
    setup = _setup("PULLBACK_ENTRY", "BUY", "HIGH")
    events = _events(
        wick_only_break=True,
        wick_break_side="HIGH",
        sweep_type="SWEEP_HIGH",
        break_validity="WICK_ONLY",
    )
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "PULLBACK_ENTRY"
    assert result["setup_direction"] == "BUY"
    assert result["setup_quality"] == "MEDIUM"
    assert result["setup_confidence_penalty"] == 1
    assert "SWEEP_HIGH penalizes long pullback" in result["setup_reasons"]


def test_sweep_low_hard_blocks_tc_short():
    setup = _setup("TREND_CONTINUATION", "SELL", "HIGH")
    events = _events(
        wick_only_break=True,
        wick_break_side="LOW",
        sweep_type="SWEEP_LOW",
        break_validity="WICK_ONLY",
    )
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "NO_SETUP"
    assert "SWEEP_LOW blocks short" in result["setup_reasons"]


def test_fake_reclaim_blocks_tc():
    setup = _setup("TREND_CONTINUATION", "BUY", "HIGH")
    events = _events(fake_breakout=True, break_validity="FAKE_RECLAIM")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "NO_SETUP"
    assert "fake reclaim: no BOS confirmation" in result["setup_reasons"]


def test_fake_reclaim_penalty_pb():
    setup = _setup("PULLBACK_ENTRY", "SELL", "HIGH")
    events = _events(fake_breakout=True, break_validity="FAKE_RECLAIM")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "PULLBACK_ENTRY"
    assert result["setup_quality"] == "MEDIUM"
    assert "fake reclaim: no BOS confirmation" in result["setup_reasons"]


def test_reversal_supported_by_choch():
    setup = _setup("REVERSAL_ATTEMPT", "BUY", "MEDIUM")
    events = _events(choch="CHOCH_BULLISH", break_validity="CHOCH")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "REVERSAL_ATTEMPT"
    assert "CHOCH_BULLISH supports reversal long" in result["setup_reasons"]


def test_bos_ignored_when_not_valid_break():
    setup = _setup("TREND_CONTINUATION", "BUY", "MEDIUM")
    events = _events(bos="BOS_BULLISH", break_validity="NONE")
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "TREND_CONTINUATION"
    assert result["setup_quality"] == "MEDIUM"
    assert "structure BOS_BULLISH supports long" not in result["setup_reasons"]


def test_unavailable_events_skip_filter():
    setup = _setup("TREND_CONTINUATION", "BUY", "HIGH")
    events = _events(event_reasons=["insufficient candles for structure events"])
    result = apply_structure_confluence(setup, events)
    assert result["setup_type"] == "TREND_CONTINUATION"
    assert "structure events unavailable (observer skip)" in result["setup_reasons"]


def main():
    test_none_events_fail_open()
    test_bos_bullish_supports_long_tc()
    test_bos_bearish_opposes_long_tc()
    test_bos_bullish_opposes_short_tc()
    test_choch_bearish_blocks_long()
    test_choch_bullish_blocks_short()
    test_sweep_high_hard_blocks_tc_long()
    test_sweep_high_soft_penalty_pb_long()
    test_sweep_low_hard_blocks_tc_short()
    test_fake_reclaim_blocks_tc()
    test_fake_reclaim_penalty_pb()
    test_reversal_supported_by_choch()
    test_bos_ignored_when_not_valid_break()
    test_unavailable_events_skip_filter()
    print("All structure_confluence tests passed.")


if __name__ == "__main__":
    main()
