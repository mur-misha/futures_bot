from config import Settings
from models import Direction, OIResult, OIState


def classify_oi(price_change_pct: float, oi_change_pct: float, threshold: float) -> OIState:
    if oi_change_pct >= threshold:
        return OIState.LONG_BUILDUP if price_change_pct > 0 else OIState.SHORT_BUILDUP
    if oi_change_pct <= -threshold:
        return OIState.SHORT_COVERING if price_change_pct > 0 else OIState.LONG_LIQUIDATION
    return OIState.NEUTRAL


def calc_oi_change_pct(oi_hist: list[dict], candle_close_time: int, interval_ms: int) -> float | None:
    """Use two OI samples at/before the candle close, aligned by timestamp."""
    if not oi_hist:
        return None
    samples = []
    for item in oi_hist:
        try:
            ts = int(item["timestamp"])
            oi = float(item["sumOpenInterest"])
        except (KeyError, TypeError, ValueError):
            continue
        if ts <= candle_close_time:
            samples.append((ts, oi))
    samples.sort()
    if len(samples) < 2:
        return None

    last_ts, last_oi = samples[-1]
    target = last_ts - interval_ms
    prev_candidates = [x for x in samples[:-1] if x[0] <= target]
    if prev_candidates:
        _, prev_oi = prev_candidates[-1]
    else:
        _, prev_oi = samples[-2]
    if prev_oi == 0:
        return None
    return (last_oi - prev_oi) / prev_oi * 100


class OIEngine:
    def __init__(self, settings: Settings):
        self.s = settings

    def analyze(self, price_change_pct: float, oi_change_pct: float | None) -> OIResult:
        if oi_change_pct is None:
            return OIResult(None, OIState.NEUTRAL, 0, "OI unavailable")
        state = classify_oi(price_change_pct, oi_change_pct, self.s.min_oi_change_pct)
        if state is OIState.LONG_BUILDUP:
            return OIResult(oi_change_pct, state, 20, "price up + OI up: long buildup")
        if state is OIState.SHORT_BUILDUP:
            return OIResult(oi_change_pct, state, 20, "price down + OI up: short buildup")
        if state is OIState.SHORT_COVERING:
            return OIResult(
                oi_change_pct, state, self.s.oi_reversal_score,
                "price up + OI down: short covering (unwind penalty)",
            )
        if state is OIState.LONG_LIQUIDATION:
            return OIResult(
                oi_change_pct, state, self.s.oi_reversal_score,
                "price down + OI down: long liquidation (unwind penalty)",
            )
        return OIResult(oi_change_pct, state, 0, "OI neutral")
