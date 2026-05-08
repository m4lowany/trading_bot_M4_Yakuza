def get_ma60(data):
    return "WAIT"


def get_ema238(data):
    return "WAIT"


def get_rsi(data):
    return "WAIT"


def get_fvg(data):
    return "WAIT"


def get_bag(data):
    return "WAIT"


def get_fibo(data):
    return "WAIT"


def get_all_indicators(data):
    return {
        "MA60": get_ma60(data),
        "EMA238": get_ema238(data),
        "RSI": get_rsi(data),
        "FVG": get_fvg(data),
        "BAG": get_bag(data),
        "FIBO": get_fibo(data),
    }
