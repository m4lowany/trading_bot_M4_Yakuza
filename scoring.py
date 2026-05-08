def calculate_score(indicators):
    score = 0

    for name, value in indicators.items():
        if value in ("BUY", "BULLISH"):
            score += 1

        elif value in ("SELL", "BEARISH"):
            score -= 1

    return score
