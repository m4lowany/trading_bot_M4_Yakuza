from typing import Iterable, Sequence, Any


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

