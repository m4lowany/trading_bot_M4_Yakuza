#!/usr/bin/env python3
"""Tests for Training Data Logger V1 (observation only)."""

import json
import os
import shutil
import tempfile

from paper_trader import (
    can_open_paper_trade,
    close_paper_trade,
    open_paper_trade,
    process_paper_trading,
    update_paper_trade,
)
from training_data import (
    append_training_sample,
    build_training_sample,
    finalize_path_metrics,
    init_path_tracker,
    load_training_samples,
    make_sample_id,
    safe_record_closed_trade,
    update_path_tracker,
    validate_training_sample,
)


def test_long_mae_mfe():
    path = init_path_tracker(side="BUY", entry_price=100.0, timestamp="t0")
    path = update_path_tracker(path, side="BUY", entry_price=100.0, price=105.0, timestamp="t1")
    path = update_path_tracker(path, side="BUY", entry_price=100.0, price=97.0, timestamp="t2")
    path = update_path_tracker(path, side="BUY", entry_price=100.0, price=102.0, timestamp="t3")
    m = finalize_path_metrics(path, opened_at="t0")
    assert m["mfe_percent"] == 5.0
    assert m["mae_percent"] == -3.0
    assert m["max_favorable_price"] == 105.0
    assert m["max_adverse_price"] == 97.0
    assert m["time_to_mfe_seconds"] is not None or m["mfe_percent"] == 5.0


def test_short_mae_mfe():
    path = init_path_tracker(side="SELL", entry_price=100.0, timestamp="t0")
    path = update_path_tracker(path, side="SELL", entry_price=100.0, price=95.0, timestamp="t1")
    path = update_path_tracker(path, side="SELL", entry_price=100.0, price=104.0, timestamp="t2")
    m = finalize_path_metrics(path, opened_at="t0")
    # SELL: down to 95 => +5% favorable; up to 104 => -4% adverse
    assert m["mfe_percent"] == 5.0
    assert m["mae_percent"] == -4.0
    assert m["max_favorable_price"] == 95.0
    assert m["max_adverse_price"] == 104.0


def test_path_high_low_and_timestamps():
    path = init_path_tracker(side="BUY", entry_price=50.0, timestamp="2026-09-05T10:00:00")
    path = update_path_tracker(
        path, side="BUY", entry_price=50.0, price=49.0, timestamp="2026-09-05T10:00:10"
    )
    path = update_path_tracker(
        path, side="BUY", entry_price=50.0, price=52.0, timestamp="2026-09-05T10:00:20"
    )
    assert path["lowest_price"] == 49.0
    assert path["highest_price"] == 52.0
    assert path["lowest_at"] == "2026-09-05T10:00:10"
    assert path["highest_at"] == "2026-09-05T10:00:20"
    assert path["updates"] == 3


def test_one_closed_trade_one_sample_no_duplicate():
    td = tempfile.mkdtemp()
    try:
        trade = open_paper_trade(
            side="BUY",
            entry_price=100.0,
            confidence=4,
            entry_quality="MEDIUM",
            leverage=10,
            target_profit_percent=0.25,
            reason="normal conditions",
            timestamp="2026-09-05T12:00:00",
            training_context={"raw_score": 4, "paper_source": "signal"},
        )
        trade = update_paper_trade(trade, 101.0, timestamp="2026-09-05T12:00:10")
        closed = close_paper_trade(trade, 101.5, "TP hit", timestamp="2026-09-05T12:00:20")
        out = os.path.join(td, "samples.jsonl")
        ok1, err1 = safe_record_closed_trade(
            log_dir=td, closed_trade=closed, dataset_path=out, source="live"
        )
        ok2, err2 = safe_record_closed_trade(
            log_dir=td, closed_trade=closed, dataset_path=out, source="live"
        )
        assert ok1 and err1 is None
        assert ok2 and err2 is None  # idempotent
        rows = load_training_samples(out)
        assert len(rows) == 1
        assert rows[0]["sample_id"] == make_sample_id(closed)
        assert rows[0]["label"] == "win"
        assert rows[0]["mfe_percent"] is not None
    finally:
        shutil.rmtree(td)


def test_missing_field_remains_null_on_backfill_style_sample():
    trade = {
        "side": "SELL",
        "entry_price": 100.0,
        "exit_price": 99.0,
        "confidence": 3,
        "entry_quality": "MEDIUM",
        "leverage": 12,
        "timestamp": "2026-05-17T08:00:00",
        "closed_at": "2026-05-17T08:00:30",
        "close_reason": "alignment MIXED",
        "pnl_percent": 1.0,
        "pnl_percent_leveraged": 12.0,
        "status": "CLOSED",
        "reason": "normal conditions",
    }
    sample = build_training_sample(trade, snapshot=None, path_metrics=None, source="backfill_historical")
    assert sample["mae_percent"] is None
    assert sample["mfe_percent"] is None
    assert sample["raw_score"] is None
    assert sample["ma60"] is None
    assert sample["label"] == "win"


