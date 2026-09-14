from dataclasses import dataclass

from models import Candle, Direction


@dataclass(frozen=True)
class FibLevels:
    swing_high: float
    swing_low: float
    level_382: float
    level_500: float
    level_618: float


def compute_fib_levels(candle: Candle, history: tuple[Candle, ...], direction: Direction) -> FibLevels | None:
    """Fibonacci retracement of the recent swing, used to suggest a pullback
    entry rather than chasing the climax candle that triggered the alert.

    For an UP signal: swing_low..swing_high is the recent up-leg, and the
    retracement levels sit BELOW the current price (buy-the-dip zone).
    For a DOWN signal: mirrored — levels sit ABOVE the current price.
    """
    bars = list(history) + [candle]
    swing_high = max(c.high for c in bars)
    swing_low = min(c.low for c in bars)
    rng = swing_high - swing_low
    if rng <= 0:
        return None

    # Retracement measured back from the extreme in the direction of the move:
    # UP  -> from swing_high back down toward swing_low (buy-the-dip zone)
    # DOWN -> from swing_low back up toward swing_high (sell-the-bounce zone)
    ref = swing_high if direction is Direction.UP else swing_low
    sign = -1 if direction is Direction.UP else 1

    return FibLevels(
        swing_high=swing_high,
        swing_low=swing_low,
        level_382=ref + sign * 0.382 * rng,
        level_500=ref + sign * 0.5 * rng,
        level_618=ref + sign * 0.618 * rng,
    )
