import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional


def _history_path(log_dir: str) -> str:
    return os.path.join(log_dir, "setup_history.jsonl")


def _paper_trades_path(log_dir: str) -> str:
    return os.path.join(log_dir, "paper_trades.json")


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


# Flat keys written to setup_history.jsonl (top-level, for stats/filters).
STRUCTURE_EVENT_FLAT_KEYS = (
    "structure_event_bos",
    "structure_event_choch",
    "control_shift",
    "buyers_take_control",
    "sellers_take_control",
    "structure_event_strength",
    "structure_event_reasons",
)


def structure_event_snapshot_fields(events: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map analyze_structure_events() output to setup_history fields.

    Returns flat fields (required for analytics) plus nested structure_events
    block with the full observer payload (swing levels, broken_level, etc.).
    """
    bos = events.get("bos", "NONE")
    choch = events.get("choch", "NONE")
    control_shift = events.get("control_shift", "NONE")
    buyers = bool(events.get("buyers_take_control", False))
    sellers = bool(events.get("sellers_take_control", False))
    strength = events.get("event_strength", "LOW")
    reasons = list(events.get("event_reasons") or [])

    return {
        "structure_event_bos": bos,
        "structure_event_choch": choch,
        "control_shift": control_shift,
        "buyers_take_control": buyers,
        "sellers_take_control": sellers,
        "structure_event_strength": strength,
        "structure_event_reasons": reasons,
        "structure_events": {
            "bos": bos,
            "choch": choch,
            "last_swing_high": events.get("last_swing_high"),
            "last_swing_low": events.get("last_swing_low"),
            "broken_level": events.get("broken_level"),
            "buyers_take_control": buyers,
            "sellers_take_control": sellers,
            "control_shift": control_shift,
            "event_strength": strength,
            "event_reasons": reasons,
        },
    }


def save_setup_snapshot(
    log_dir: str,
    *,
    timestamp: str,
    symbol: str,
    price: float,
    signal: str,
    paper_signal: str,
    paper_trade_allowed: bool,
    setup_type: str,
    setup_direction: str,
    setup_quality: str,
    signal_confidence: int,
    entry_quality: str,
    tf_alignment: str,
    alignment_strength: str,
    market_structure: str,
    structure_strength: str,
    momentum: str,
    risk_level: str,
    recommended_leverage: int,
    target_profit_percent: float,
    fvg_type: str,
    fvg_touched: bool,
    rejection_after_touch: bool,
    candle_strength: str,
    wick_rejection: str,
    fake_breakout: bool,
    support_reaction: bool,
    resistance_reaction: bool,
    momentum_shift: bool,
    setup_reasons: List[str],
    confidence_reasons: List[str],
    structure_events: Optional[Dict[str, Any]] = None,
    only_when_paper_signal: bool = False,
    paper_confidence: Optional[int] = None,
    paper_entry_quality: Optional[str] = None,
    paper_source: Optional[str] = None,
) -> None:
    """
    Append one JSON snapshot per line to logs/setup_history.jsonl.
    By default logs every iteration; set only_when_paper_signal=True to skip WAIT paper rows.

    Dual-path observability (does not affect trading logic):
    - signal_confidence / entry_quality — legacy MTF signal path
    - paper_confidence / paper_entry_quality / paper_source — values used by paper_trader
      (may differ after resolve_paper_from_setup boost/override)

    When paper_* args are omitted, they default to the signal-path equivalents
    and paper_source="signal" (safe for older callers / tests).

    Pass structure_events=analyze_structure_events(candles) for observer fields;
    does not affect trading logic elsewhere.
    """
    if only_when_paper_signal and paper_signal == "WAIT":
        return

    observer_fields = (
        structure_event_snapshot_fields(structure_events)
        if structure_events is not None
        else structure_event_snapshot_fields({})
    )

    resolved_paper_confidence = (
        int(paper_confidence) if paper_confidence is not None else int(signal_confidence)
    )
    resolved_paper_entry_quality = (
        paper_entry_quality if paper_entry_quality is not None else entry_quality
    )
    resolved_paper_source = paper_source if paper_source is not None else "signal"

    record = {
        "timestamp": timestamp,
        "symbol": symbol,
        "price": price,
        "signal": signal,
        "paper_signal": paper_signal,
        "paper_trade_allowed": paper_trade_allowed,
        "paper_confidence": resolved_paper_confidence,
        "paper_entry_quality": resolved_paper_entry_quality,
        "paper_source": resolved_paper_source,
        "setup_type": setup_type,
        "setup_direction": setup_direction,
        "setup_quality": setup_quality,
        "signal_confidence": signal_confidence,
        "entry_quality": entry_quality,
        "tf_alignment": tf_alignment,
        "alignment_strength": alignment_strength,
        "market_structure": market_structure,
        "structure_strength": structure_strength,
        "momentum": momentum,
        "risk_level": risk_level,
        "recommended_leverage": recommended_leverage,
        "target_profit_percent": target_profit_percent,
        "fvg_type": fvg_type,
        "fvg_touched": fvg_touched,
        "rejection_after_touch": rejection_after_touch,
        "candle_strength": candle_strength,
        "wick_rejection": wick_rejection,
        "fake_breakout": fake_breakout,
        "support_reaction": support_reaction,
        "resistance_reaction": resistance_reaction,
        "momentum_shift": momentum_shift,
        "setup_reasons": list(setup_reasons),
        "confidence_reasons": list(confidence_reasons),
    }
    record.update(observer_fields)

    os.makedirs(log_dir, exist_ok=True)
    path = _history_path(log_dir)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_setup_history(log_dir: str) -> List[Dict[str, Any]]:
    path = _history_path(log_dir)
    if not os.path.exists(path):
        return []

    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_paper_trades(log_dir: str) -> List[Dict[str, Any]]:
    path = _paper_trades_path(log_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    history = data.get("history", []) if isinstance(data, dict) else []
    closed = [t for t in history if isinstance(t, dict) and t.get("status") == "CLOSED"]
    return closed


def _setup_type_from_reason(reason: str) -> Optional[str]:
    if not reason:
        return None
    marker = "setup_engine:"
    if marker not in reason:
        return None
    tail = reason.split(marker, 1)[1]
    return tail.split("|")[0].strip() or None


def _match_snapshot_for_trade(
    trade: Dict[str, Any], snapshots: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    trade_ts = _parse_iso(trade.get("timestamp") or trade.get("closed_at"))
    if trade_ts is None:
        return None

    side = trade.get("side")
    best: Optional[Dict[str, Any]] = None
    best_delta = None

    for snap in snapshots:
        if snap.get("paper_signal") != side:
            continue
        snap_ts = _parse_iso(snap.get("timestamp"))
        if snap_ts is None:
            continue
        delta = (trade_ts - snap_ts).total_seconds()
        if delta < 0:
            continue
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = snap

    if best is not None and best_delta is not None and best_delta <= 3600:
        return best
    return None


def _nested_structure_events(snap: Dict[str, Any]) -> Dict[str, Any]:
    nested = snap.get("structure_events")
    return nested if isinstance(nested, dict) else {}


def _snapshot_string_field(snap: Dict[str, Any], flat_key: str, nested_key: str) -> str:
    if flat_key in snap and snap[flat_key] is not None:
        return str(snap[flat_key])
    nested = _nested_structure_events(snap)
    if nested_key in nested and nested[nested_key] is not None:
        return str(nested[nested_key])
    return "UNKNOWN"


def _snapshot_bool_field(snap: Dict[str, Any], flat_key: str) -> bool:
    if flat_key in snap:
        return bool(snap[flat_key])
    nested = _nested_structure_events(snap)
    if flat_key in nested:
        return bool(nested[flat_key])
    return False


def _apply_structure_fields_from_snapshot(
    target: Dict[str, Any], snap: Optional[Dict[str, Any]]
) -> None:
    if not snap:
        target.setdefault("structure_event_bos", "UNKNOWN")
        target.setdefault("structure_event_choch", "UNKNOWN")
        target.setdefault("control_shift", "UNKNOWN")
        target.setdefault("buyers_take_control", False)
        target.setdefault("sellers_take_control", False)
        target.setdefault("structure_event_strength", "UNKNOWN")
        return

    target["structure_event_bos"] = _snapshot_string_field(
        snap, "structure_event_bos", "bos"
    )
    target["structure_event_choch"] = _snapshot_string_field(
        snap, "structure_event_choch", "choch"
    )
    target["control_shift"] = _snapshot_string_field(snap, "control_shift", "control_shift")
    target["buyers_take_control"] = _snapshot_bool_field(snap, "buyers_take_control")
    target["sellers_take_control"] = _snapshot_bool_field(snap, "sellers_take_control")
    target["structure_event_strength"] = _snapshot_string_field(
        snap, "structure_event_strength", "event_strength"
    )


def _apply_paper_observability_from_snapshot(
    target: Dict[str, Any], snap: Optional[Dict[str, Any]]
) -> None:
    """
    Attach snapshot paper_* / signal_* audit fields for analytics.

    Never overwrites trade.confidence or trade.entry_quality — those are the
    values actually used at paper open (authoritative for execution history).
    """
    if not snap:
        target.setdefault("paper_confidence", "UNKNOWN")
        target.setdefault("paper_entry_quality", "UNKNOWN")
        target.setdefault("paper_source", "UNKNOWN")
        target.setdefault("snapshot_signal_confidence", "UNKNOWN")
        target.setdefault("snapshot_entry_quality", "UNKNOWN")
        return

    if "paper_confidence" in snap and snap["paper_confidence"] is not None:
        target["paper_confidence"] = snap["paper_confidence"]
    else:
        target["paper_confidence"] = "UNKNOWN"

    if "paper_entry_quality" in snap and snap["paper_entry_quality"] is not None:
        target["paper_entry_quality"] = snap["paper_entry_quality"]
    else:
        target["paper_entry_quality"] = "UNKNOWN"

    if "paper_source" in snap and snap["paper_source"] is not None:
        target["paper_source"] = snap["paper_source"]
    else:
        # Infer for pre-observability history from trade reason suffix.
        from_reason = _setup_type_from_reason(str(target.get("reason", "")))
        target["paper_source"] = (
            f"setup_engine:{from_reason}" if from_reason else "UNKNOWN"
        )

    target["snapshot_signal_confidence"] = snap.get("signal_confidence", "UNKNOWN")
    target["snapshot_entry_quality"] = snap.get("entry_quality", "UNKNOWN")


def _enrich_trade(trade: Dict[str, Any], snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Join closed paper trade with entry snapshot for analytics.

    Preserves trade.confidence / trade.entry_quality (paper open decision).
    Adds setup/structure fields and paper_* observability from the snapshot.
    Do not compare snapshot signal_confidence to trade.confidence for
    setup_engine overrides — use paper_confidence / trade.confidence instead.
    """
    enriched = dict(trade)
    snap = _match_snapshot_for_trade(trade, snapshots)
    if snap:
        enriched["setup_type"] = snap.get("setup_type", "UNKNOWN")
        enriched["setup_quality"] = snap.get("setup_quality", "UNKNOWN")
        enriched["tf_alignment"] = snap.get("tf_alignment", "UNKNOWN")
        _apply_structure_fields_from_snapshot(enriched, snap)
        _apply_paper_observability_from_snapshot(enriched, snap)
    else:
        from_reason = _setup_type_from_reason(str(trade.get("reason", "")))
        enriched["setup_type"] = from_reason or "UNKNOWN"
        enriched["setup_quality"] = trade.get("entry_quality", "UNKNOWN")
        enriched["tf_alignment"] = "UNKNOWN"
        _apply_structure_fields_from_snapshot(enriched, None)
        _apply_paper_observability_from_snapshot(enriched, None)
    return enriched


def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _win_rate(trades: List[Dict[str, Any]]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if float(t.get("pnl_percent", 0)) > 0)
    return _pct(wins, len(trades))


def _breakdown_row(group: List[Dict[str, Any]], *, has_pnl: bool = True) -> Dict[str, Any]:
    count = len(group)
    if not has_pnl or count == 0:
        return {
            "count": count,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "average_pnl": None,
            "has_pnl": False,
        }

    pnls = [float(t.get("pnl_percent", 0)) for t in group]
    wins = sum(1 for p in pnls if p > 0)
    losses = count - wins
    return {
        "count": count,
        "wins": wins,
        "losses": losses,
        "win_rate": _pct(wins, count),
        "average_pnl": _avg(pnls),
        "has_pnl": True,
    }


def _breakdown(trades: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        label = str(trade.get(key, "UNKNOWN"))
        groups[label].append(trade)

    result: Dict[str, Dict[str, Any]] = {}
    for label, group in sorted(groups.items()):
        result[label] = _breakdown_row(group, has_pnl=True)
    return result


def _snapshot_count_breakdown(
    snapshots: List[Dict[str, Any]], key: str, *, bool_field: bool = False
) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, int] = defaultdict(int)
    for snap in snapshots:
        if bool_field:
            label = str(_snapshot_bool_field(snap, key))
        elif key == "structure_event_bos":
            label = _snapshot_string_field(snap, "structure_event_bos", "bos")
        elif key == "structure_event_choch":
            label = _snapshot_string_field(snap, "structure_event_choch", "choch")
        elif key == "control_shift":
            label = _snapshot_string_field(snap, "control_shift", "control_shift")
        elif key == "structure_event_strength":
            label = _snapshot_string_field(snap, "structure_event_strength", "event_strength")
        else:
            label = str(snap.get(key, "UNKNOWN"))
        groups[label] += 1

    return {
        label: {
            "count": count,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "average_pnl": None,
            "has_pnl": False,
        }
        for label, count in sorted(groups.items())
    }


def _breakdown_composite(
    items: List[Dict[str, Any]], keys: List[str], *, has_pnl: bool
) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        parts = [str(item.get(k, "UNKNOWN")) for k in keys]
        label = " | ".join(parts)
        groups[label].append(item)

    return {
        label: _breakdown_row(group, has_pnl=has_pnl)
        for label, group in sorted(groups.items())
    }


def _best_worst_setup_type(trades: List[Dict[str, Any]]) -> Dict[str, str]:
    by_type: Dict[str, List[float]] = defaultdict(list)
    for trade in trades:
        st = str(trade.get("setup_type", "UNKNOWN"))
        by_type[st].append(float(trade.get("pnl_percent", 0)))

    rated = []
    for st, pnls in by_type.items():
        if st == "UNKNOWN" or len(pnls) < 1:
            continue
        rated.append((st, _avg(pnls), len(pnls)))

    if not rated:
        return {"best_setup_type": "n/a", "worst_setup_type": "n/a"}

    rated.sort(key=lambda x: x[1], reverse=True)
    return {
        "best_setup_type": rated[0][0],
        "worst_setup_type": rated[-1][0],
    }


def _setup_type_trade_stats(
    trades: List[Dict[str, Any]], setup_type: str
) -> Dict[str, Any]:
    filtered = [t for t in trades if t.get("setup_type") == setup_type]
    return {
        "count": len(filtered),
        "win_rate": _win_rate(filtered),
        "average_pnl": _avg([float(t.get("pnl_percent", 0)) for t in filtered]),
    }


def generate_stats(log_dir: str = "logs") -> Dict[str, Any]:
    snapshots = load_setup_history(log_dir)
    closed_trades = load_paper_trades(log_dir)
    enriched_trades = [_enrich_trade(t, snapshots) for t in closed_trades]

    qualifying_setups = [
        s for s in snapshots if s.get("setup_type") not in (None, "", "NO_SETUP")
    ]
    actionable_snapshots = [s for s in snapshots if s.get("paper_signal") != "WAIT"]

    wins = [t for t in enriched_trades if float(t.get("pnl_percent", 0)) > 0]
    tp_hits = [t for t in enriched_trades if t.get("close_reason") == "TP hit"]
    sl_hits = [t for t in enriched_trades if t.get("close_reason") == "SL hit"]
    leverages = [
        float(t.get("leverage", 0)) for t in enriched_trades if t.get("leverage")
    ]

    setup_quality_breakdown = _breakdown(enriched_trades, "setup_quality")
    entry_quality_breakdown = _breakdown(enriched_trades, "entry_quality")
    tf_alignment_breakdown = _breakdown(enriched_trades, "tf_alignment")

    setup_type_breakdown = _breakdown(enriched_trades, "setup_type")

    best_worst = _best_worst_setup_type(enriched_trades)

    structure_bos_snapshots = _snapshot_count_breakdown(
        snapshots, "structure_event_bos"
    )
    structure_choch_snapshots = _snapshot_count_breakdown(
        snapshots, "structure_event_choch"
    )
    control_shift_snapshots = _snapshot_count_breakdown(snapshots, "control_shift")
    buyers_snapshots = _snapshot_count_breakdown(
        snapshots, "buyers_take_control", bool_field=True
    )
    sellers_snapshots = _snapshot_count_breakdown(
        snapshots, "sellers_take_control", bool_field=True
    )
    strength_snapshots = _snapshot_count_breakdown(
        snapshots, "structure_event_strength"
    )

    structure_bos_trades = _breakdown(enriched_trades, "structure_event_bos")
    structure_choch_trades = _breakdown(enriched_trades, "structure_event_choch")
    control_shift_trades = _breakdown(enriched_trades, "control_shift")
    buyers_trades = _breakdown(enriched_trades, "buyers_take_control")
    sellers_trades = _breakdown(enriched_trades, "sellers_take_control")
    strength_trades = _breakdown(enriched_trades, "structure_event_strength")

    setup_type_choch_trades = _breakdown_composite(
        enriched_trades,
        ["setup_type", "structure_event_choch"],
        has_pnl=True,
    )
    setup_type_bos_trades = _breakdown_composite(
        enriched_trades,
        ["setup_type", "structure_event_bos"],
        has_pnl=True,
    )
    setup_quality_strength_trades = _breakdown_composite(
        enriched_trades,
        ["setup_quality", "structure_event_strength"],
        has_pnl=True,
    )

    setup_type_choch_snapshots = _breakdown_composite(
        snapshots,
        ["setup_type", "structure_event_choch"],
        has_pnl=False,
    )
    setup_type_bos_snapshots = _breakdown_composite(
        snapshots,
        ["setup_type", "structure_event_bos"],
        has_pnl=False,
    )
    setup_quality_strength_snapshots = _breakdown_composite(
        snapshots,
        ["setup_quality", "structure_event_strength"],
        has_pnl=False,
    )

    snapshots_with_structure = sum(
        1
        for s in snapshots
        if _snapshot_string_field(s, "structure_event_bos", "bos") != "UNKNOWN"
        or _nested_structure_events(s)
    )

    return {
        "total_snapshots": len(snapshots),
        "total_setups": len(qualifying_setups),
        "total_actionable_snapshots": len(actionable_snapshots),
        "total_paper_trades": len(enriched_trades),
        "win_rate": _win_rate(enriched_trades),
        "average_pnl": _avg([float(t.get("pnl_percent", 0)) for t in enriched_trades]),
        "average_pnl_leveraged": _avg(
            [float(t.get("pnl_percent_leveraged", 0)) for t in enriched_trades]
        ),
        "wins": len(wins),
        "losses": len(enriched_trades) - len(wins),
        "best_setup_type": best_worst["best_setup_type"],
        "worst_setup_type": best_worst["worst_setup_type"],
        "setup_type_breakdown": setup_type_breakdown,
        "breakdown_by_setup_quality": setup_quality_breakdown,
        "breakdown_by_entry_quality": entry_quality_breakdown,
        "breakdown_by_tf_alignment": tf_alignment_breakdown,
        "average_leverage": _avg(leverages),
        "tp_hit_percent": _pct(len(tp_hits), len(enriched_trades)),
        "sl_hit_percent": _pct(len(sl_hits), len(enriched_trades)),
        "reversal_setups": _setup_type_trade_stats(
            enriched_trades, "REVERSAL_ATTEMPT"
        ),
        "trend_continuation_setups": _setup_type_trade_stats(
            enriched_trades, "TREND_CONTINUATION"
        ),
        "pullback_setups": _setup_type_trade_stats(enriched_trades, "PULLBACK_ENTRY"),
        "snapshots_with_structure_fields": snapshots_with_structure,
        "structure_event_snapshot_counts": {
            "structure_event_bos": structure_bos_snapshots,
            "structure_event_choch": structure_choch_snapshots,
            "control_shift": control_shift_snapshots,
            "buyers_take_control": buyers_snapshots,
            "sellers_take_control": sellers_snapshots,
            "structure_event_strength": strength_snapshots,
        },
        "structure_event_trade_performance": {
            "structure_event_bos": structure_bos_trades,
            "structure_event_choch": structure_choch_trades,
            "control_shift": control_shift_trades,
            "buyers_take_control": buyers_trades,
            "sellers_take_control": sellers_trades,
            "structure_event_strength": strength_trades,
        },
        "structure_event_cross_snapshot_counts": {
            "setup_type_structure_event_choch": setup_type_choch_snapshots,
            "setup_type_structure_event_bos": setup_type_bos_snapshots,
            "setup_quality_structure_event_strength": setup_quality_strength_snapshots,
        },
        "structure_event_cross_trade_performance": {
            "setup_type_structure_event_choch": setup_type_choch_trades,
            "setup_type_structure_event_bos": setup_type_bos_trades,
            "setup_quality_structure_event_strength": setup_quality_strength_trades,
        },
    }


def _format_breakdown_lines(
    breakdown: Dict[str, Dict[str, Any]], *, show_pnl: bool, empty_msg: str = "  (no data)"
) -> List[str]:
    if not breakdown:
        return [empty_msg]

    lines = []
    for label, row in breakdown.items():
        count = row.get("count", 0)
        if show_pnl and row.get("has_pnl"):
            avg = row.get("average_pnl")
            pnl_str = f"{avg:+.4f}%" if avg is not None else "n/a"
            lines.append(
                f"  {label:42} count={count:5}  wins={row.get('wins', 0):3}  "
                f"losses={row.get('losses', 0):3}  win_rate={row.get('win_rate', 0):6}%  "
                f"avg_pnl={pnl_str}"
            )
        else:
            lines.append(f"  {label:42} count={count:5}")
    return lines


def format_stats_report(stats: Dict[str, Any]) -> str:
    lines = [
        "===== SETUP STATS =====",
        "",
        "--- Overview ---",
        f"Total snapshots:          {stats['total_snapshots']}",
        f"Total setups (non-NO):    {stats['total_setups']}",
        f"Actionable paper snaps:   {stats['total_actionable_snapshots']}",
        f"Closed paper trades:      {stats['total_paper_trades']}",
        f"Wins / Losses:            {stats['wins']} / {stats['losses']}",
        f"Win rate:                 {stats['win_rate']}%",
        f"Average PnL:              {stats['average_pnl']}%",
        f"Average PnL (leveraged):  {stats['average_pnl_leveraged']}%",
        f"Average leverage:         {stats['average_leverage']}",
        f"TP hit %:                 {stats['tp_hit_percent']}%",
        f"SL hit %:                 {stats['sl_hit_percent']}%",
        f"Best setup type:          {stats['best_setup_type']}",
        f"Worst setup type:         {stats['worst_setup_type']}",
        "",
        "--- Setup type performance (closed trades) ---",
    ]

    lines.extend(
        _format_breakdown_lines(
            stats.get("setup_type_breakdown", {}),
            show_pnl=True,
            empty_msg="  (no closed trades yet)",
        )
    )

    lines.extend(
        [
            "",
            "--- By setup_quality ---",
        ]
    )
    lines.extend(
        _format_breakdown_lines(
            stats.get("breakdown_by_setup_quality", {}), show_pnl=True
        )
    )

    lines.extend(["", "--- By entry_quality ---"])
    lines.extend(
        _format_breakdown_lines(
            stats.get("breakdown_by_entry_quality", {}), show_pnl=True
        )
    )

    lines.extend(["", "--- By tf_alignment ---"])
    lines.extend(
        _format_breakdown_lines(
            stats.get("breakdown_by_tf_alignment", {}), show_pnl=True
        )
    )

    snap_struct = stats.get("snapshots_with_structure_fields", 0)
    lines.extend(
        [
            "",
            "===== STRUCTURE EVENTS (setup_history.jsonl) =====",
            "",
            f"Snapshots total:              {stats.get('total_snapshots', 0)}",
            f"With structure fields:        {snap_struct}",
            "",
            "--- Snapshot counts: structure_event_bos ---",
        ]
    )
    snap_counts = stats.get("structure_event_snapshot_counts", {})
    lines.extend(
        _format_breakdown_lines(snap_counts.get("structure_event_bos", {}), show_pnl=False)
    )
    lines.extend(["", "--- Snapshot counts: structure_event_choch ---"])
    lines.extend(
        _format_breakdown_lines(snap_counts.get("structure_event_choch", {}), show_pnl=False)
    )
    lines.extend(["", "--- Snapshot counts: control_shift ---"])
    lines.extend(
        _format_breakdown_lines(snap_counts.get("control_shift", {}), show_pnl=False)
    )
    lines.extend(["", "--- Snapshot counts: buyers_take_control ---"])
    lines.extend(
        _format_breakdown_lines(snap_counts.get("buyers_take_control", {}), show_pnl=False)
    )
    lines.extend(["", "--- Snapshot counts: sellers_take_control ---"])
    lines.extend(
        _format_breakdown_lines(snap_counts.get("sellers_take_control", {}), show_pnl=False)
    )
    lines.extend(["", "--- Snapshot counts: structure_event_strength ---"])
    lines.extend(
        _format_breakdown_lines(
            snap_counts.get("structure_event_strength", {}), show_pnl=False
        )
    )

    cross_snap = stats.get("structure_event_cross_snapshot_counts", {})
    lines.extend(["", "--- Snapshot counts: setup_type + structure_event_choch ---"])
    lines.extend(
        _format_breakdown_lines(
            cross_snap.get("setup_type_structure_event_choch", {}), show_pnl=False
        )
    )
    lines.extend(["", "--- Snapshot counts: setup_type + structure_event_bos ---"])
    lines.extend(
        _format_breakdown_lines(
            cross_snap.get("setup_type_structure_event_bos", {}), show_pnl=False
        )
    )
    lines.extend(["", "--- Snapshot counts: setup_quality + structure_event_strength ---"])
    lines.extend(
        _format_breakdown_lines(
            cross_snap.get("setup_quality_structure_event_strength", {}),
            show_pnl=False,
        )
    )

    trade_perf = stats.get("structure_event_trade_performance", {})
    lines.extend(
        [
            "",
            "===== STRUCTURE EVENTS (closed paper trades @ entry snapshot) =====",
            "",
            f"Closed trades:                {stats.get('total_paper_trades', 0)}",
            "",
            "--- Trades: structure_event_bos ---",
        ]
    )
    lines.extend(
        _format_breakdown_lines(trade_perf.get("structure_event_bos", {}), show_pnl=True)
    )
    lines.extend(["", "--- Trades: structure_event_choch ---"])
    lines.extend(
        _format_breakdown_lines(trade_perf.get("structure_event_choch", {}), show_pnl=True)
    )
    lines.extend(["", "--- Trades: control_shift ---"])
    lines.extend(
        _format_breakdown_lines(trade_perf.get("control_shift", {}), show_pnl=True)
    )
    lines.extend(["", "--- Trades: buyers_take_control ---"])
    lines.extend(
        _format_breakdown_lines(trade_perf.get("buyers_take_control", {}), show_pnl=True)
    )
    lines.extend(["", "--- Trades: sellers_take_control ---"])
    lines.extend(
        _format_breakdown_lines(trade_perf.get("sellers_take_control", {}), show_pnl=True)
    )
    lines.extend(["", "--- Trades: structure_event_strength ---"])
    lines.extend(
        _format_breakdown_lines(
            trade_perf.get("structure_event_strength", {}), show_pnl=True
        )
    )

    cross_trade = stats.get("structure_event_cross_trade_performance", {})
    lines.extend(["", "--- Trades: setup_type + structure_event_choch ---"])
    lines.extend(
        _format_breakdown_lines(
            cross_trade.get("setup_type_structure_event_choch", {}), show_pnl=True
        )
    )
    lines.extend(["", "--- Trades: setup_type + structure_event_bos ---"])
    lines.extend(
        _format_breakdown_lines(
            cross_trade.get("setup_type_structure_event_bos", {}), show_pnl=True
        )
    )
    lines.extend(["", "--- Trades: setup_quality + structure_event_strength ---"])
    lines.extend(
        _format_breakdown_lines(
            cross_trade.get("setup_quality_structure_event_strength", {}),
            show_pnl=True,
        )
    )

    rev = stats.get("reversal_setups", {})
    trend = stats.get("trend_continuation_setups", {})
    pull = stats.get("pullback_setups", {})

    lines.extend(
        [
            "",
            "--- Key setup edges ---",
            f"  REVERSAL_ATTEMPT:     count={rev.get('count', 0):3}  "
            f"win_rate={rev.get('win_rate', 0):6}%  avg_pnl={rev.get('average_pnl', 0):+.4f}%",
            f"  TREND_CONTINUATION:   count={trend.get('count', 0):3}  "
            f"win_rate={trend.get('win_rate', 0):6}%  avg_pnl={trend.get('average_pnl', 0):+.4f}%",
            f"  PULLBACK_ENTRY:       count={pull.get('count', 0):3}  "
            f"win_rate={pull.get('win_rate', 0):6}%  avg_pnl={pull.get('average_pnl', 0):+.4f}%",
            "",
            "=======================",
        ]
    )
    return "\n".join(lines)
