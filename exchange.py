import asyncio
import random
from typing import Any

import aiohttp

from config import Settings


class BinanceAPIError(RuntimeError):
    pass


class BinanceClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.session: aiohttp.ClientSession | None = None
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.s.request_timeout_sec)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def get(self, path: str, params: dict[str, Any] | None = None):
        if not self.session:
            raise RuntimeError("BinanceClient must be used as an async context manager")
        url = self.s.base_url + path
        last_error = None
        for attempt in range(self.s.request_retries):
            try:
                async with self.semaphore:
                    async with self.session.get(url, params=params) as resp:
                        if resp.status == 429:
                            retry_after = float(resp.headers.get("Retry-After", "1"))
                            await asyncio.sleep(max(retry_after, self.s.request_retry_base_sec))
                            continue
                        if resp.status >= 500:
                            raise BinanceAPIError(f"HTTP {resp.status}")
                        if resp.status != 200:
                            text = await resp.text()
                            raise BinanceAPIError(f"HTTP {resp.status}: {text[:300]}")
                        return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError, BinanceAPIError) as exc:
                last_error = exc
                if attempt + 1 < self.s.request_retries:
                    await asyncio.sleep(self.s.request_retry_base_sec * (2 ** attempt) + random.random() * 0.2)
        raise BinanceAPIError(str(last_error))

    async def get_symbols(self) -> list[str]:
        data = await self.get("/fapi/v1/exchangeInfo")
        return [
            s["symbol"] for s in data["symbols"]
            if s.get("quoteAsset") == "USDT"
            and s.get("status") == "TRADING"
            and s.get("contractType") == "PERPETUAL"
        ]

    async def fetch_klines(self, symbol: str, limit: int, interval: str | None = None):
        return await self.get("/fapi/v1/klines", {
            "symbol": symbol,
            "interval": interval or self.s.interval,
            "limit": limit,
        })

    async def fetch_open_interest_hist(self, symbol: str, limit: int):
        return await self.get("/futures/data/openInterestHist", {
            "symbol": symbol,
            "period": self.s.interval,
            "limit": limit,
        })
