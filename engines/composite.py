from config import Settings
from models import CompositeSignal, Direction, FlowSignal, MarketSnapshot, OIResult, SignalStrength, UTState


class CompositeEngine:
    def __init__(self, settings: Settings):
        self.s = settings

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        flow: FlowSignal,
        oi: OIResult,
        ut: UTState | None,
    ) -> CompositeSignal | None:
        # A volume/price/taker event remains the primary trigger.
        if not flow.valid or flow.direction is None:
            return None

        score = flow.score + oi.score
        reasons = list(flow.reasons)
        reasons.append(oi.reason)

        if ut is not None:
            same_bar_cross = (
                ut.just_crossed and ut.cross_direction is flow.direction
            )
            if same_bar_cross:
                # The impulse that triggered flow also broke the 15m trailing
                # stop. That is not independent confirmation — show it, do
                # not score it, and do not treat the new pos as a prior trend.
                reasons.append("fresh UT cross on this bar (not used as confirmation)")
            elif ut.pos == flow.direction.sign:
                score += 15
                reasons.append("UT trend confirms direction")
            else:
                reasons.append("flow is against current UT trend")

        score = min(score, 100)
        strength = self._strength(score, ut, flow.direction)
        min_score = (
            self.s.early_min_alert_score
            if strength is SignalStrength.EARLY
            else self.s.min_alert_score
        )
        if score < min_score:
            return None

        return CompositeSignal(
            symbol=snapshot.symbol,
            candle_time=snapshot.candle.open_time,
            direction=flow.direction,
            strength=strength,
            score=score,
            snapshot=snapshot,
            flow=flow,
            oi=oi,
            ut=ut,
            reasons=tuple(reasons),
        )

    def _strength(self, score: int, ut: UTState | None, direction: Direction) -> SignalStrength:
        # Against an *established* UT regime (not a same-bar flip) is EARLY.
        # A same-bar cross is neither confirmation nor "against prior trend".
        if ut is not None and ut.pos != direction.sign and not (
            ut.just_crossed and ut.cross_direction is direction
        ):
            return SignalStrength.EARLY
        if score >= self.s.strong_score:
            return SignalStrength.STRONG
        if score >= self.s.normal_score:
            return SignalStrength.NORMAL
        return SignalStrength.WATCH
