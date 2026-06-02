# src/boss_job_hunter/rate_limiter.py
import asyncio
import time


class RateLimiter:
    """
    Token-bucket rate limiter.
    Default: 15 requests per 60 seconds = 4s average interval.
    Excess calls are awaited (not dropped).
    """

    def __init__(self, max_calls: int = 15, period: float = 60.0):
        self._max_calls = max_calls
        self._period = period
        self._min_interval = period / max_calls  # 4.0s
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


_default_limiter = RateLimiter()


async def rate_limited_delay() -> None:
    await _default_limiter.acquire()
