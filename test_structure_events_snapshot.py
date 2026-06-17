#!/usr/bin/env python3
"""
Verify structure_events observer fields are written to setup_history.jsonl.

Does not touch SIGNAL, paper_trader, scoring, or setup_engine.
"""

import json
import os
import shutil
import tempfile

from setup_stats import (
    STRUCTURE_EVENT_FLAT_KEYS,
    load_setup_history,
    save_setup_snapshot,
    structure_event_snapshot_fields,
)
from structure_events import analyze_structure_events


def _sample_events():
    return {
        "bos": "BOS_BULLISH",
        "choch": "NONE",
        "last_swing_high": 101.5,
        "last_swing_low": 98.2,
        "broken_level": 101.5,
        "buyers_take_control": True,
        "sellers_take_control": False,
        "control_shift": "BUYERS",
        "event_strength": "HIGH",
        "event_reasons": ["test reason"],
    }


def test_snapshot_fields_mapping():
    fields = structure_event_snapshot_fields(_sample_events())
    assert fields["structure_event_bos"] == "BOS_BULLISH"
    assert fields["structure_event_choch"] == "NONE"
    assert fields["control_shift"] == "BUYERS"
    assert fields["buyers_take_control"] is True
    assert fields["sellers_take_control"] is False
    assert fields["structure_event_strength"] == "HIGH"
    assert fields["structure_event_reasons"] == ["test reason"]
    assert fields["structure_events"]["last_swing_high"] == 101.5
    assert fields["structure_events"]["broken_level"] == 101.5
    for key in STRUCTURE_EVENT_FLAT_KEYS:
        assert key in fields


def test_jsonl_write():
    td = tempfile.mkdtemp()
    try:
        events = _sample_events()
        save_setup_snapshot(
            td,
            timestamp="2026-05-17T12:00:00",
            symbol="BTC/USDT",
            price=100000.0,
            signal="WAIT",
            paper_signal="WAIT",
            paper_trade_allowed=False,
            setup_type="NO_SETUP",
            setup_direction="WAIT",
            setup_quality="LOW",
            signal_confidence=0,
            entry_quality="LOW",
            tf_alignment="MIXED",
            alignment_strength="WEAK",
            market_structure="SIDEWAYS",
            structure_strength="WEAK",
            momentum="WEAK",
            risk_level="MEDIUM",
            recommended_leverage=0,
            target_profit_percent=0.0,
            fvg_type="NONE",
            fvg_touched=False,
            rejection_after_touch=False,
            candle_strength="WEAK",
            wick_rejection="NONE",
            fake_breakout=False,
            support_reaction=False,
            resistance_reaction=False,
            momentum_shift=False,
            setup_reasons=[],
            confidence_reasons=[],
            structure_events=events,
        )
        rows = load_setup_history(td)
        assert len(rows) == 1
        row = rows[0]
        for key in STRUCTURE_EVENT_FLAT_KEYS:
            assert key in row, f"missing flat key: {key}"
        assert row["structure_event_bos"] == "BOS_BULLISH"
        assert row["structure_events"]["control_shift"] == "BUYERS"
    finally:
        shutil.rmtree(td)


def test_analyze_and_snapshot_roundtrip():
    candles = []
    for i in range(20):
        o = 100.0 + i * 0.3
        c = o + 0.2
        candles.append([0, o, c + 0.15, o - 0.1, c, 0])
    candles.append([0, 105.0, 106.5, 104.8, 106.2, 0])

    events = analyze_structure_events(candles)
    fields = structure_event_snapshot_fields(events)
    assert fields["structure_event_bos"] in (
        "NONE",
        "BOS_BULLISH",
        "BOS_BEARISH",
        "CHOCH_BULLISH",
        "CHOCH_BEARISH",
    )
    assert isinstance(fields["structure_event_reasons"], list)
    for key in (
        "wick_only_break",
        "wick_break_side",
        "sweep_type",
        "break_validity",
        "fake_breakout",
        "structure_character",
        "choch_state",
        "last_hl",
        "last_lh",
        "structure_phase",
        "choch_is_first_in_leg",
    ):
        assert key in events, f"missing key in analyze output: {key}"


def _candle(o, h, l, c):
    return [0, o, h, l, c, 0]


def _build_structure_series(extra_tail=None):
    """
    Deterministic OHLCV with >=2 valid swing highs/lows (lookback=3, reaction filter).

    Swing high at index 14 (102.5); tail candles start at index 18+ so the wick
    test bar does not sit inside that swing's lookback window.
    """
    pattern = [
        (100.0, 100.4, 99.6, 100.2),
        (100.2, 100.5, 99.8, 100.3),
        (100.3, 100.6, 99.9, 100.1),
        (100.1, 100.3, 99.0, 99.2),
        (99.2, 99.5, 98.8, 99.0),
        (99.0, 99.3, 98.5, 98.7),
        (98.7, 101.5, 98.6, 101.0),   # swing high ~6
        (101.0, 101.2, 99.5, 99.8),
        (99.8, 100.0, 99.0, 99.2),
        (99.2, 99.5, 98.8, 99.0),
        (99.0, 99.2, 97.8, 98.0),     # swing low ~10
        (98.0, 98.5, 97.5, 98.3),
        (98.3, 98.8, 98.0, 98.6),
        (98.6, 100.0, 98.4, 99.8),
        (99.8, 102.5, 99.5, 102.0),   # swing high ~14 (reference level)
        (102.0, 102.1, 100.5, 100.8), # reaction
        (100.8, 101.0, 100.2, 100.4),
        (100.4, 100.6, 100.0, 100.2), # buffer before tail (index 17)
    ]
    candles = [_candle(*row) for row in pattern]
    if extra_tail:
        candles.extend(extra_tail)
    return candles


def test_wick_only_sweep_not_bos():
    """High wicks above level but close stays below -> sweep, not BOS."""
    swing_high = 102.5
    candles = _build_structure_series(
        extra_tail=[_candle(100.5, swing_high + 0.4, 100.2, swing_high - 0.2)]
    )

    events = analyze_structure_events(candles)
    assert events["wick_only_break"] is True
    assert events["bos"] == "NONE"
    assert events["sweep_type"] == "SWEEP_HIGH"
    assert events["break_validity"] == "WICK_ONLY"


def test_fake_reclaim_blocks_bos():
    """Prev close breaks level; current close reclaims -> fake, not BOS."""
    swing_high = 102.5
    candles = _build_structure_series(
        extra_tail=[
            _candle(102.0, swing_high + 0.2, 101.8, swing_high + 0.05),  # prev close break
            _candle(swing_high + 0.02, swing_high - 0.05, 101.5, swing_high - 0.1),  # reclaim
        ]
    )

    events = analyze_structure_events(candles)
    assert events["fake_breakout"] is True
    assert events["break_validity"] == "FAKE_RECLAIM"
    assert events["bos"] == "NONE"


def main():
    test_snapshot_fields_mapping()
    test_jsonl_write()
    test_analyze_and_snapshot_roundtrip()
    test_wick_only_sweep_not_bos()
    test_fake_reclaim_blocks_bos()
    print("All structure_events snapshot tests passed.")


if __name__ == "__main__":
    main()
