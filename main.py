import ccxt
import os
import traceback
import time
from datetime import datetime
from config import (
    CONFIRM_TIMEFRAME as CONFIRM_TIMEFRAME_CONFIG,
    DEBUG_MODE,
    ENABLE_LOGS,
    ENTRY_TIMEFRAME as ENTRY_TIMEFRAME_CONFIG,
    INDICATORS,
    LOOP_DELAY,
    OHLCV_LIMIT,
    SYMBOL,
    TREND_TIMEFRAME as TREND_TIMEFRAME_CONFIG,
)
from price_action import analyze_candles
from risk_manager import calculate_dynamic_leverage, can_trade
from scoring import calculate_confidence, calculate_score
from signals import get_signal
from timeframe_analysis import (
    analyze_timeframe,
    analyze_timeframe_alignment,
    apply_alignment_final_filter,
    apply_alignment_to_confidence,
)
from paper_trader import process_paper_trading
from setup_engine import detect_setup, resolve_paper_from_setup
from setup_stats import save_setup_snapshot
from structure_events import analyze_structure_events
from training_data import build_entry_training_context
from utils import validate_candles, validate_timeframes

TREND_TIMEFRAME, CONFIRM_TIMEFRAME, ENTRY_TIMEFRAME = validate_timeframes(
    TREND_TIMEFRAME_CONFIG,
    CONFIRM_TIMEFRAME_CONFIG,
    ENTRY_TIMEFRAME_CONFIG,
)

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

if DEBUG_MODE:
    print(f"TREND_TIMEFRAME={TREND_TIMEFRAME}")
    print(f"CONFIRM_TIMEFRAME={CONFIRM_TIMEFRAME}")
    print(f"ENTRY_TIMEFRAME={ENTRY_TIMEFRAME}")

