from __future__ import annotations

from app.utils.rate_limit import FixedWindowRateLimiter


def test_fixed_window_blocks_after_limit():
    limiter = FixedWindowRateLimiter()

    first = limiter.check("client", max_requests=2, window_seconds=60, now=100.0)
    second = limiter.check("client", max_requests=2, window_seconds=60, now=101.0)
    third = limiter.check("client", max_requests=2, window_seconds=60, now=102.0)

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.retry_after_seconds == 58


def test_fixed_window_resets_after_window():
    limiter = FixedWindowRateLimiter()

    assert limiter.check("client", max_requests=1, window_seconds=60, now=100.0).allowed
    blocked = limiter.check("client", max_requests=1, window_seconds=60, now=120.0)
    reset = limiter.check("client", max_requests=1, window_seconds=60, now=160.0)

    assert not blocked.allowed
    assert reset.allowed


def test_fixed_window_can_be_disabled():
    limiter = FixedWindowRateLimiter()

    for _ in range(3):
        result = limiter.check("client", max_requests=0, window_seconds=60, now=100.0)
        assert result.allowed


def test_fixed_window_caps_bucket_count():
    limiter = FixedWindowRateLimiter(max_buckets=2, sweep_interval_seconds=999)

    assert limiter.check("client-1", max_requests=10, window_seconds=60, now=100.0).allowed
    assert limiter.check("client-2", max_requests=10, window_seconds=60, now=100.0).allowed
    assert limiter.check("client-3", max_requests=10, window_seconds=60, now=100.0).allowed

    assert len(limiter._buckets) == 2
    assert "client-1" not in limiter._buckets
