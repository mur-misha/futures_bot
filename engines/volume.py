import statistics

from config import Settings
from models import Candle, Direction, FlowSignal, MarketSnapshot


class VolumeEngine:
    def __init__(self, settings: Settings):
        self.s = settings

    def analyze(self, snapshot: MarketSnapshot) -> FlowSignal:
        z = snapshot.volume_zscore
        p = snapshot.price_change_pct
        t = snapshot.taker_buy_ratio
        reasons: list[str] = []

        if z < self.s.volume_zscore_threshold:
            return FlowSignal(None, False, z, p, t, 0, ("volume below threshold",))
        reasons.append(f"volume {z:.1f}σ")

        if abs(p) < self.s.min_price_change_pct:
            return FlowSignal(None, False, z, p, t, 0, tuple(reasons + ["price move below threshold"]))
        reasons.append(f"price {p:+.2f}%")

        if self.s.max_price_change_pct > 0 and abs(p) > self.s.max_price_change_pct:
            # Candle already moved too far — this is the exhaustion/climax
            # signature that tends to mark a local reversal, not an early
            # trend entry. Reject rather than chase it.
            return FlowSignal(None, False, z, p, t, 0, tuple(reasons + ["price move too extended (likely exhaustion)"]))

        if p > 0 and t >= self.s.taker_up_threshold:
            direction = Direction.UP
            reasons.append(f"taker {t:.2f} confirms buyers")
        elif p < 0 and t <= self.s.taker_down_threshold:
            direction = Direction.DOWN
            reasons.append(f"taker {t:.2f} confirms sellers")
        else:
            return FlowSignal(None, False, z, p, t, 0, tuple(reasons + ["taker does not confirm direction"]))

        score = self._score(z, p, t)
        return FlowSignal(direction, True, z, p, t, score, tuple(reasons))

    def _score(self, z: float, p: float, t: float) -> int:
        # 25 volume + 15 price + 15 taker.
        volume_score = min(25, max(0, int(25 * min(z / 4.0, 1.0))))
        price_score = min(15, max(0, int(15 * min(abs(p) / 1.0, 1.0))))
        taker_edge = abs(t - 0.5)
        taker_score = min(15, max(0, int(15 * min(taker_edge / 0.20, 1.0))))
        return volume_score + price_score + taker_score


def build_snapshot(symbol: str, klines: list, now_ms: int, lookback: int) -> MarketSnapshot | None:
    """Extract the latest closed candle and exactly LOOKBACK preceding candles."""
    if len(klines) < lookback + 1:
        return None

    parsed = []
    for row in klines:
        if len(row) < 10:
            continue
        parsed.append((
            int(row[0]), int(row[6]), float(row[1]), float(row[2]), float(row[3]),
            float(row[4]), float(row[5]), float(row[9])
        ))
    if len(parsed) < lookback + 1:
        return None

    closed = [r for r in parsed if r[1] < now_ms]
    if len(closed) < lookback + 1:
        return None

    last = closed[-1]
    history_rows = closed[-(lookback + 1):-1]
    history = tuple(Candle(*r) for r in history_rows)
    candle = Candle(*last)

    volumes = [c.volume for c in history]
    avg = statistics.mean(volumes)
    std = statistics.pstdev(volumes)
    z = (candle.volume - avg) / (std if std > 0 else max(avg * 1e-9, 1e-12))
    price_pct = (candle.close - candle.open) / candle.open * 100 if candle.open else 0.0
    taker_ratio = candle.taker_buy_base_volume / candle.volume if candle.volume > 0 else 0.5

    return MarketSnapshot(
        symbol=symbol,
        candle=candle,
        history=history,
        avg_volume=avg,
        volume_zscore=z,
        price_change_pct=price_pct,
        taker_buy_ratio=taker_ratio,
        oi_change_pct=None,
    )