while True:
    try:
        counter += 1
        trend_interval, confirm_interval, entry_interval = validate_timeframes(
            TREND_TIMEFRAME,
            CONFIRM_TIMEFRAME,
            ENTRY_TIMEFRAME,
        )

        if DEBUG_MODE:
            print(f"TREND_TIMEFRAME={trend_interval}")
            print(f"CONFIRM_TIMEFRAME={confirm_interval}")
            print(f"ENTRY_TIMEFRAME={entry_interval}")

        ticker = exchange.fetch_ticker(SYMBOL)
        trend_candles = exchange.fetch_ohlcv(
            SYMBOL, timeframe=trend_interval, limit=OHLCV_LIMIT
        )
        confirm_candles = exchange.fetch_ohlcv(
            SYMBOL, timeframe=confirm_interval, limit=OHLCV_LIMIT
        )
        entry_candles = exchange.fetch_ohlcv(
            SYMBOL, timeframe=entry_interval, limit=OHLCV_LIMIT
        )

        if DEBUG_MODE:
            print(
                f"CANDLES_SOURCE: TREND={trend_interval} | "
                f"CONFIRM={confirm_interval} | ENTRY={entry_interval}"
            )

        if not all(
            validate_candles(c)
            for c in (trend_candles, confirm_candles, entry_candles)
        ):
            if DEBUG_MODE:
                print("INVALID CANDLES: skipping iteration")
            time.sleep(LOOP_DELAY)
            continue

        price = ticker["last"]

        trend_tf = analyze_timeframe(trend_candles)
        confirm_tf = analyze_timeframe(confirm_candles)
        entry_tf = analyze_timeframe(entry_candles)

        trend_tf_signal = trend_tf["signal"]
        confirm_tf_signal = confirm_tf["signal"]
        entry_tf_signal = entry_tf["signal"]

        alignment_data = analyze_timeframe_alignment(
            trend_tf_signal,
            confirm_tf_signal,
            entry_tf_signal,
            trend_structure_strength=trend_tf["structure_data"]["structure_strength"],
            confirm_structure_strength=confirm_tf["structure_data"]["structure_strength"],
            entry_structure_strength=entry_tf["structure_data"]["structure_strength"],
        )
        tf_alignment = alignment_data["alignment"]
        alignment_strength = alignment_data["alignment_strength"]

        candles = entry_candles
        structure_data = entry_tf["structure_data"]
        price_action_data = analyze_candles(candles)
        indicator_status = entry_tf["indicator_status"]
        fvg_data = indicator_status.get(
            "FVG",
            {
                "fvg_signal": "WAIT",
                "fvg_type": "NONE",
                "gap_size_percent": 0.0,
                "fvg_touched": False,
                "rejection_after_touch": False,
            },
        )
        fibo_data = indicator_status.get(
            "FIBO",
            {
                "fibo_signal": "WAIT",
                "fibo_direction": "NEUTRAL",
                "fibo_zone": "NONE",
                "retracement": 0.0,
            },
        )
        score = calculate_score(indicator_status)
        if fvg_data["fvg_type"] == "BULLISH" and fvg_data["rejection_after_touch"]:
            score += 1
        elif fvg_data["fvg_type"] == "BEARISH" and fvg_data["rejection_after_touch"]:
            score -= 1
        if (
            structure_data["structure"] == "BULLISH"
            and structure_data["structure_strength"] == "STRONG"
            and structure_data["momentum"] == "STRONG"
        ):
            score += 1
        elif (
            structure_data["structure"] == "BEARISH"
            and structure_data["structure_strength"] == "STRONG"
            and structure_data["momentum"] == "STRONG"
        ):
            score -= 1
        signal = get_signal(score)
        confidence_data = calculate_confidence(
            score,
            signal,
            structure_data,
            price_action_data,
            fvg_data,
            fibo_data,
        )
        confidence_data = apply_alignment_to_confidence(
            confidence_data,
            alignment_data,
            signal,
            structure_data,
            fake_breakout=price_action_data["fake_breakout"],
            liquidity_event=structure_data["liquidity_event"],
        )
        final_filter = apply_alignment_final_filter(
            signal, confidence_data, alignment_data
        )
        signal = final_filter["signal"]
        confidence_data = final_filter["confidence_data"]
        alignment_allows_trade = final_filter["trade_allowed"]
        signal_confidence = confidence_data["confidence"]
        entry_quality = confidence_data["entry_quality"]
        confidence_reasons = confidence_data["confidence_reasons"]

        if tf_alignment == "FULL_BULLISH":
            trend = "BULLISH"
        elif tf_alignment == "FULL_BEARISH":
            trend = "BEARISH"
        else:
            trend = "MIXED"

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
            reason = "liquidity event / market breakdown"
        else:
            if structure_data["momentum"] == "STRONG" and structure_data["structure"] != "SIDEWAYS":
                risk_level = "LOW"
            trade_allowed = can_enter and alignment_allows_trade

        if price_action_data["fake_breakout"]:
            if risk_level == "LOW":
                risk_level = "MEDIUM"
            reason = f"{reason} + fake breakout risk"

        structure_events = analyze_structure_events(confirm_candles)

        setup_data = detect_setup(
            trend_tf,
            confirm_tf,
            entry_tf,
            price_action_data,
            fvg_data,
            structure_events=structure_events,
        )
        setup_type = setup_data["setup_type"]
        setup_direction = setup_data["setup_direction"]
        setup_quality = setup_data["setup_quality"]
        setup_reasons = setup_data["setup_reasons"]

        paper_ctx = resolve_paper_from_setup(
            signal=signal,
            trade_allowed=trade_allowed,
            entry_quality=entry_quality,
            signal_confidence=signal_confidence,
            setup=setup_data,
            liquidity_event=structure_data["liquidity_event"],
        )
        paper_signal = paper_ctx["paper_signal"]
        paper_trade_allowed = paper_ctx["paper_trade_allowed"]
        paper_entry_quality = paper_ctx["paper_entry_quality"]
        paper_confidence = paper_ctx["paper_confidence"]
        paper_source = paper_ctx["paper_source"]

        dynamic_risk = calculate_dynamic_leverage(
            move_percent,
            risk_level,
            signal=paper_signal,
            trade_allowed=paper_trade_allowed,
        )
        if dynamic_risk["reason"] == "no trade / wait signal" and not structure_data["liquidity_event"]:
            reason = dynamic_risk["reason"]
        trade_allowed_label = "YES" if trade_allowed else "NO"
        timestamp = datetime.now().isoformat()

        if not can_enter:
            pass

        print(
            f"[ITERATION {counter}] SYMBOL: {SYMBOL} | BTC PRICE: {price} | SIGNAL: {signal} | TREND: {trend} | TRADE_ALLOWED: {trade_allowed_label}"
        )
        print(f"TREND_TF_SIGNAL: {trend_tf_signal}")
        print(f"CONFIRM_TF_SIGNAL: {confirm_tf_signal}")
        print(f"ENTRY_TF_SIGNAL: {entry_tf_signal}")
        print(f"TF_ALIGNMENT: {tf_alignment}")
        print(f"ALIGNMENT_STRENGTH: {alignment_strength}")
        print(f"INDICATOR_STATUS: {indicator_status}")
        print(f"SCORE: {score}")
        print(f"SIGNAL_CONFIDENCE: {signal_confidence}/5")
        print(f"ENTRY_QUALITY: {entry_quality}")
        print(f"CONFIDENCE_REASONS: {confidence_reasons}")
        print(
            f"MARKET_STRUCTURE: {structure_data['structure']} | REVERSAL_CHANCE: {structure_data['reversal_chance']} | LIQUIDITY_EVENT: {structure_data['liquidity_event']} | MOMENTUM: {structure_data['momentum']}"
        )
        print(
            f"STRUCTURE_STRENGTH: {structure_data['structure_strength']} | TREND_CONTINUATION_CHANCE: {structure_data['trend_continuation_chance']}"
        )
        print(
            f"CANDLE_STRENGTH: {price_action_data['candle_strength']} | WICK_REJECTION: {price_action_data['wick_rejection']} | FAKE_BREAKOUT: {price_action_data['fake_breakout']} | SUPPORT_REACTION: {price_action_data['support_reaction']} | RESISTANCE_REACTION: {price_action_data['resistance_reaction']} | MOMENTUM_SHIFT: {price_action_data['momentum_shift']}"
        )
        print(
            f"FVG_TYPE: {fvg_data['fvg_type']} | GAP_SIZE_PERCENT: {fvg_data['gap_size_percent']} | FVG_TOUCHED: {fvg_data['fvg_touched']} | REJECTION_AFTER_TOUCH: {fvg_data['rejection_after_touch']}"
        )
        print(
            f"RISK_LEVEL: {risk_level} | REASON: {reason} | RECOMMENDED_LEVERAGE: {dynamic_risk['recommended_leverage']} | TARGET_PROFIT_PERCENT: {dynamic_risk['target_profit_percent']}"
        )
        print(f"SETUP_TYPE: {setup_type}")
        print(f"SETUP_DIRECTION: {setup_direction}")
        print(f"SETUP_QUALITY: {setup_quality}")
        print(f"SETUP_REASONS: {setup_reasons}")
        print(
            f"PAPER_SOURCE: {paper_source} | PAPER_SIGNAL: {paper_signal} | "
            f"PAPER_TRADE_ALLOWED: {'YES' if paper_trade_allowed else 'NO'} | "
            f"PAPER_ENTRY_QUALITY: {paper_entry_quality} | PAPER_CONFIDENCE: {paper_confidence}/5"
        )

        paper_reason = reason
        if paper_source != "signal":
            paper_reason = f"{reason} | {paper_source}"

        # Observation-only open-time feature capture for training samples.
        training_context = build_entry_training_context(
            symbol=SYMBOL,
            score=score,
            signal=signal,
            signal_confidence=signal_confidence,
            entry_quality=entry_quality,
            tf_alignment=tf_alignment,
            alignment_strength=alignment_strength,
            setup_type=setup_type,
            setup_direction=setup_direction,
            setup_quality=setup_quality,
            setup_reasons=setup_reasons,
            paper_source=paper_source,
            paper_confidence=paper_confidence,
            paper_entry_quality=paper_entry_quality,
            structure_data=structure_data,
            price_action_data=price_action_data,
            fvg_data=fvg_data,
            indicator_status=indicator_status,
            structure_events=structure_events,
            risk_level=risk_level,
            trend_timeframe=TREND_TIMEFRAME,
            confirm_timeframe=CONFIRM_TIMEFRAME,
            entry_timeframe=ENTRY_TIMEFRAME,
        )

        paper_logs = process_paper_trading(
            log_dir,
            current_price=price,
            signal=paper_signal,
            trade_allowed=paper_trade_allowed,
            signal_confidence=paper_confidence,
            entry_quality=paper_entry_quality,
            tf_alignment=tf_alignment,
            leverage=dynamic_risk["recommended_leverage"],
            target_profit_percent=dynamic_risk["target_profit_percent"],
            reason=paper_reason,
            timestamp=timestamp,
            training_context=training_context,
        )
        for line in paper_logs:
            print(line)

        print(f"STRUCTURE_EVENT_BOS: {structure_events['bos']}")
        print(f"STRUCTURE_EVENT_CHOCH: {structure_events['choch']}")
        print(f"CONTROL_SHIFT: {structure_events['control_shift']}")
        print(f"BUYERS_TAKE_CONTROL: {structure_events['buyers_take_control']}")
        print(f"SELLERS_TAKE_CONTROL: {structure_events['sellers_take_control']}")
        print(f"STRUCTURE_EVENT_STRENGTH: {structure_events['event_strength']}")
        print(f"STRUCTURE_EVENT_REASONS: {structure_events['event_reasons']}")

        save_setup_snapshot(
            log_dir,
            timestamp=timestamp,
            symbol=SYMBOL,
            price=price,
            signal=signal,
            paper_signal=paper_signal,
            paper_trade_allowed=paper_trade_allowed,
            paper_confidence=paper_confidence,
            paper_entry_quality=paper_entry_quality,
            paper_source=paper_source,
            setup_type=setup_type,
            setup_direction=setup_direction,
            setup_quality=setup_quality,
            signal_confidence=signal_confidence,
            entry_quality=entry_quality,
            tf_alignment=tf_alignment,
            alignment_strength=alignment_strength,
            market_structure=structure_data["structure"],
            structure_strength=structure_data["structure_strength"],
            momentum=structure_data["momentum"],
            risk_level=risk_level,
            recommended_leverage=dynamic_risk["recommended_leverage"],
            target_profit_percent=dynamic_risk["target_profit_percent"],
            fvg_type=fvg_data["fvg_type"],
            fvg_touched=fvg_data["fvg_touched"],
            rejection_after_touch=fvg_data["rejection_after_touch"],
            candle_strength=price_action_data["candle_strength"],
            wick_rejection=price_action_data["wick_rejection"],
            fake_breakout=price_action_data["fake_breakout"],
            support_reaction=price_action_data["support_reaction"],
            resistance_reaction=price_action_data["resistance_reaction"],
            momentum_shift=price_action_data["momentum_shift"],
            setup_reasons=setup_reasons,
            confidence_reasons=confidence_reasons,
            structure_events=structure_events,
        )

        if ENABLE_LOGS:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(
                    f"{timestamp} | [ITERATION {counter}] SYMBOL: {SYMBOL} | BTC PRICE: {price} | SIGNAL: {signal} | SIGNAL_CONFIDENCE: {signal_confidence}/5 | ENTRY_QUALITY: {entry_quality} | CONFIDENCE_REASONS: {confidence_reasons} | SETUP_TYPE: {setup_type} | SETUP_DIRECTION: {setup_direction} | SETUP_QUALITY: {setup_quality} | SETUP_REASONS: {setup_reasons} | PAPER_SOURCE: {paper_source} | PAPER_SIGNAL: {paper_signal} | PAPER_TRADE_ALLOWED: {'YES' if paper_trade_allowed else 'NO'} | TREND: {trend} | TREND_TF_SIGNAL: {trend_tf_signal} | CONFIRM_TF_SIGNAL: {confirm_tf_signal} | ENTRY_TF_SIGNAL: {entry_tf_signal} | TF_ALIGNMENT: {tf_alignment} | ALIGNMENT_STRENGTH: {alignment_strength} | MARKET_STRUCTURE: {structure_data['structure']} | STRUCTURE_STRENGTH: {structure_data['structure_strength']} | TREND_CONTINUATION_CHANCE: {structure_data['trend_continuation_chance']} | REVERSAL_CHANCE: {structure_data['reversal_chance']} | LIQUIDITY_EVENT: {structure_data['liquidity_event']} | MOMENTUM: {structure_data['momentum']} | CANDLE_STRENGTH: {price_action_data['candle_strength']} | WICK_REJECTION: {price_action_data['wick_rejection']} | FAKE_BREAKOUT: {price_action_data['fake_breakout']} | SUPPORT_REACTION: {price_action_data['support_reaction']} | RESISTANCE_REACTION: {price_action_data['resistance_reaction']} | MOMENTUM_SHIFT: {price_action_data['momentum_shift']} | FVG_TYPE: {fvg_data['fvg_type']} | GAP_SIZE_PERCENT: {fvg_data['gap_size_percent']} | FVG_TOUCHED: {fvg_data['fvg_touched']} | REJECTION_AFTER_TOUCH: {fvg_data['rejection_after_touch']} | RISK_LEVEL: {risk_level} | REASON: {reason} | LEVERAGE: {dynamic_risk['recommended_leverage']} | TARGET_PROFIT_PERCENT: {dynamic_risk['target_profit_percent']} | DATA_FLOW: MTF | INDICATORS: {indicator_status}\n"
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
