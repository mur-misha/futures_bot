import asyncio
import time
from dataclasses import replace

import aiohttp

from alerts.telegram import TelegramNotifier, format_signal
from config import OI_SUPPORTED_PERIODS, SETTINGS
from engines.composite import CompositeEngine
from engines.oi import OIEngine, calc_oi_change_pct
from engines.ut import UTEngine
from engines.volume import VolumeEngine, build_snapshot
from exchange import BinanceClient
from models import AlertKey
from state.store import StateStore


INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


def next_boundary_sleep_ms(interval_ms: int, delay_sec: float) -> float:
    now = int(time.time() * 1000)
    next_open = ((now // interval_ms) + 1) * interval_ms
    return max(0.0, (next_open - now) / 1000 + delay_sec)


async def process_symbol(
    symbol: str,
    exchange: BinanceClient,
    ut_engine: UTEngine,
    volume_engine: VolumeEngine,
    oi_engine: OIEngine,
    composite: CompositeEngine,
    settings=SETTINGS,
):
    try:
        kline_limit = settings.lookback + 3
        # Enough bars on the UT timeframe to warm up ATR RMA (needs >= period*3)
        # plus the configured minimum.
        ut_kline_limit = max(settings.ut_min_bars + 10, settings.ut_atr_period * 3 + 5)

        klines_task = asyncio.create_task(exchange.fetch_klines(symbol, kline_limit))
        ut_klines_task = asyncio.create_task(
            exchange.fetch_klines(symbol, ut_kline_limit, interval=settings.ut_interval)
        )
        oi_task = asyncio.create_task(exchange.fetch_open_interest_hist(symbol, settings.oi_limit))
        klines, ut_klines, oi_hist = await asyncio.gather(klines_task, ut_klines_task, oi_task)

        now_ms = int(time.time() * 1000)
        snapshot = build_snapshot(symbol, klines, now_ms, settings.lookback)
        if snapshot is None:
            return None

        interval_ms = INTERVAL_MS[settings.interval]
        oi_change = calc_oi_change_pct(oi_hist, snapshot.candle.close_time, interval_ms)
        snapshot = replace(snapshot, oi_change_pct=oi_change)

        flow = volume_engine.analyze(snapshot)
        oi = oi_engine.analyze(snapshot.price_change_pct, oi_change)

        # UT Bot runs on its OWN timeframe (settings.ut_interval), decoupled
        # from the main signal interval — e.g. flow triggers on 5m candles
        # while UT confirms trend direction on steadier 15m/30m candles.
        parsed = [
            (int(r[0]), int(r[6]), float(r[1]), float(r[2]), float(r[3]), float(r[4]))
            for r in ut_klines if len(r) >= 7 and int(r[6]) < now_ms
        ]
        open_times = [x[0] for x in parsed]
        highs = [x[3] for x in parsed]
        lows = [x[4] for x in parsed]
        closes = [x[5] for x in parsed]
        ut = ut_engine.analyze(symbol, open_times, highs, lows, closes)

        return composite.evaluate(snapshot, flow, oi, ut)
    except Exception as exc:
        print(f"[warn] {symbol}: {exc}")
        return None


async def run():
    settings = SETTINGS
    if settings.interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {settings.interval}")
    if settings.ut_interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported UT_INTERVAL: {settings.ut_interval}")
    if settings.interval not in OI_SUPPORTED_PERIODS:
        raise ValueError(
            f"INTERVAL={settings.interval} is not supported by Binance's "
            f"openInterestHist endpoint. Supported values: {sorted(OI_SUPPORTED_PERIODS)}. "
            f"Using an unsupported interval would silently fail OI fetches for every symbol."
        )

    store = StateStore(settings.state_file)
    notifier = TelegramNotifier(settings)
    async with BinanceClient(settings) as exchange:
        symbols = await exchange.get_symbols()

        # Все движки создаются ОДИН раз, а не на каждую монету в каждом цикле.
        # UTEngine - stateful (хранит trailing stop по каждому символу отдельно),
        # поэтому единственный экземпляр обязателен и был таким изначально.
        # VolumeEngine/OIEngine/CompositeEngine - stateless (хранят только settings),
        # поэтому их тоже безопасно переиспользовать между всеми монетами и циклами.
        ut_engine = UTEngine(settings)
        volume_engine = VolumeEngine(settings)
        oi_engine = OIEngine(settings)
        composite = CompositeEngine(settings)

        print(f"Отслеживаю {len(symbols)} perpetual USDT contracts, interval={settings.interval}")

        # Telegram-сессия создаётся один раз на весь запуск, а не заново каждый цикл.
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as tg_session:
            first = True
            while True:
                if not first or not settings.run_immediately:
                    sleep_sec = next_boundary_sleep_ms(INTERVAL_MS[settings.interval], settings.candle_close_delay_sec)
                    print(f"[wait] следующая свеча через {sleep_sec:.1f}s")
                    await asyncio.sleep(sleep_sec)
                first = False

                started = time.monotonic()
                tasks = [
                    process_symbol(symbol, exchange, ut_engine, volume_engine, oi_engine, composite, settings)
                    for symbol in symbols
                ]
                results = await asyncio.gather(*tasks)
                signals = [r for r in results if r is not None]

                sent = 0
                for sig in signals:
                    if store.already_processed(sig.symbol, sig.candle_time):
                        continue
                    store.mark_processed(sig.symbol, sig.candle_time)

                    key = AlertKey(sig.symbol, sig.candle_time, sig.direction, sig.strength)
                    if not store.should_alert(key, settings.alert_cooldown_sec):
                        continue

                    msg = format_signal(sig, settings)
                    print("\n" + msg + "\n")
                    await notifier.send(tg_session, msg)
                    store.mark_alert(key)
                    sent += 1

                store.save()
                elapsed = time.monotonic() - started
                print(f"[cycle] checked={len(symbols)} signals={len(signals)} sent={sent} elapsed={elapsed:.1f}s")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