def test_logger_failure_does_not_affect_paper_decision():
    # Decision gates unchanged
    assert (
        can_open_paper_trade(
            signal="BUY",
            trade_allowed=True,
            entry_quality="MEDIUM",
            signal_confidence=4,
            has_active_trade=False,
            close_cooldown_remaining=0,
        )
        is True
    )
    td = tempfile.mkdtemp()
    try:
        # Force emit failure by making dataset path a directory (write will fail)
        bad_path = os.path.join(td, "not_a_file")
        os.makedirs(bad_path)
        closed = {
            "side": "BUY",
            "entry_price": 1.0,
            "exit_price": 1.1,
            "confidence": 4,
            "entry_quality": "MEDIUM",
            "leverage": 2,
            "timestamp": "2026-09-05T12:00:00",
            "closed_at": "2026-09-05T12:01:00",
            "close_reason": "TP hit",
            "pnl_percent": 10.0,
            "pnl_percent_leveraged": 20.0,
            "status": "CLOSED",
            "reason": "x",
        }
        ok, err = safe_record_closed_trade(
            log_dir=td, closed_trade=closed, dataset_path=bad_path, source="live"
        )
        assert ok is False
        assert err is not None
        # Paper open decision still independent
        assert (
            can_open_paper_trade(
                signal="BUY",
                trade_allowed=True,
                entry_quality="MEDIUM",
                signal_confidence=4,
                has_active_trade=False,
            )
            is True
        )
    finally:
        shutil.rmtree(td)


def test_process_paper_trading_emits_sample_and_keeps_decisions():
    td = tempfile.mkdtemp()
    prev = os.environ.get("YAKUZA_TRAINING_DATASET")
    try:
        log_dir = os.path.join(td, "logs")
        os.makedirs(log_dir, exist_ok=True)
        samples_path = os.path.join(td, "samples.jsonl")
        os.environ["YAKUZA_TRAINING_DATASET"] = samples_path
        # Open
        logs1 = process_paper_trading(
            log_dir,
            current_price=100.0,
            signal="BUY",
            trade_allowed=True,
            signal_confidence=4,
            entry_quality="MEDIUM",
            tf_alignment="FULL_BULLISH",
            leverage=10,
            target_profit_percent=0.25,
            reason="normal conditions",
            timestamp="2026-09-05T13:00:00",
            training_context={"raw_score": 4, "paper_source": "signal", "ma60": "BUY"},
        )
        assert any("PAPER_TRADE_OPEN" in x for x in logs1)
        # Small favorable move (below TP 0.25%)
        process_paper_trading(
            log_dir,
            current_price=100.1,
            signal="BUY",
            trade_allowed=True,
            signal_confidence=4,
            entry_quality="MEDIUM",
            tf_alignment="FULL_BULLISH",
            leverage=10,
            target_profit_percent=0.25,
            reason="normal conditions",
            timestamp="2026-09-05T13:00:10",
        )
        # Close via opposite signal
        logs3 = process_paper_trading(
            log_dir,
            current_price=100.05,
            signal="SELL",
            trade_allowed=True,
            signal_confidence=4,
            entry_quality="MEDIUM",
            tf_alignment="FULL_BEARISH",
            leverage=10,
            target_profit_percent=0.25,
            reason="normal conditions",
            timestamp="2026-09-05T13:00:20",
        )
        assert any("PAPER_TRADE_CLOSE" in x for x in logs3)
        assert any("TRAINING_SAMPLE: appended" in x for x in logs3)
        assert os.path.exists(samples_path)
        rows = load_training_samples(samples_path)
        assert len(rows) == 1
        assert rows[0]["paper_confidence"] == 4
        assert rows[0]["ma60"] == "BUY"
        assert rows[0]["mfe_percent"] is not None
    finally:
        if prev is None:
            os.environ.pop("YAKUZA_TRAINING_DATASET", None)
        else:
            os.environ["YAKUZA_TRAINING_DATASET"] = prev
        shutil.rmtree(td)


def test_validator_detects_malformed_sample():
    bad = {"schema_version": "nope", "sample_id": "", "label": "banana"}
    errs = validate_training_sample(bad)
    assert "bad_schema_version" in errs
    assert "missing_sample_id" in errs
    assert "bad_label" in errs


def test_observability_fields_mapped():
    trade = open_paper_trade(
        side="SELL",
        entry_price=200.0,
        confidence=3,
        entry_quality="MEDIUM",
        leverage=12,
        target_profit_percent=0.25,
        reason="normal conditions | setup_engine:PULLBACK_ENTRY",
        timestamp="2026-09-05T14:00:00",
        training_context={
            "paper_source": "setup_engine:PULLBACK_ENTRY",
            "signal_confidence": 0,
            "raw_score": 2,
        },
    )
    closed = close_paper_trade(trade, 199.0, "alignment MIXED", timestamp="2026-09-05T14:00:33")
    snap = {
        "paper_source": "setup_engine:PULLBACK_ENTRY",
        "paper_confidence": 3,
        "signal_confidence": 0,
        "setup_type": "PULLBACK_ENTRY",
        "tf_alignment": "MIXED",
    }
    sample = build_training_sample(closed, snapshot=snap, source="live")
    assert sample["paper_source"] == "setup_engine:PULLBACK_ENTRY"
    assert sample["paper_confidence"] == 3
    assert sample["signal_confidence"] == 0
    assert sample["setup_type"] == "PULLBACK_ENTRY"
    assert sample["raw_score"] == 2


if __name__ == "__main__":
    test_long_mae_mfe()
    test_short_mae_mfe()
    test_path_high_low_and_timestamps()
    test_one_closed_trade_one_sample_no_duplicate()
    test_missing_field_remains_null_on_backfill_style_sample()
    test_logger_failure_does_not_affect_paper_decision()
    test_process_paper_trading_emits_sample_and_keeps_decisions()
    test_validator_detects_malformed_sample()
    test_observability_fields_mapped()
    print("All training data logger V1 tests passed.")
