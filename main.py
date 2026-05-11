import ccxt
import os
import traceback
import time
from datetime import datetime
from config import (
    CONFIRM_TIMEFRAME,
    DEBUG_MODE,
    ENABLE_LOGS,
    ENTRY_TIMEFRAME,
    INDICATORS,
    LOOP_DELAY,
    OHLCV_LIMIT,
    SYMBOL,
    TREND_TIMEFRAME,
)
from indicators import get_all_indicators
from market_structure import analyze_market_structure
from price_action import analyze_candles
from risk_manager import calculate_dynamic_leverage, can_trade
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
        candles = exchange.fetch_ohlcv(SYMBOL, timeframe=TREND_TIMEFRAME, limit=OHLCV_LIMIT)
        price = ticker["last"]
        structure_data = analyze_market_structure(candles)
        price_action_data = analyze_candles(candles)
        indicator_status = get_all_indicators(None)
        score = calculate_score(indicator_status)
        signal = get_signal(score)
        signal_confidence = max(0, min(5, abs(score)))
        trend = "WAIT"
        trend_tf_signal = "WAIT"
        confirm_tf_signal = "WAIT"
        entry_tf_signal = "WAIT"
        can_enter = can_trade(signal)
        risk_level = "MEDIUM"
        reason = "normal conditions"

        recent_high = max(c[2] for c in candles[-10:])
        recent_low = min(c[3] for c in candles[-10:])
        move_percent = 0.0
        if recent_low > 0:
            move_percent = ((recent_high - recent_low) / recent_low) * 100

        if structure_data["liquidity_event"]:
            trade_allowed = False
            risk_level = "HIGH"
            reason = "market breakdown / liquidity event"
        else:
            if structure_data["momentum"] == "STRONG" and structure_data["structure"] != "SIDEWAYS":
                risk_level = "LOW"
            trade_allowed = can_enter

        if price_action_data["fake_breakout"]:
            signal_confidence = max(0, signal_confidence - 1)
            if risk_level == "LOW":
                risk_level = "MEDIUM"
            reason = f"{reason} + fake breakout risk"

        dynamic_risk = calculate_dynamic_leverage(
            move_percent,
            risk_level,
            signal=signal,
            trade_allowed=trade_allowed,
        )
        if dynamic_risk["reason"] == "no trade / wait signal":
            reason = dynamic_risk["reason"]
        trade_allowed_label = "YES" if trade_allowed else "NO"
        timestamp = datetime.now().isoformat()

        if not can_enter:
            pass

        print(
            f"[ITERATION {counter}] SYMBOL: {SYMBOL} | BTC PRICE: {price} | SIGNAL: {signal} | TREND: {trend} | TRADE_ALLOWED: {trade_allowed_label}"
        )
        print(
            f"TREND_TF: {trend_tf_signal} | CONFIRM_TF: {confirm_tf_signal} | ENTRY_TF: {entry_tf_signal}"
        )
        print(f"INDICATOR_STATUS: {indicator_status}")
        print(f"SCORE: {score}")
        print(f"SIGNAL_CONFIDENCE: {signal_confidence}/5")
        print(
            f"MARKET_STRUCTURE: {structure_data['structure']} | REVERSAL_CHANCE: {structure_data['reversal_chance']} | LIQUIDITY_EVENT: {structure_data['liquidity_event']} | MOMENTUM: {structure_data['momentum']}"
        )
        print(
            f"CANDLE_STRENGTH: {price_action_data['candle_strength']} | WICK_REJECTION: {price_action_data['wick_rejection']} | FAKE_BREAKOUT: {price_action_data['fake_breakout']} | SUPPORT_REACTION: {price_action_data['support_reaction']} | RESISTANCE_REACTION: {price_action_data['resistance_reaction']} | MOMENTUM_SHIFT: {price_action_data['momentum_shift']}"
        )
        print(
            f"RISK_LEVEL: {risk_level} | REASON: {reason} | RECOMMENDED_LEVERAGE: {dynamic_risk['recommended_leverage']} | TARGET_PROFIT_PERCENT: {dynamic_risk['target_profit_percent']}"
        )
        if ENABLE_LOGS:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"{timestamp} | [ITERATION {counter}] SYMBOL: {SYMBOL} | BTC PRICE: {price} | SIGNAL: {signal} | SIGNAL_CONFIDENCE: {signal_confidence}/5 | TREND: {trend} | MARKET_STRUCTURE: {structure_data['structure']} | REVERSAL_CHANCE: {structure_data['reversal_chance']} | LIQUIDITY_EVENT: {structure_data['liquidity_event']} | MOMENTUM: {structure_data['momentum']} | CANDLE_STRENGTH: {price_action_data['candle_strength']} | WICK_REJECTION: {price_action_data['wick_rejection']} | FAKE_BREAKOUT: {price_action_data['fake_breakout']} | SUPPORT_REACTION: {price_action_data['support_reaction']} | RESISTANCE_REACTION: {price_action_data['resistance_reaction']} | MOMENTUM_SHIFT: {price_action_data['momentum_shift']} | RISK_LEVEL: {risk_level} | REASON: {reason} | LEVERAGE: {dynamic_risk['recommended_leverage']} | TARGET_PROFIT_PERCENT: {dynamic_risk['target_profit_percent']} | INDICATORS: {indicator_status}\n"
                )
            with open(signals_history_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | ITERATION {counter} | {signal}\n")
            with open(trend_history_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | ITERATION {counter} | {trend}\n")

        time.sleep(LOOP_DELAY)

    except Exception as e:
        if DEBUG_MODE:
            print("ERROR:", e)
            traceback.print_exc()
        else:
            print("ERROR: market fetch failed")
        time.sleep(5)
