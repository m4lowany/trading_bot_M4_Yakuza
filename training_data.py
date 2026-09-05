"""
Training Data Logger V1 — observability / learning infra only.

Does NOT affect trading decisions. Failures must be caught by callers
so paper trading continues uninterrupted.
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "v1"
DEFAULT_RELATIVE_DATASET = os.path.join("data", "training", "training_samples_v1.jsonl")


def training_dataset_path(repo_root: Optional[str] = None) -> str:
    env = os.environ.get("YAKUZA_TRAINING_DATASET")
    if env:
        return env
    root = repo_root or os.getcwd()
    return os.path.join(root, DEFAULT_RELATIVE_DATASET)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00").split("+")[0])
    except ValueError:
        return None


def _duration_seconds(opened_at: Optional[str], closed_at: Optional[str]) -> Optional[float]:
    a, b = _parse_iso(opened_at), _parse_iso(closed_at)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds(), 6)


def _pnl_percent(side: str, entry_price: float, price: float) -> float:
    if entry_price <= 0:
        return 0.0
    move = ((price - entry_price) / entry_price) * 100.0
    if side == "SELL":
        move = -move
    return round(move, 6)


def init_path_tracker(
    *,
    side: str,
    entry_price: float,
    timestamp: str,
) -> Dict[str, Any]:
    """Start path observation at entry (observation only)."""
    pnl0 = _pnl_percent(side, entry_price, entry_price)
    return {
        "lowest_price": float(entry_price),
        "highest_price": float(entry_price),
        "lowest_at": timestamp,
        "highest_at": timestamp,
        "mae_percent": pnl0,
        "mfe_percent": pnl0,
        "max_adverse_price": float(entry_price),
        "max_favorable_price": float(entry_price),
        "mae_at": timestamp,
        "mfe_at": timestamp,
        "opened_at": timestamp,
        "updates": 1,
    }


def update_path_tracker(
    path: Dict[str, Any],
    *,
    side: str,
    entry_price: float,
    price: float,
    timestamp: str,
) -> Dict[str, Any]:
    """Update high/low and MAE/MFE from current mark price."""
    updated = deepcopy(path) if path else init_path_tracker(
        side=side, entry_price=entry_price, timestamp=timestamp
    )
    px = float(price)
    pnl = _pnl_percent(side, float(entry_price), px)

    if px < float(updated["lowest_price"]):
        updated["lowest_price"] = px
        updated["lowest_at"] = timestamp
    if px > float(updated["highest_price"]):
        updated["highest_price"] = px
        updated["highest_at"] = timestamp

    # MAE = most adverse unrealized PnL% (min); MFE = most favorable (max)
    if pnl < float(updated["mae_percent"]):
        updated["mae_percent"] = pnl
        updated["max_adverse_price"] = px
        updated["mae_at"] = timestamp
    if pnl > float(updated["mfe_percent"]):
        updated["mfe_percent"] = pnl
        updated["max_favorable_price"] = px
        updated["mfe_at"] = timestamp

    updated["updates"] = int(updated.get("updates", 0)) + 1
    return updated


def finalize_path_metrics(
    path: Optional[Dict[str, Any]],
    *,
    opened_at: Optional[str],
) -> Dict[str, Any]:
    """
    Derive close-time path labels.

    MAE/MFE are unrealized PnL% extremes relative to entry (side-aware):
    - MFE% = best (max) unrealized pnl% seen
    - MAE% = worst (min) unrealized pnl% seen
    """
    if not path:
        return {
            "mae_percent": None,
            "mfe_percent": None,
            "max_adverse_price": None,
            "max_favorable_price": None,
            "time_to_mae_seconds": None,
            "time_to_mfe_seconds": None,
            "path_lowest_price": None,
            "path_highest_price": None,
            "path_updates": None,
        }

    open_ts = path.get("opened_at") or opened_at
    return {
        "mae_percent": path.get("mae_percent"),
        "mfe_percent": path.get("mfe_percent"),
        "max_adverse_price": path.get("max_adverse_price"),
        "max_favorable_price": path.get("max_favorable_price"),
        "time_to_mae_seconds": _duration_seconds(open_ts, path.get("mae_at")),
        "time_to_mfe_seconds": _duration_seconds(open_ts, path.get("mfe_at")),
        "path_lowest_price": path.get("lowest_price"),
        "path_highest_price": path.get("highest_price"),
        "path_updates": path.get("updates"),
    }


def make_trade_id(trade: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(trade.get("timestamp") or ""),
            str(trade.get("closed_at") or ""),
            str(trade.get("side") or ""),
            str(trade.get("entry_price") or ""),
            str(trade.get("exit_price") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def make_sample_id(trade: Dict[str, Any]) -> str:
    return f"ts_{SCHEMA_VERSION}_{make_trade_id(trade)}"


def _label_from_pnl(pnl: Optional[float]) -> Optional[str]:
    if pnl is None:
        return None
    if pnl > 0:
        return "win"
    if pnl < 0:
        return "loss"
    return "flat"


def _get(d: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
    if not d:
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def build_training_sample(
    trade: Dict[str, Any],
    *,
    snapshot: Optional[Dict[str, Any]] = None,
    entry_context: Optional[Dict[str, Any]] = None,
    path_metrics: Optional[Dict[str, Any]] = None,
    source: str = "live",
    trend_timeframe: Optional[str] = None,
    confirm_timeframe: Optional[str] = None,
    entry_timeframe: Optional[str] = None,
    symbol_default: str = "BTC/USDT",
) -> Dict[str, Any]:
    """
    Build one V1 labeled sample from a CLOSED trade.

    Missing values stay null. Never invent MAE/MFE when path_metrics absent.
    """
    ctx = entry_context or trade.get("training_context") or {}
    snap = snapshot or {}
    path = path_metrics
    if path is None and trade.get("path_tracker"):
        path = finalize_path_metrics(
            trade.get("path_tracker"), opened_at=trade.get("timestamp")
        )
    if path is None:
        path = finalize_path_metrics(None, opened_at=trade.get("timestamp"))

    nested = snap.get("structure_events") if isinstance(snap.get("structure_events"), dict) else {}
    events_ctx = ctx.get("structure_events") if isinstance(ctx.get("structure_events"), dict) else {}

    pnl = trade.get("pnl_percent")
    try:
        pnl_f = float(pnl) if pnl is not None else None
    except (TypeError, ValueError):
        pnl_f = None

    sample = {
        "schema_version": SCHEMA_VERSION,
        "sample_id": make_sample_id(trade),
        "trade_id": make_trade_id(trade),
        "source": source,
        "symbol": _get(snap, "symbol") or _get(ctx, "symbol") or symbol_default,
        "opened_at": trade.get("timestamp"),
        "closed_at": trade.get("closed_at"),
        # MARKET
        "entry_price": trade.get("entry_price"),
        "exit_price": trade.get("exit_price"),
        "trend_timeframe": trend_timeframe or _get(ctx, "trend_timeframe"),
        "confirm_timeframe": confirm_timeframe or _get(ctx, "confirm_timeframe"),
        "entry_timeframe": entry_timeframe or _get(ctx, "entry_timeframe"),
        # INDICATORS (prefer entry_context captured at open; else null)
        "ma60": _get(ctx, "ma60"),
        "ema238": _get(ctx, "ema238"),
        "rsi": _get(ctx, "rsi"),
        "fvg_type": _get(ctx, "fvg_type") or _get(snap, "fvg_type"),
        "fvg_touched": _get(ctx, "fvg_touched", default=_get(snap, "fvg_touched")),
        "fvg_rejection_after_touch": _get(
            ctx, "rejection_after_touch", default=_get(snap, "rejection_after_touch")
        ),
        "fvg_gap_size_percent": _get(ctx, "fvg_gap_size_percent"),
        "bag": _get(ctx, "bag"),
        "fibo_signal": _get(ctx, "fibo_signal"),
        "fibo_direction": _get(ctx, "fibo_direction"),
        "fibo_zone": _get(ctx, "fibo_zone"),
        "fibo_retracement": _get(ctx, "fibo_retracement"),
        # STRUCTURE
        "market_structure": _get(snap, "market_structure") or _get(ctx, "market_structure"),
        "structure_character": (
            _get(events_ctx, "structure_character")
            or _get(nested, "structure_character")
            or _get(ctx, "structure_character")
        ),
        "structure_phase": (
            _get(events_ctx, "structure_phase")
            or _get(nested, "structure_phase")
            or _get(ctx, "structure_phase")
        ),
        "structure_strength": _get(snap, "structure_strength") or _get(ctx, "structure_strength"),
        "structure_event_bos": _get(snap, "structure_event_bos") or _get(ctx, "structure_event_bos"),
        "structure_event_choch": _get(snap, "structure_event_choch")
        or _get(ctx, "structure_event_choch"),
        "control_shift": _get(snap, "control_shift") or _get(ctx, "control_shift"),
        "buyers_take_control": _get(snap, "buyers_take_control", default=_get(ctx, "buyers_take_control")),
        "sellers_take_control": _get(
            snap, "sellers_take_control", default=_get(ctx, "sellers_take_control")
        ),
        "momentum": _get(snap, "momentum") or _get(ctx, "momentum"),
        "liquidity_event": _get(ctx, "liquidity_event"),
        "fake_breakout": _get(snap, "fake_breakout", default=_get(ctx, "fake_breakout")),
        "wick_rejection": _get(snap, "wick_rejection") or _get(ctx, "wick_rejection"),
        # SIGNAL
        "raw_score": _get(ctx, "raw_score"),
        "signal": _get(snap, "signal") or _get(ctx, "signal"),
        "signal_confidence": _get(snap, "signal_confidence", default=_get(ctx, "signal_confidence")),
        "entry_quality_signal_path": _get(snap, "entry_quality") or _get(ctx, "entry_quality"),
        "tf_alignment": _get(snap, "tf_alignment") or _get(ctx, "tf_alignment"),
        "alignment_strength": _get(snap, "alignment_strength") or _get(ctx, "alignment_strength"),
        # SETUP / PAPER
        "setup_type": _get(snap, "setup_type") or _get(ctx, "setup_type"),
        "setup_direction": _get(snap, "setup_direction") or _get(ctx, "setup_direction"),
        "setup_quality": _get(snap, "setup_quality") or _get(ctx, "setup_quality"),
        "setup_reasons": _get(snap, "setup_reasons") or _get(ctx, "setup_reasons"),
        "paper_source": _get(snap, "paper_source")
        or _get(ctx, "paper_source")
        or (
            f"setup_engine:{trade.get('reason', '').split('setup_engine:', 1)[1].split()[0]}"
            if "setup_engine:" in str(trade.get("reason", ""))
            else None
        ),
        "paper_confidence": trade.get("confidence"),
        "paper_entry_quality": trade.get("entry_quality"),
        "paper_signal": trade.get("side"),
        # RISK
        "leverage": trade.get("leverage"),
        "risk_level": _get(snap, "risk_level") or _get(ctx, "risk_level"),
        "stop_loss_percent": trade.get("stop_loss_percent"),
        "target_profit_percent": trade.get("target_profit_percent"),
        # LABEL
        "label": _label_from_pnl(pnl_f),
        "pnl_percent": pnl_f,
        "pnl_percent_leveraged": trade.get("pnl_percent_leveraged"),
        "exit_reason": trade.get("close_reason"),
        "duration_seconds": _duration_seconds(trade.get("timestamp"), trade.get("closed_at")),
        "side": trade.get("side"),
        # PATH LABELS
        "mae_percent": path.get("mae_percent"),
        "mfe_percent": path.get("mfe_percent"),
        "max_adverse_price": path.get("max_adverse_price"),
        "max_favorable_price": path.get("max_favorable_price"),
        "time_to_mae_seconds": path.get("time_to_mae_seconds"),
        "time_to_mfe_seconds": path.get("time_to_mfe_seconds"),
        "path_lowest_price": path.get("path_lowest_price"),
        "path_highest_price": path.get("path_highest_price"),
        "path_updates": path.get("path_updates"),
    }
    return sample


def validate_training_sample(sample: Dict[str, Any]) -> List[str]:
    """Return list of malformation reasons (empty = OK)."""
    errors: List[str] = []
    if not isinstance(sample, dict):
        return ["sample_not_dict"]
    if sample.get("schema_version") != SCHEMA_VERSION:
        errors.append("bad_schema_version")
    if not sample.get("sample_id"):
        errors.append("missing_sample_id")
    if not sample.get("trade_id"):
        errors.append("missing_trade_id")
    if sample.get("side") not in ("BUY", "SELL", None):
        errors.append("bad_side")
    if sample.get("label") not in ("win", "loss", "flat", None):
        errors.append("bad_label")
    if sample.get("opened_at") and _parse_iso(sample.get("opened_at")) is None:
        errors.append("bad_opened_at")
    if sample.get("closed_at") and _parse_iso(sample.get("closed_at")) is None:
        errors.append("bad_closed_at")
    return errors


def append_training_sample(dataset_path: str, sample: Dict[str, Any]) -> None:
    """Append-only write. Raises on failure (caller must catch)."""
    errors = validate_training_sample(sample)
    if errors:
        raise ValueError(f"malformed training sample: {errors}")
    os.makedirs(os.path.dirname(dataset_path) or ".", exist_ok=True)
    with open(dataset_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def load_training_samples(dataset_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(dataset_path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_malformed_line": line})
    return rows


def sample_id_exists(dataset_path: str, sample_id: str) -> bool:
    for row in load_training_samples(dataset_path):
        if row.get("sample_id") == sample_id:
            return True
    return False


def safe_record_closed_trade(
    *,
    log_dir: str,
    closed_trade: Dict[str, Any],
    dataset_path: Optional[str] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    source: str = "live",
) -> Tuple[bool, Optional[str]]:
    """
    Fail-safe emitter used by paper_trader.

    Returns (ok, error_message). Never raises to caller.
    """
    try:
        path = dataset_path or training_dataset_path()
        # Prefer matching snapshot from setup_history when not provided
        snap = snapshot
        if snap is None:
            try:
                from setup_stats import load_setup_history, _match_snapshot_for_trade

                snaps = load_setup_history(log_dir)
                snap = _match_snapshot_for_trade(closed_trade, snaps)
            except Exception:
                snap = None

        sample = build_training_sample(
            closed_trade,
            snapshot=snap,
            entry_context=closed_trade.get("training_context"),
            source=source,
        )
        sid = sample["sample_id"]
        if sample_id_exists(path, sid):
            return True, None  # idempotent skip
        append_training_sample(path, sample)
        return True, None
    except Exception as exc:  # noqa: BLE001 — must never break paper
        return False, f"{type(exc).__name__}: {exc}"


def build_entry_training_context(
    *,
    symbol: str,
    score: int,
    signal: str,
    signal_confidence: int,
    entry_quality: str,
    tf_alignment: str,
    alignment_strength: str,
    setup_type: str,
    setup_direction: str,
    setup_quality: str,
    setup_reasons: List[str],
    paper_source: str,
    paper_confidence: int,
    paper_entry_quality: str,
    structure_data: Dict[str, Any],
    price_action_data: Dict[str, Any],
    fvg_data: Dict[str, Any],
    indicator_status: Dict[str, Any],
    structure_events: Dict[str, Any],
    risk_level: str,
    trend_timeframe: str,
    confirm_timeframe: str,
    entry_timeframe: str,
) -> Dict[str, Any]:
    """Capture open-time features for later labeling (observation only)."""
    fibo = indicator_status.get("FIBO") if isinstance(indicator_status.get("FIBO"), dict) else {}
    return {
        "symbol": symbol,
        "raw_score": score,
        "signal": signal,
        "signal_confidence": signal_confidence,
        "entry_quality": entry_quality,
        "tf_alignment": tf_alignment,
        "alignment_strength": alignment_strength,
        "setup_type": setup_type,
        "setup_direction": setup_direction,
        "setup_quality": setup_quality,
        "setup_reasons": list(setup_reasons),
        "paper_source": paper_source,
        "paper_confidence": paper_confidence,
        "paper_entry_quality": paper_entry_quality,
        "market_structure": structure_data.get("structure"),
        "structure_strength": structure_data.get("structure_strength"),
        "momentum": structure_data.get("momentum"),
        "liquidity_event": structure_data.get("liquidity_event"),
        "fake_breakout": price_action_data.get("fake_breakout"),
        "wick_rejection": price_action_data.get("wick_rejection"),
        "fvg_type": fvg_data.get("fvg_type"),
        "fvg_touched": fvg_data.get("fvg_touched"),
        "rejection_after_touch": fvg_data.get("rejection_after_touch"),
        "fvg_gap_size_percent": fvg_data.get("gap_size_percent"),
        "ma60": indicator_status.get("MA60"),
        "ema238": indicator_status.get("EMA238"),
        "rsi": indicator_status.get("RSI"),
        "bag": indicator_status.get("BAG"),
        "fibo_signal": fibo.get("fibo_signal"),
        "fibo_direction": fibo.get("fibo_direction"),
        "fibo_zone": fibo.get("fibo_zone"),
        "fibo_retracement": fibo.get("retracement"),
        "structure_event_bos": structure_events.get("bos"),
        "structure_event_choch": structure_events.get("choch"),
        "control_shift": structure_events.get("control_shift"),
        "buyers_take_control": structure_events.get("buyers_take_control"),
        "sellers_take_control": structure_events.get("sellers_take_control"),
        "structure_character": structure_events.get("structure_character"),
        "structure_phase": structure_events.get("structure_phase"),
        "structure_events": {
            "structure_character": structure_events.get("structure_character"),
            "structure_phase": structure_events.get("structure_phase"),
            "bos": structure_events.get("bos"),
            "choch": structure_events.get("choch"),
            "control_shift": structure_events.get("control_shift"),
        },
        "risk_level": risk_level,
        "trend_timeframe": trend_timeframe,
        "confirm_timeframe": confirm_timeframe,
        "entry_timeframe": entry_timeframe,
    }
