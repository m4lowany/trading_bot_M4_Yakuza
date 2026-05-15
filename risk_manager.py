def can_trade(signal):
    if signal == "WAIT":
        return False

    return True


def calculate_dynamic_leverage(move_percent, risk_level, signal=None, trade_allowed=True):
    if signal == "WAIT":
        return {
            "recommended_leverage": 0,
            "target_profit_percent": 0,
            "reason": "no trade / wait signal",
        }

    if not trade_allowed:
        return {
            "recommended_leverage": 0,
            "target_profit_percent": 0,
            "reason": "trade not allowed",
        }

    abs_move = abs(move_percent)

    if abs_move >= 8:
        base_leverage = 2
    elif abs_move >= 5:
        base_leverage = 3
    elif abs_move >= 3:
        base_leverage = 5
    elif abs_move >= 1.5:
        base_leverage = 8
    else:
        base_leverage = 12

    risk_adjustment = {
        "HIGH": -3,
        "MEDIUM": 0,
        "LOW": 2,
    }
    adjusted_leverage = base_leverage + risk_adjustment.get(risk_level, 0)
    recommended_leverage = max(1, min(20, int(adjusted_leverage)))
    target_profit_percent = round(max(abs_move * 0.25, 0.25), 2)

    return {
        "recommended_leverage": recommended_leverage,
        "target_profit_percent": target_profit_percent,
        "reason": "dynamic risk by volatility and risk level",
    }
