def get_signal(score):
    if score >= 3:
        return "BUY"
    if score <= -3:
        return "SELL"
    return "WAIT"
