from dataclasses import dataclass, field
from enum import Enum


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.UP else -1


class OIState(str, Enum):
    LONG_BUILDUP = "LONG_BUILDUP"
    SHORT_BUILDUP = "SHORT_BUILDUP"
    SHORT_COVERING = "SHORT_COVERING"
    LONG_LIQUIDATION = "LONG_LIQUIDATION"
    NEUTRAL = "NEUTRAL"


class SignalStrength(str, Enum):
    STRONG = "STRONG"
    NORMAL = "NORMAL"
    EARLY = "EARLY"
    WATCH = "WATCH"


@dataclass(frozen=True)
class Candle:
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    taker_buy_base_volume: float


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    candle: Candle
    history: tuple[Candle, ...]
    avg_volume: float
    volume_zscore: float
    price_change_pct: float
    taker_buy_ratio: float
    oi_change_pct: float | None


@dataclass(frozen=True)
class FlowSignal:
    direction: Direction | None
    valid: bool
    volume_zscore: float
    price_change_pct: float
    taker_buy_ratio: float
    score: int
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OIResult:
    change_pct: float | None
    state: OIState
    score: int
    reason: str


@dataclass(frozen=True)
class UTState:
    pos: int
    trailing_stop: float
    just_crossed: bool
    cross_direction: Direction | None = None


@dataclass(frozen=True)
class CompositeSignal:
    symbol: str
    candle_time: int
    direction: Direction
    strength: SignalStrength
    score: int
    snapshot: MarketSnapshot
    flow: FlowSignal
    oi: OIResult
    ut: UTState | None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    fib: "FibLevels | None" = None


@dataclass(frozen=True)
class AlertKey:
    symbol: str
    candle_time: int
    direction: Direction
    strength: SignalStrength
