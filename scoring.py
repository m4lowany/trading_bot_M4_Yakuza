def calculate_score(indicators):
    score = 0

    for name, value in indicators.items():
        if value == "BULLISH":
            score += 1

        elif value == "BEARISH":
            score -= 1

    return score
