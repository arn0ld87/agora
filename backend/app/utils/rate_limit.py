"""Small in-process fixed-window rate limiter for app-level abuse guards."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from flask import request


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

    def __init__(
        self,
        *,
        max_buckets: int = 4096,
        sweep_interval_seconds: int = 60,
    ) -> None:
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()
        self._max_buckets = max(1, max_buckets)
        self._sweep_interval_seconds = max(1, sweep_interval_seconds)
        self._next_sweep_at = 0.0

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
                if current >= self._next_sweep_at:
                    self._sweep(current)
                    self._next_sweep_at = current + self._sweep_interval_seconds
                if key not in self._buckets and len(self._buckets) >= self._max_buckets:
                    self._buckets.popitem(last=False)
                self._buckets[key] = _Bucket(count=1, reset_at=reset_at)
                return RateLimitResult(True)

            self._buckets.move_to_end(key)
            if bucket.count >= max_requests:
                retry_after = max(1, math.ceil(bucket.reset_at - current))
                return RateLimitResult(False, retry_after)

            bucket.count += 1
            return RateLimitResult(True)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._next_sweep_at = 0.0

    def _sweep(self, now: float) -> None:
        stale = [key for key, bucket in self._buckets.items() if now >= bucket.reset_at]
        for key in stale:
            self._buckets.pop(key, None)


def build_rate_limit_key(prefix: str, *, include_endpoint: bool = False) -> str:
    """Build a stable limiter key from the trusted Flask client address."""

    parts = [prefix]
    if include_endpoint:
        parts.append(request.endpoint or "unknown")
    parts.append(request.remote_addr or "unknown")
    return ":".join(parts)


ticket_rate_limiter = FixedWindowRateLimiter()
upload_rate_limiter = FixedWindowRateLimiter()
llm_trigger_rate_limiter = FixedWindowRateLimiter()
report_rate_limiter = FixedWindowRateLimiter()


__all__ = [
    "FixedWindowRateLimiter",
    "RateLimitResult",
    "build_rate_limit_key",
    "llm_trigger_rate_limiter",
    "report_rate_limiter",
    "ticket_rate_limiter",
    "upload_rate_limiter",
]
