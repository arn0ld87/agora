"""Small in-process fixed-window rate limiter for app-level abuse guards."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


@dataclass
class _Bucket:
    count: int
    reset_at: float


class FixedWindowRateLimiter:
    """Thread-safe fixed-window limiter keyed by caller and endpoint.

    This is intentionally process-local. Agora v1.0 is single-user/local-first;
    Redis-backed distributed throttling can follow if the deployment model
    expands beyond that.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        max_requests: int,
        window_seconds: int,
        now: float | None = None,
    ) -> RateLimitResult:
        if max_requests <= 0 or window_seconds <= 0:
            return RateLimitResult(True)

        current = time.monotonic() if now is None else now
        reset_at = current + window_seconds

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or current >= bucket.reset_at:
                self._buckets[key] = _Bucket(count=1, reset_at=reset_at)
                self._sweep(current)
                return RateLimitResult(True)

            if bucket.count >= max_requests:
                retry_after = max(1, math.ceil(bucket.reset_at - current))
                return RateLimitResult(False, retry_after)

            bucket.count += 1
            return RateLimitResult(True)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _sweep(self, now: float) -> None:
        stale = [key for key, bucket in self._buckets.items() if now >= bucket.reset_at]
        for key in stale:
            self._buckets.pop(key, None)


ticket_rate_limiter = FixedWindowRateLimiter()


__all__ = ["FixedWindowRateLimiter", "RateLimitResult", "ticket_rate_limiter"]
