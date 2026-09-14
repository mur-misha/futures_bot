"""UT Bot Alerts implementation, kept compatible with the original public API."""
from models import Direction, UTState


def compute_true_range(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    if not highs or len(highs) != len(lows) or len(lows) != len(closes):
        raise ValueError("highs/lows/closes must be non-empty and have equal length")
    tr = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return tr


def compute_atr_rma(tr: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period must be > 0")
    n = len(tr)
    if n < period:
        raise ValueError("not enough bars for ATR")
    atr = [0.0] * n
    atr[period - 1] = sum(tr[:period]) / period
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def compute_ut_bot_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    key_value: float = 1.0,
    atr_period: int = 10,
) -> tuple[list[float], list[int], list[float]] | None:
    """Full-history Chandelier trailing-stop computation.

    Returns (stop, pos, atr) arrays aligned to `closes`, or None if there
    isn't enough history. This is the single source of truth for the UT Bot
    stop/position logic — both `compute_ut_bot` (cold, stateless callers) and
    `engines.ut.UTEngine._seed` (warm, stateful runtime) must go through this
    instead of re-implementing the loop, so a future formula change can't
    silently diverge between the two call sites.
    """
    n = len(closes)
    if n < atr_period * 3 or len(highs) != n or len(lows) != n:
        return None
    if key_value <= 0 or atr_period <= 0:
        raise ValueError("key_value and atr_period must be > 0")

    tr = compute_true_range(highs, lows, closes)
    atr = compute_atr_rma(tr, atr_period)

    stop = [0.0] * n
    pos = [0] * n
    first = atr_period - 1
    stop[first] = closes[first] - key_value * atr[first] if closes[first] > 0 else closes[first] + key_value * atr[first]

    for i in range(first + 1, n):
        n_loss = key_value * atr[i]
        src = closes[i]
        prev_stop = stop[i - 1]
        prev_src = closes[i - 1]
        if src > prev_stop and prev_src > prev_stop:
            stop[i] = max(prev_stop, src - n_loss)
        elif src < prev_stop and prev_src < prev_stop:
            stop[i] = min(prev_stop, src + n_loss)
        else:
            stop[i] = src - n_loss if src > prev_stop else src + n_loss

        if prev_src < prev_stop and src > prev_stop:
            pos[i] = 1
        elif prev_src > prev_stop and src < prev_stop:
            pos[i] = -1
        else:
            pos[i] = pos[i - 1]

    # Bootstrap direction from the first meaningful bar instead of leaking a 0 state.
    if pos[first] == 0:
        pos[first] = 1 if closes[first] >= stop[first] else -1
        for i in range(first + 1, n):
            if pos[i] == 0:
                pos[i] = pos[i - 1]

    return stop, pos, atr


def compute_ut_bot(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    key_value: float = 1.0,
    atr_period: int = 10,
) -> UTState | None:
    series = compute_ut_bot_series(highs, lows, closes, key_value=key_value, atr_period=atr_period)
    if series is None:
        return None
    stop, pos, _atr = series

    cross_direction = None
    just_crossed = False
    if pos[-1] != pos[-2]:
        just_crossed = True
        cross_direction = Direction.UP if pos[-1] == 1 else Direction.DOWN

    return UTState(
        pos=pos[-1],
        trailing_stop=stop[-1],
        just_crossed=just_crossed,
        cross_direction=cross_direction,
    )


# Backward-compatible name from V1.
UTBotResult = UTState
