import json
import os
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_STOP_LOSS_PERCENT = 1.0
MIN_CONFIDENCE_TO_OPEN = 3
CLOSE_COOLDOWN_ITERATIONS = 3
MIXED_ALIGNMENT_CLOSE_ITERATIONS = 3
ALIGNMENT_MIXED_WARNING = "alignment mixed warning"


def _trades_path(log_dir: str) -> str:
    return os.path.join(log_dir, "paper_trades.json")


def _default_state() -> Dict[str, Any]:
    return {
        "active_trade": None,
        "history": [],
        "close_cooldown_remaining": 0,
    }


def load_paper_state(log_dir: str) -> Dict[str, Any]:
    path = _trades_path(log_dir)
    if not os.path.exists(path):
        return _default_state()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _default_state()
    if not isinstance(data, dict):
        return _default_state()
    data.setdefault("active_trade", None)
    data.setdefault("history", [])
    data.setdefault("close_cooldown_remaining", 0)
    return data


def save_paper_state(log_dir: str, state: Dict[str, Any]) -> None:
    os.makedirs(log_dir, exist_ok=True)
    path = _trades_path(log_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _calc_pnl_percent(side: str, entry_price: float, current_price: float) -> float:
    if entry_price <= 0:
        return 0.0
    move = ((current_price - entry_price) / entry_price) * 100
    if side == "SELL":
        move = -move
    return round(move, 4)


def _stop_loss_percent(target_profit_percent: float) -> float:
    if target_profit_percent > 0:
        return round(max(target_profit_percent * 0.5, 0.5), 2)
    return DEFAULT_STOP_LOSS_PERCENT


def can_open_paper_trade(
    *,
    signal: str,
    trade_allowed: bool,
    entry_quality: str,
    signal_confidence: int,
    has_active_trade: bool,
    close_cooldown_remaining: int = 0,
) -> bool:
    if has_active_trade:
        return False
    if close_cooldown_remaining > 0:
        return False
    if signal == "WAIT":
        return False
    if not trade_allowed:
        return False
    if entry_quality == "LOW":
        return False
    if signal_confidence < MIN_CONFIDENCE_TO_OPEN:
        return False
    return True


def open_paper_trade(
    *,
    side: str,
    entry_price: float,
    confidence: int,
    entry_quality: str,
    leverage: int,
    target_profit_percent: float,
    reason: str,
    timestamp: Optional[str] = None,
    stop_loss_percent: Optional[float] = None,
) -> Dict[str, Any]:
    ts = timestamp or datetime.now().isoformat()
    sl = stop_loss_percent if stop_loss_percent is not None else _stop_loss_percent(
        target_profit_percent
    )
    return {
        "side": side,
        "entry_price": entry_price,
        "current_price": entry_price,
        "confidence": confidence,
        "entry_quality": entry_quality,
        "leverage": leverage,
        "target_profit_percent": target_profit_percent,
        "stop_loss_percent": sl,
        "timestamp": ts,
        "reason": reason,
        "status": "OPEN",
        "mixed_alignment_streak": 0,
        "alignment_warning": None,
    }


def update_paper_trade(
    trade: Dict[str, Any],
    current_price: float,
) -> Dict[str, Any]:
    updated = deepcopy(trade)
    updated["current_price"] = current_price
    updated["unrealized_pnl_percent"] = _calc_pnl_percent(
        updated["side"], updated["entry_price"], current_price
    )
    return updated


def _tp_hit(trade: Dict[str, Any], current_price: float) -> bool:
    entry = trade["entry_price"]
    tp = trade["target_profit_percent"]
    if entry <= 0 or tp <= 0:
        return False
    pnl = _calc_pnl_percent(trade["side"], entry, current_price)
    return pnl >= tp


def _sl_hit(trade: Dict[str, Any], current_price: float) -> bool:
    entry = trade["entry_price"]
    sl = trade["stop_loss_percent"]
    if entry <= 0 or sl <= 0:
        return False
    pnl = _calc_pnl_percent(trade["side"], entry, current_price)
    return pnl <= -sl


def _opposite_signal(trade: Dict[str, Any], signal: str) -> bool:
    if trade["side"] == "BUY" and signal == "SELL":
        return True
    if trade["side"] == "SELL" and signal == "BUY":
        return True
    return False


def close_reason_for_trade(
    trade: Dict[str, Any],
    *,
    current_price: float,
    signal: str,
) -> Optional[str]:
    """Immediate close reasons only (TP / SL / opposite signal). MIXED handled separately."""
    if _tp_hit(trade, current_price):
        return "TP hit"
    if _sl_hit(trade, current_price):
        return "SL hit"
    if _opposite_signal(trade, signal):
        return "opposite signal"
    return None


def _update_mixed_alignment_state(
    trade: Dict[str, Any], tf_alignment: str
) -> Dict[str, Any]:
    updated = deepcopy(trade)
    streak = int(updated.get("mixed_alignment_streak", 0))

    if tf_alignment == "MIXED":
        streak += 1
        updated["mixed_alignment_streak"] = streak
        updated["alignment_warning"] = ALIGNMENT_MIXED_WARNING
    else:
        updated["mixed_alignment_streak"] = 0
        updated["alignment_warning"] = None

    return updated


def _mixed_alignment_close_reason(trade: Dict[str, Any]) -> Optional[str]:
    if int(trade.get("mixed_alignment_streak", 0)) >= MIXED_ALIGNMENT_CLOSE_ITERATIONS:
        return "alignment MIXED"
    return None


def close_paper_trade(
    trade: Dict[str, Any],
    exit_price: float,
    close_reason: str,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    closed = deepcopy(trade)
    closed["exit_price"] = exit_price
    closed["current_price"] = exit_price
    closed["close_reason"] = close_reason
    closed["closed_at"] = timestamp or datetime.now().isoformat()
    closed["status"] = "CLOSED"
    pnl = _calc_pnl_percent(closed["side"], closed["entry_price"], exit_price)
    closed["pnl_percent"] = pnl
    closed["pnl_percent_leveraged"] = round(
        pnl * max(int(closed.get("leverage", 1)), 1), 4
    )
    return closed


def _start_close_cooldown(state: Dict[str, Any]) -> None:
    state["close_cooldown_remaining"] = CLOSE_COOLDOWN_ITERATIONS


def _tick_close_cooldown(state: Dict[str, Any]) -> None:
    remaining = int(state.get("close_cooldown_remaining", 0))
    if remaining > 0:
        state["close_cooldown_remaining"] = remaining - 1


def format_paper_log(event: str, trade: Dict[str, Any], extra: str = "") -> str:
    parts = [
        event,
        f"side={trade.get('side')}",
        f"entry={trade.get('entry_price')}",
        f"current={trade.get('current_price')}",
        f"confidence={trade.get('confidence')}",
        f"entry_quality={trade.get('entry_quality')}",
        f"leverage={trade.get('leverage')}",
        f"tp%={trade.get('target_profit_percent')}",
        f"sl%={trade.get('stop_loss_percent')}",
        f"reason={trade.get('reason')}",
    ]
    if trade.get("close_reason"):
        parts.append(f"close_reason={trade['close_reason']}")
    if trade.get("alignment_warning"):
        parts.append(f"warning={trade['alignment_warning']}")
    if trade.get("mixed_alignment_streak"):
        parts.append(f"mixed_streak={trade['mixed_alignment_streak']}")
    if "pnl_percent" in trade:
        parts.append(f"pnl%={trade['pnl_percent']}")
    if extra:
        parts.append(extra)
    return " | ".join(parts)


def process_paper_trading(
    log_dir: str,
    *,
    current_price: float,
    signal: str,
    trade_allowed: bool,
    signal_confidence: int,
    entry_quality: str,
    tf_alignment: str,
    leverage: int,
    target_profit_percent: float,
    reason: str,
    timestamp: Optional[str] = None,
) -> List[str]:
    """
    Jedna iteracja paper tradingu: update / close / open.
    Zwraca listę linii do wydruku (PAPER_TRADE_OPEN, PAPER_TRADE_CLOSE, PAPER_PNL_PERCENT).
    """
    ts = timestamp or datetime.now().isoformat()
    state = load_paper_state(log_dir)
    logs: List[str] = []
    active = state.get("active_trade")
    cooldown = int(state.get("close_cooldown_remaining", 0))
    closed_this_iteration = False

    if active is not None:
        active = update_paper_trade(active, current_price)
        close_reason = close_reason_for_trade(
            active,
            current_price=current_price,
            signal=signal,
        )

        if close_reason is None:
            active = _update_mixed_alignment_state(active, tf_alignment)
            close_reason = _mixed_alignment_close_reason(active)
            if active.get("alignment_warning") and close_reason is None:
                logs.append(
                    format_paper_log(
                        "PAPER_ALIGNMENT_WARNING",
                        active,
                        extra=(
                            f"streak={active.get('mixed_alignment_streak', 0)}"
                            f"/{MIXED_ALIGNMENT_CLOSE_ITERATIONS}"
                        ),
                    )
                )

        if close_reason:
            closed = close_paper_trade(
                active, current_price, close_reason, timestamp=ts
            )
            state["history"].append(closed)
            state["active_trade"] = None
            _start_close_cooldown(state)
            closed_this_iteration = True
            logs.append(format_paper_log("PAPER_TRADE_CLOSE", closed))
            logs.append(
                f"PAPER_PNL_PERCENT: {closed['pnl_percent']} "
                f"(leveraged: {closed['pnl_percent_leveraged']})"
            )
        else:
            state["active_trade"] = active
            logs.append(
                f"PAPER_PNL_PERCENT: {active['unrealized_pnl_percent']} (unrealized)"
            )

    cooldown = int(state.get("close_cooldown_remaining", 0))

    if state.get("active_trade") is None and can_open_paper_trade(
        signal=signal,
        trade_allowed=trade_allowed,
        entry_quality=entry_quality,
        signal_confidence=signal_confidence,
        has_active_trade=False,
        close_cooldown_remaining=cooldown,
    ):
        new_trade = open_paper_trade(
            side=signal,
            entry_price=current_price,
            confidence=signal_confidence,
            entry_quality=entry_quality,
            leverage=leverage,
            target_profit_percent=target_profit_percent,
            reason=reason,
            timestamp=ts,
        )
        state["active_trade"] = new_trade
        logs.append(format_paper_log("PAPER_TRADE_OPEN", new_trade))
    elif state.get("active_trade") is None and cooldown > 0:
        logs.append(f"PAPER_COOLDOWN: {cooldown} iteration(s) remaining after close")

    if not closed_this_iteration:
        _tick_close_cooldown(state)
    save_paper_state(log_dir, state)
    return logs
