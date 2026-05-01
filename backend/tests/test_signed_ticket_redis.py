"""Tests for redis-backed single-use ticket replay detection (Slice 3)."""

from __future__ import annotations

import pytest
import fakeredis

from app.utils import signed_ticket


SECRET = "test-secret-sl3"


@pytest.fixture(autouse=True)
def _reset_module():
    signed_ticket._reset_seen_for_tests()
    yield
    signed_ticket._reset_seen_for_tests()


@pytest.fixture
def fakeredis_client():
    """Return a fakeredis Redis client that can be injected via monkeypatch."""
    return fakeredis.FakeRedis()


class TestRedisConsume:
    """consume() uses Redis SET NX when a client is wired in."""

    def test_first_consume_succeeds(self, fakeredis_client, monkeypatch):
        monkeypatch.setattr(
            signed_ticket, "_get_redis_client", lambda: fakeredis_client
        )
        t = signed_ticket.issue(SECRET, "sse:sim", ttl_seconds=60, now=1000.0)

        assert signed_ticket.consume(SECRET, t, "sse:sim", now=1000.0)

    def test_replay_blocked_by_redis(self, fakeredis_client, monkeypatch):
        monkeypatch.setattr(
            signed_ticket, "_get_redis_client", lambda: fakeredis_client
        )
        t = signed_ticket.issue(SECRET, "sse:sim", ttl_seconds=60, now=1000.0)

        assert signed_ticket.consume(SECRET, t, "sse:sim", now=1000.0)
        assert not signed_ticket.consume(SECRET, t, "sse:sim", now=1001.0)

    def test_multi_worker_simulation(self, fakeredis_client, monkeypatch):
        """Simulate two callers (e.g. workers) racing for the same ticket."""
        monkeypatch.setattr(
            signed_ticket, "_get_redis_client", lambda: fakeredis_client
        )
        t = signed_ticket.issue(SECRET, "sse:sim", ttl_seconds=60, now=1000.0)

        # Two calls — only one wins
        results = [
            signed_ticket.consume(SECRET, t, "sse:sim", now=1000.0),
            signed_ticket.consume(SECRET, t, "sse:sim", now=1000.0),
        ]
        assert results.count(True) == 1
        assert results.count(False) == 1


class TestInMemoryFallback:
    """When Redis returns None (unavailable), the in-process set kicks in."""

    def test_fallback_allows_first_consume(self):
        # _get_redis_client already returns None (no REDIS_URL configured)
        t = signed_ticket.issue(SECRET, "sse:sim", ttl_seconds=60, now=1000.0)

        assert signed_ticket.consume(SECRET, t, "sse:sim", now=1000.0)

    def test_fallback_blocks_replay(self):
        t = signed_ticket.issue(SECRET, "sse:sim", ttl_seconds=60, now=1000.0)
        assert signed_ticket.consume(SECRET, t, "sse:sim", now=1000.0)
        assert not signed_ticket.consume(SECRET, t, "sse:sim", now=1001.0)

    def test_fallback_emits_warning(self, monkeypatch):
        import logging
        import io
        # Force in-memory path without triggering _get_redis_client's own log
        monkeypatch.setattr(signed_ticket, "_get_redis_client", lambda: None)
        # Attach a temporary handler to the module logger
        handler = logging.StreamHandler(io.StringIO())
        handler.setLevel(logging.DEBUG)
        signed_ticket.logger.addHandler(handler)
        signed_ticket.logger.setLevel(logging.DEBUG)
        t = signed_ticket.issue(SECRET, "sse:sim", ttl_seconds=60, now=1000.0)
        signed_ticket.consume(SECRET, t, "sse:sim", now=1000.0)
        output = handler.stream.getvalue()
        signed_ticket.logger.removeHandler(handler)
        assert "in-process" in output
