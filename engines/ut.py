from dataclasses import dataclass

from config import Settings
from models import Direction, UTState
from ut_bot import compute_ut_bot_series


@dataclass
class _Runtime:
    last_candle_time: int
    prev_close: float
    atr: float
    trailing_stop: float
    pos: int


class UTEngine:
    """UT Bot engine with a historical seed and O(1) updates per new closed candle."""

    def __init__(self, settings: Settings):
        self.s = settings
        self._runtime: dict[str, _Runtime] = {}

    def analyze(
        self,
        symbol: str,
        open_times: list[int],
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ) -> UTState | None:
        if len(closes) < self.s.ut_min_bars:
            return None
        if not (len(open_times) == len(highs) == len(lows) == len(closes)):
            raise ValueError("UT input arrays must have equal length")

        last_time = open_times[-1]
        runtime = self._runtime.get(symbol)

        if runtime is None or last_time < runtime.last_candle_time:
            state = self._seed(symbol, open_times, highs, lows, closes)
            return state

        if last_time == runtime.last_candle_time:
            return self._state(runtime, False, None)

        # Normal case: exactly one new closed candle. If several candles were missed,
        # replay them sequentially so the state remains deterministic.
        start_idx = open_times.index(runtime.last_candle_time) + 1 if runtime.last_candle_time in open_times else None
        if start_idx is None:
            return self._seed(symbol, open_times, highs, lows, closes)

        cross = False
        cross_direction = None
        for i in range(start_idx, len(closes)):
            cross, cross_direction = self._update(runtime, highs[i], lows[i], closes[i])
            runtime.last_candle_time = open_times[i]

        return self._state(runtime, cross, cross_direction)

    def _seed(self, symbol, open_times, highs, lows, closes) -> UTState | None:
        # Single source of truth: both the cold UTState result and the warm
        # runtime (used for O(1) updates later) are derived from the same
        # array computation, so they can never silently diverge.
        series = compute_ut_bot_series(
            highs, lows, closes,
            key_value=self.s.ut_key_value,
            atr_period=self.s.ut_atr_period,
        )
        if series is None:
            return None
        stop, pos, atr = series

        cross_direction = None
        just_crossed = False
        if pos[-1] != pos[-2]:
            just_crossed = True
            cross_direction = Direction.UP if pos[-1] == 1 else Direction.DOWN

        self._runtime[symbol] = _Runtime(
            last_candle_time=open_times[-1],
            prev_close=closes[-1],
            atr=atr[-1],
            trailing_stop=stop[-1],
            pos=pos[-1],
        )
        return UTState(pos[-1], stop[-1], just_crossed, cross_direction)

    def _update(self, runtime: _Runtime, high: float, low: float, close: float):
        period = self.s.ut_atr_period
        # Wilder RMA update needs the current TR and previous ATR. The seeded runtime
        # already contains a valid ATR, so each new closed candle is O(1).
        tr = max(high - low, abs(high - runtime.prev_close), abs(low - runtime.prev_close))
        runtime.atr = (runtime.atr * (period - 1) + tr) / period
        loss = self.s.ut_key_value * runtime.atr
        prev_stop = runtime.trailing_stop
        prev_close = runtime.prev_close

        if close > prev_stop and prev_close > prev_stop:
            runtime.trailing_stop = max(prev_stop, close - loss)
        elif close < prev_stop and prev_close < prev_stop:
            runtime.trailing_stop = min(prev_stop, close + loss)
        else:
            runtime.trailing_stop = close - loss if close > prev_stop else close + loss

        cross = False
        cross_direction = None
        if prev_close < prev_stop and close > prev_stop:
            runtime.pos = 1
            cross = True
            cross_direction = Direction.UP
        elif prev_close > prev_stop and close < prev_stop:
            runtime.pos = -1
            cross = True
            cross_direction = Direction.DOWN

        runtime.prev_close = close
        return cross, cross_direction

    @staticmethod
    def _state(runtime: _Runtime, crossed: bool, cross_direction: Direction | None) -> UTState:
        return UTState(runtime.pos, runtime.trailing_stop, crossed, cross_direction)
