from dataclasses import dataclass
import os
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Tiny dotenv loader; avoids an extra dependency."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

# Binance's /futures/data/openInterestHist endpoint only accepts these periods
# for its `period` parameter — unlike /fapi/v1/klines, it does NOT support 1m/3m.
# Kept here (not in main.py) so exchange.py and config validation share one source.
OI_SUPPORTED_PERIODS = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv("BINANCE_BASE_URL", "https://fapi.binance.com")
    interval: str = os.getenv("INTERVAL", "5m")
    lookback: int = int(os.getenv("LOOKBACK", "20"))
    candle_close_delay_sec: float = float(os.getenv("CANDLE_CLOSE_DELAY_SEC", "3"))
    run_immediately: bool = os.getenv("RUN_IMMEDIATELY", "true").lower() == "true"

    volume_zscore_threshold: float = float(os.getenv("VOLUME_ZSCORE_THRESHOLD", "2.0"))
    min_price_change_pct: float = float(os.getenv("MIN_PRICE_CHANGE_PCT", "0.4"))
    # 0 = disabled. Set to e.g. 2.0 to reject candles that already moved too
    # far (classic exhaustion/climax candles, which is what tends to mark
    # local reversals rather than early trend entries).
    # Hard gate: reject trigger candles that already moved this far (climax).
    # 0 = disabled. Default 1.2% on the 5m bar.
    max_price_change_pct: float = float(os.getenv("MAX_PRICE_CHANGE_PCT", "1.2"))
    # Unused for the price gate (that is MAX_PRICE_CHANGE_PCT). Kept so older
    # .env files still load; Telegram warnings now cover OI unwind / neutral
    # OI + extreme volume only.
    reversal_warn_price_pct: float = float(os.getenv("REVERSAL_WARN_PRICE_PCT", "1.5"))
    # Third warning condition: OI stayed NEUTRAL (no new capital either way)
    # while volume was an extreme outlier. This is the same "move without
    # capital backing" red flag as SHORT_COVERING/LONG_LIQUIDATION, just for
    # the case where OI barely moved at all instead of dropping.
    reversal_warn_neutral_oi_zscore: float = float(os.getenv("REVERSAL_WARN_NEUTRAL_OI_ZSCORE", "5.0"))
    taker_up_threshold: float = float(os.getenv("PRICE_UP_TAKER_RATIO", "0.53"))
    taker_down_threshold: float = float(os.getenv("PRICE_DOWN_TAKER_RATIO", "0.47"))
    min_oi_change_pct: float = float(os.getenv("MIN_OI_CHANGE_PCT", "0.4"))
    # Applied to SHORT_COVERING / LONG_LIQUIDATION. Negative = penalty so
    # unwind cannot push a climax candle over the alert threshold.
    oi_reversal_score: int = int(os.getenv("OI_REVERSAL_SCORE", "-15"))

    ut_key_value: float = float(os.getenv("UT_KEY_VALUE", "1.0"))
    ut_atr_period: int = int(os.getenv("UT_ATR_PERIOD", "10"))
    ut_min_bars: int = int(os.getenv("UT_MIN_BARS", "30"))
    # UT Bot can run on a HIGHER timeframe than the main signal interval —
    # e.g. main flow triggers on 5m candles, but UT trend confirmation uses
    # 15m/30m candles for a steadier, less noisy directional filter.
    # Must be one of INTERVAL_MS's keys in main.py.
    ut_interval: str = os.getenv("UT_INTERVAL", "15m")

    strong_score: int = int(os.getenv("STRONG_SCORE", "75"))
    normal_score: int = int(os.getenv("NORMAL_SCORE", "60"))
    watch_score: int = int(os.getenv("WATCH_SCORE", "45"))
    min_alert_score: int = int(os.getenv("MIN_ALERT_SCORE", "60"))
    # Flow against the established UT regime is EARLY; require a cleaner
    # score so weak against-trend prints do not ride in on leftover points.
    early_min_alert_score: int = int(os.getenv("EARLY_MIN_ALERT_SCORE", "70"))
    alert_cooldown_sec: int = int(os.getenv("ALERT_COOLDOWN_SEC", "900"))

    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "8"))
    request_timeout_sec: float = float(os.getenv("REQUEST_TIMEOUT_SEC", "15"))
    request_retries: int = int(os.getenv("REQUEST_RETRIES", "3"))
    request_retry_base_sec: float = float(os.getenv("REQUEST_RETRY_BASE_SEC", "0.75"))
    oi_limit: int = int(os.getenv("OI_LIMIT", "6"))

    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")
    state_file: str = os.getenv("STATE_FILE", "bot_state.json")


SETTINGS = Settings()
