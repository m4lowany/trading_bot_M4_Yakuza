#!/usr/bin/env python3
"""
Regression tests for paper dual-path observability.

Observability only — does not change scoring, setup conditions, gates, or exits.
"""

import shutil
import tempfile

from setup_engine import resolve_paper_from_setup
from setup_stats import (
    _enrich_trade,
    load_setup_history,
    save_setup_snapshot,
)


def _base_snapshot_kwargs(**overrides):
    kwargs = dict(
        timestamp="2026-08-15T12:00:00",
        symbol="BTC/USDT",
        price=65000.0,
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
    )
    kwargs.update(overrides)
    return kwargs


def test_resolve_paper_no_setup_passthrough():
    """NO_SETUP keeps paper_* equal to signal path; paper_source=signal."""
    setup = {
        "setup_type": "NO_SETUP",
        "setup_direction": "WAIT",
        "setup_quality": "LOW",
        "setup_reasons": [],
    }
    ctx = resolve_paper_from_setup(
        signal="BUY",
        trade_allowed=True,
        entry_quality="MEDIUM",
        signal_confidence=4,
        setup=setup,
        liquidity_event=False,
    )
    assert ctx["paper_source"] == "signal"
    assert ctx["paper_signal"] == "BUY"
    assert ctx["paper_trade_allowed"] is True
    assert ctx["paper_entry_quality"] == "MEDIUM"
    assert ctx["paper_confidence"] == 4


def test_resolve_paper_wait_setup_boost_zero_to_three():
    """WAIT + MEDIUM setup boosts paper confidence 0 → 3 and copies setup quality."""
    setup = {
        "setup_type": "PULLBACK_ENTRY",
        "setup_direction": "SELL",
        "setup_quality": "MEDIUM",
        "setup_reasons": ["test"],
    }
    ctx = resolve_paper_from_setup(
        signal="WAIT",
        trade_allowed=False,
        entry_quality="LOW",
        signal_confidence=0,
        setup=setup,
        liquidity_event=False,
    )
    assert ctx["paper_source"] == "setup_engine:PULLBACK_ENTRY"
    assert ctx["paper_signal"] == "SELL"
    assert ctx["paper_trade_allowed"] is True
    assert ctx["paper_entry_quality"] == "MEDIUM"
    assert ctx["paper_confidence"] == 3


def test_snapshot_persists_paper_fields():
    """setup_history.jsonl stores both signal_* and paper_* when they diverge."""
    td = tempfile.mkdtemp()
    try:
        save_setup_snapshot(
            td,
            **_base_snapshot_kwargs(
                signal="WAIT",
                signal_confidence=0,
                entry_quality="LOW",
                paper_signal="SELL",
                paper_trade_allowed=True,
                paper_confidence=3,
                paper_entry_quality="MEDIUM",
                paper_source="setup_engine:PULLBACK_ENTRY",
                setup_type="PULLBACK_ENTRY",
                setup_direction="SELL",
                setup_quality="MEDIUM",
            ),
        )
        rows = load_setup_history(td)
        assert len(rows) == 1
        row = rows[0]
        assert row["signal_confidence"] == 0
        assert row["entry_quality"] == "LOW"
        assert row["paper_confidence"] == 3
        assert row["paper_entry_quality"] == "MEDIUM"
        assert row["paper_source"] == "setup_engine:PULLBACK_ENTRY"
        assert row["paper_signal"] == "SELL"
        assert row["paper_trade_allowed"] is True
    finally:
        shutil.rmtree(td)


def test_enrich_trade_does_not_clobber_trade_confidence():
    """Enrichment attaches paper_* / snapshot signal_* but keeps trade.confidence."""
    trade = {
        "side": "SELL",
        "status": "CLOSED",
        "timestamp": "2026-08-15T12:00:00",
        "confidence": 3,
        "entry_quality": "MEDIUM",
        "pnl_percent": 0.01,
        "reason": "normal conditions | setup_engine:PULLBACK_ENTRY",
    }
    snap = {
        "timestamp": "2026-08-15T12:00:00",
        "paper_signal": "SELL",
        "setup_type": "PULLBACK_ENTRY",
        "setup_quality": "MEDIUM",
        "tf_alignment": "MIXED",
        "signal_confidence": 0,
        "entry_quality": "LOW",
        "paper_confidence": 3,
        "paper_entry_quality": "MEDIUM",
        "paper_source": "setup_engine:PULLBACK_ENTRY",
        "structure_event_bos": "NONE",
        "structure_event_choch": "NONE",
        "control_shift": "NONE",
        "buyers_take_control": False,
        "sellers_take_control": False,
        "structure_event_strength": "LOW",
    }
    enriched = _enrich_trade(trade, [snap])
    assert enriched["confidence"] == 3
    assert enriched["entry_quality"] == "MEDIUM"
    assert enriched["paper_confidence"] == 3
    assert enriched["paper_entry_quality"] == "MEDIUM"
    assert enriched["paper_source"] == "setup_engine:PULLBACK_ENTRY"
    assert enriched["snapshot_signal_confidence"] == 0
    assert enriched["snapshot_entry_quality"] == "LOW"
    assert enriched["setup_type"] == "PULLBACK_ENTRY"


def test_enrich_trade_legacy_snapshot_without_paper_fields():
    """Old snapshots lacking paper_* leave trade.confidence intact."""
    trade = {
        "side": "SELL",
        "status": "CLOSED",
        "timestamp": "2026-06-24T08:00:00",
        "confidence": 3,
        "entry_quality": "MEDIUM",
        "pnl_percent": -0.01,
        "reason": "normal conditions | setup_engine:PULLBACK_ENTRY",
    }
    snap = {
        "timestamp": "2026-06-24T08:00:00",
        "paper_signal": "SELL",
        "setup_type": "PULLBACK_ENTRY",
        "setup_quality": "MEDIUM",
        "tf_alignment": "MIXED",
        "signal_confidence": 0,
        "entry_quality": "LOW",
    }
    enriched = _enrich_trade(trade, [snap])
    assert enriched["confidence"] == 3
    assert enriched["entry_quality"] == "MEDIUM"
    assert enriched["paper_confidence"] == "UNKNOWN"
    assert enriched["paper_entry_quality"] == "UNKNOWN"
    assert enriched["paper_source"] == "setup_engine:PULLBACK_ENTRY"
    assert enriched["snapshot_signal_confidence"] == 0


if __name__ == "__main__":
    test_resolve_paper_no_setup_passthrough()
    test_resolve_paper_wait_setup_boost_zero_to_three()
    test_snapshot_persists_paper_fields()
    test_enrich_trade_does_not_clobber_trade_confidence()
    test_enrich_trade_legacy_snapshot_without_paper_fields()
    print("All paper observability tests passed.")
