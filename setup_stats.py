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
) -> None:
    """
    Append one JSON snapshot per line to logs/setup_history.jsonl.
    By default logs every iteration; set only_when_paper_signal=True to skip WAIT paper rows.

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

    record = {
        "timestamp": timestamp,
        "symbol": symbol,
        "price": price,
        "signal": signal,
        "paper_signal": paper_signal,
        "paper_trade_allowed": paper_trade_allowed,
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


def _enrich_trade(trade: Dict[str, Any], snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    enriched = dict(trade)
    snap = _match_snapshot_for_trade(trade, snapshots)
    if snap:
        enriched["setup_type"] = snap.get("setup_type", "UNKNOWN")
        enriched["setup_quality"] = snap.get("setup_quality", "UNKNOWN")
        enriched["tf_alignment"] = snap.get("tf_alignment", "UNKNOWN")
    else:
        from_reason = _setup_type_from_reason(str(trade.get("reason", "")))
        enriched["setup_type"] = from_reason or "UNKNOWN"
        enriched["setup_quality"] = trade.get("entry_quality", "UNKNOWN")
        enriched["tf_alignment"] = "UNKNOWN"
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


def _breakdown(trades: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        label = str(trade.get(key, "UNKNOWN"))
        groups[label].append(trade)

    result: Dict[str, Dict[str, Any]] = {}
    for label, group in sorted(groups.items()):
        pnls = [float(t.get("pnl_percent", 0)) for t in group]
        result[label] = {
            "count": len(group),
            "win_rate": _win_rate(group),
            "average_pnl": _avg(pnls),
        }
    return result


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
    }


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

    breakdown = stats.get("setup_type_breakdown", {})
    if not breakdown:
        lines.append("  (no closed trades yet)")
    else:
        for label, row in breakdown.items():
            lines.append(
                f"  {label:22} count={row['count']:3}  "
                f"win_rate={row['win_rate']:6}%  avg_pnl={row['average_pnl']:+.4f}%"
            )

    lines.extend(
        [
            "",
            "--- By setup_quality ---",
        ]
    )
    for label, row in stats.get("breakdown_by_setup_quality", {}).items():
        lines.append(
            f"  {label:10} count={row['count']:3}  "
            f"win_rate={row['win_rate']:6}%  avg_pnl={row['average_pnl']:+.4f}%"
        )
    if not stats.get("breakdown_by_setup_quality"):
        lines.append("  (no data)")

    lines.extend(["", "--- By entry_quality ---"])
    for label, row in stats.get("breakdown_by_entry_quality", {}).items():
        lines.append(
            f"  {label:10} count={row['count']:3}  "
            f"win_rate={row['win_rate']:6}%  avg_pnl={row['average_pnl']:+.4f}%"
        )
    if not stats.get("breakdown_by_entry_quality"):
        lines.append("  (no data)")

    lines.extend(["", "--- By tf_alignment ---"])
    for label, row in stats.get("breakdown_by_tf_alignment", {}).items():
        lines.append(
            f"  {label:16} count={row['count']:3}  "
            f"win_rate={row['win_rate']:6}%  avg_pnl={row['average_pnl']:+.4f}%"
        )
    if not stats.get("breakdown_by_tf_alignment"):
        lines.append("  (no data)")

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
