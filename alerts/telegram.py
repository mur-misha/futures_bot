import aiohttp

from config import Settings
from models import CompositeSignal, OIState


def _oi_label(state: OIState) -> str:
    return {
        OIState.LONG_BUILDUP: "🟢 LONG BUILDUP",
        OIState.SHORT_BUILDUP: "🔴 SHORT BUILDUP",
        OIState.SHORT_COVERING: "🟡 SHORT COVERING",
        OIState.LONG_LIQUIDATION: "🟠 LONG LIQUIDATION",
        OIState.NEUTRAL: "⚪ NEUTRAL",
    }[state]


def _reversal_warning(sig: CompositeSignal, settings: Settings) -> str | None:
    """Soft note only. Extended price is a hard gate (MAX_PRICE_CHANGE_PCT);
    same-bar UT cross is excluded from score. Remaining warns:
      1. OI unwind (SHORT_COVERING / LONG_LIQUIDATION)
      2. NEUTRAL OI plus extreme volume (move without capital backing)
    """
    reasons = []
    z = sig.snapshot.volume_zscore
    if sig.oi.state in (OIState.SHORT_COVERING, OIState.LONG_LIQUIDATION):
        reasons.append("движение без роста OI (закрытие позиций, а не новый капитал)")
    elif sig.oi.state is OIState.NEUTRAL and z >= settings.reversal_warn_neutral_oi_zscore:
        reasons.append(
            f"экстремальный объём ({z:.1f}σ) при полностью нейтральном OI "
            f"— похоже на выброс без нового капитала, а не на устойчивый тренд"
        )

    if not reasons:
        return None
    return (
        "⚠️ ВНИМАНИЕ: возможен локальный разворот — " + "; ".join(reasons) + ". "
        "Рекомендуется наблюдать, не входить сразу на этой свече."
    )


def format_signal(sig: CompositeSignal, settings: Settings) -> str:
    s = sig.snapshot
    arrow = "🟢▲" if sig.direction.value == "UP" else "🔴▼"
    ut_text = "N/A"
    ut_stop = "N/A"
    if sig.ut:
        ut_text = "🟢 BULLISH" if sig.ut.pos == 1 else "🔴 BEARISH"
        if sig.ut.just_crossed:
            ut_text += " / FRESH CROSS (not confirmation)"
        ut_stop = f"{sig.ut.trailing_stop:,.4f}"

    oi = "N/A" if sig.oi.change_pct is None else f"{sig.oi.change_pct:+.2f}%"
    reasons = "\n".join(f"✓ {r}" for r in sig.reasons)

    warning = _reversal_warning(sig, settings)
    warning_block = f"\n{warning}\n" if warning else ""

    return (
        f"{arrow} {sig.strength.value} {sig.direction.value} — {sig.symbol} [FUTURES]\n"
        f"{warning_block}\n"
        f"Price       {s.price_change_pct:+.2f}%\n"
        f"Volume      {s.volume_zscore:.1f}σ\n"
        f"Taker       {s.taker_buy_ratio:.2f}\n"
        f"OI          {oi}\n"
        f"OI regime   {_oi_label(sig.oi.state)}\n\n"
        f"UT Bot      {ut_text}\n"
        f"UT Stop     {ut_stop}\n"
        f"Score       {sig.score}/100\n\n"
        f"Reasons:\n{reasons}"
    )


class TelegramNotifier:
    def __init__(self, settings: Settings):
        self.s = settings

    async def send(self, session: aiohttp.ClientSession, text: str):
        if not self.s.telegram_bot_token or not self.s.telegram_chat_id:
            return
        url = f"https://api.telegram.org/bot{self.s.telegram_bot_token}/sendMessage"
        payload = {"chat_id": self.s.telegram_chat_id, "text": text}
        try:
            async with session.post(url, data=payload) as resp:
                if resp.status != 200:
                    print(f"[warn] Telegram HTTP {resp.status}: {await resp.text()}")
        except aiohttp.ClientError as exc:
            print(f"[warn] Telegram error: {exc}")
