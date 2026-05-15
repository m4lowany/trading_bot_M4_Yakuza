from typing import Any, Iterable, Sequence, Tuple


def require_timeframe(name: str, value: Any) -> str:
    """Return a non-empty timeframe string or raise ValueError."""
    if value is None:
        raise ValueError(
            f"{name} is not set in config.py (got None). "
            f'Example: {name} = "3m"'
        )
    if not isinstance(value, str):
        raise ValueError(
            f"{name} must be a string in config.py "
            f"(got {type(value).__name__}: {value!r})"
        )
    stripped = value.strip()
    if not stripped:
        raise ValueError(
            f"{name} is empty in config.py. "
            f'Set a valid exchange interval, e.g. {name} = "3m"'
        )
    return stripped


def validate_timeframes(
    trend_timeframe: Any,
    confirm_timeframe: Any,
    entry_timeframe: Any,
) -> Tuple[str, str, str]:
    """Validate all three MTF intervals from config."""
    return (
        require_timeframe("TREND_TIMEFRAME", trend_timeframe),
        require_timeframe("CONFIRM_TIMEFRAME", confirm_timeframe),
        require_timeframe("ENTRY_TIMEFRAME", entry_timeframe),
    )


def validate_candles(candles: Any, min_length: int = 1) -> bool:
    """
    Basic validation for OHLCV candles used across the bot.

    Returns True only if:
    - candles is a non-empty iterable
    - len(candles) >= min_length
    - no candle or its first 5 OHLCV fields is None
    """
    if not candles:
        return False

    try:
        length = len(candles)  # type: ignore[arg-type]
    except Exception:
        return False

    if length < min_length:
        return False

    for candle in candles:  # type: ignore[assignment]
        if candle is None:
            return False

        if not isinstance(candle, Sequence) or len(candle) < 5:
            return False

        o, h, l, c, v = candle[:5]
        if any(x is None for x in (o, h, l, c, v)):
            return False

    return True

