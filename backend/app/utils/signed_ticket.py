"""Short-lived HMAC-signed tickets for URL-bound auth (P0.2).

The Agora API guard normally accepts the bearer token via header. URLs
that browsers can't sign — SSE ``EventSource`` connections, anchor-tag
downloads — needed a long-lived ``?token=<bearer>`` fallback. That
exposes the bearer in proxy logs, browser history, and Referer headers.

This module mints scope-bound, expiring, single-use tickets keyed by the
process ``SECRET_KEY``. Format::

    v1.<exp_unix>.<scope>.<sig>

* ``exp_unix`` — integer seconds since epoch when the ticket stops being
  valid.
* ``scope`` — caller-defined identifier, e.g. ``sse:<sim_id>`` or
  ``download:report:<id>``. ``verify``/``consume`` reject mismatched
  scopes so a ticket minted for one resource cannot be replayed against
  another.
* ``sig`` — first 32 hex chars (128 bits) of
  ``HMAC-SHA256(secret, "v1.<exp>.<scope>")``.

``consume`` uses an atomic ``SET NX`` against Redis when available,
making replay detection safe across gunicorn workers. Falls back to
the in-process set when Redis is unreachable or not configured.
"""

from __future__ import annotations

import hmac
import logging
import threading
import time
from hashlib import sha256
logger = logging.getLogger("agora.signed_ticket")

VERSION = "v1"
_SIG_LEN = 32
_SEPARATOR = "."


def _signature(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), sha256)
    return digest.hexdigest()[:_SIG_LEN]


def issue(secret: str, scope: str, ttl_seconds: int = 60, *, now: float | None = None) -> str:
    """Mint a ticket bound to ``scope`` valid for ``ttl_seconds`` seconds."""
    if not secret:
        raise ValueError("signed_ticket.issue requires a non-empty secret")
    if not scope or _SEPARATOR in scope:
        raise ValueError("scope must be non-empty and not contain '.'")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")

    issued_at = now if now is not None else time.time()
    exp = int(issued_at + ttl_seconds)
    payload = f"{VERSION}{_SEPARATOR}{exp}{_SEPARATOR}{scope}"
    return f"{payload}{_SEPARATOR}{_signature(secret, payload)}"


def _parse(ticket: str) -> tuple[str, int, str, str] | None:
    if not ticket or ticket.count(_SEPARATOR) < 3:
        return None
    version, exp_str, scope, sig = ticket.split(_SEPARATOR, 3)
    if version != VERSION:
        return None
    try:
        exp = int(exp_str)
    except ValueError:
        return None
    return version, exp, scope, sig


def verify(
    secret: str,
    ticket: str,
    expected_scope: str,
    *,
    now: float | None = None,
) -> bool:
    """Return True iff ticket signature, scope and expiry all check out."""
    parsed = _parse(ticket)
    if parsed is None:
        return False
    version, exp, scope, sig = parsed
    if scope != expected_scope:
        return False
    current = now if now is not None else time.time()
    if exp <= current:
        return False
    payload = f"{version}{_SEPARATOR}{exp}{_SEPARATOR}{scope}"
    expected_sig = _signature(secret, payload)
    return hmac.compare_digest(sig, expected_sig)


# ---- Single-use redemption store -----------------------------------------

_seen_lock = threading.Lock()
_seen: dict[str, int] = {}  # signature -> expiry unix seconds

# Redis integration (multi-worker-safe replay detection)
_redis_client: "object | None" = None  # redis.Redis or None
_redis_init_attempted = False

_REDIS_TICKET_PREFIX = "ticket:"

_warn_in_memory_done = False


def _warn_in_memory_once() -> None:
    """Emit a single process-lifetime warning about in-process ticket storage."""
    global _warn_in_memory_done
    if not _warn_in_memory_done:
        _warn_in_memory_done = True
        logger.warning(
            "Using in-process ticket store (single-worker mode); "
            "configure REDIS_URL for multi-worker safety"
        )


def _get_redis_client() -> "object | None":
    """Lazy-init a Redis client from Config.REDIS_URL. Returns None on failure.

    Does NOT permanently cache a failed init — if Redis was down on first
    attempt, the next call will retry.
    """
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted and _redis_client is not None:
        return _redis_client
    try:
        import redis as redis_lib

        from ..config import Config

        url = Config.REDIS_URL
        if not url:
            return None
        _redis_client = redis_lib.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        _redis_client.ping()
        logger.info("signed_ticket Redis connected")
        _redis_init_attempted = True
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning("signed_ticket Redis not available: %s", exc)
        _redis_client = None
        # Leave _redis_init_attempted False so the next call retries.
    return _redis_client


def _try_redis_consume(sig: str, ttl: int) -> bool | None:
    """Try atomic ``SET ticket:<sig> 1 NX EX <ttl>`` against Redis.

    Returns:
        True:  first consumer (SET returned OK)
        False: replay (SET returned None — key already existed)
        None:  Redis unavailable, caller should fall back to in-memory
    """
    r = _get_redis_client()
    if r is None:
        return None
    try:
        key = f"{_REDIS_TICKET_PREFIX}{sig}"
        was_set = r.set(key, "1", nx=True, ex=ttl)
        return bool(was_set)
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning("Redis SET NX failed: %s, falling back to in-memory", exc)
        return None


def _sweep_locked(now_int: int) -> None:
    expired = [sig for sig, exp in _seen.items() if exp <= now_int]
    for sig in expired:
        _seen.pop(sig, None)


def consume(
    secret: str,
    ticket: str,
    expected_scope: str,
    *,
    now: float | None = None,
) -> bool:
    """Verify and mark ticket as redeemed. Replay returns False.

    Uses atomic Redis ``SET NX`` when available for multi-worker safety.
    Falls back to in-process set with a warning.
    """
    if not verify(secret, ticket, expected_scope, now=now):
        return False
    parsed = _parse(ticket)
    assert parsed is not None  # verify guaranteed it
    _, exp, _, sig = parsed
    current = now if now is not None else time.time()
    now_int = int(current)
    ttl = max(1, exp - now_int)

    # Try Redis first (atomic across workers)
    result = _try_redis_consume(sig, ttl)
    if result is not None:
        return result

    # Fallback: in-process set (not safe under gunicorn multi-worker)
    _warn_in_memory_once()
    with _seen_lock:
        _sweep_locked(now_int)
        if sig in _seen:
            return False
        _seen[sig] = exp
    return True


def reset_after_fork() -> None:
    """Close and discard the inherited Redis client after gunicorn fork.

    The first real call will trigger a new connection. Also clears the
    in-process redemption store to avoid double-redemption race conditions
    with the parent process (though in-memory is not recommended for prod).
    """
    global _redis_client, _redis_init_attempted, _warn_in_memory_done
    with _seen_lock:
        _seen.clear()
    try:
        if _redis_client is not None:
            _redis_client.close()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 — Redis close on fork; exc discarded
        logger.debug("signed_ticket: redis.close() after fork failed, ignoring: %s", exc)
    finally:
        _redis_client = None
        _redis_init_attempted = False
        _warn_in_memory_done = False


def _reset_seen_for_tests() -> None:
    """Test helper — clear the redemption store between cases."""
    reset_after_fork()
