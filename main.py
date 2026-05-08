import ccxt
import os
import time
from datetime import datetime
from config import (
    CONFIRM_TIMEFRAME,
    ENABLE_LOGS,
    ENTRY_TIMEFRAME,
    INDICATORS,
    LOOP_DELAY,
    SYMBOL,
    TREND_TIMEFRAME,
)
from indicators import get_all_indicators
from risk_manager import can_trade
from scoring import calculate_score
from signals import get_signal

exchange = ccxt.mexc()
log_dir = "logs"
log_file = os.path.join(log_dir, "market_log.txt")
signals_history_file = os.path.join(log_dir, "signals_history.txt")
trend_history_file = os.path.join(log_dir, "trend_history.txt")
os.makedirs(log_dir, exist_ok=True)
counter = 0

print(
    f"TIMEFRAMES: TREND={TREND_TIMEFRAME} | CONFIRM={CONFIRM_TIMEFRAME} | ENTRY={ENTRY_TIMEFRAME}"
)
print(f"INDICATORS: {', '.join(INDICATORS)}")

while True:
    try:
        counter += 1
        ticker = exchange.fetch_ticker(SYMBOL)
        price = ticker['last']
        indicator_status = get_all_indicators(None)
        score = calculate_score(indicator_status)
        signal = get_signal(score)
        trend = "WAIT"
        trend_tf_signal = "WAIT"
        confirm_tf_signal = "WAIT"
        entry_tf_signal = "WAIT"
        can_enter = can_trade(signal)
        trade_allowed = "YES" if can_enter else "NO"
        timestamp = datetime.now().isoformat()

        if not can_enter:
            pass

        print(
            f"[ITERATION {counter}] SYMBOL: {SYMBOL} | BTC PRICE: {price} | SIGNAL: {signal} | TREND: {trend} | TRADE_ALLOWED: {trade_allowed}"
        )
        print(
            f"TREND_TF: {trend_tf_signal} | CONFIRM_TF: {confirm_tf_signal} | ENTRY_TF: {entry_tf_signal}"
        )
        print(f"INDICATOR_STATUS: {indicator_status}")
        print(f"SCORE: {score}")
        if ENABLE_LOGS:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"{timestamp} | [ITERATION {counter}] SYMBOL: {SYMBOL} | BTC PRICE: {price} | SIGNAL: {signal} | TREND: {trend} | INDICATORS: {indicator_status}\n"
                )
            with open(signals_history_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | ITERATION {counter} | {signal}\n")
            with open(trend_history_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | ITERATION {counter} | {trend}\n")

        time.sleep(LOOP_DELAY)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
