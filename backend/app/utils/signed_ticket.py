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

``consume`` additionally tracks redeemed signatures in an in-process
set with TTL-based sweeping so the same ticket can't be replayed inside
its expiry window. Multi-worker deployments lose that guarantee per
worker; tighten via a shared store later if needed.
"""

from __future__ import annotations

import hmac
import threading
import time
from hashlib import sha256

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
    """Verify and mark ticket as redeemed. Replay returns False."""
    if not verify(secret, ticket, expected_scope, now=now):
        return False
    parsed = _parse(ticket)
    assert parsed is not None  # verify guaranteed it
    _, exp, _, sig = parsed
    current = now if now is not None else time.time()
    now_int = int(current)
    with _seen_lock:
        _sweep_locked(now_int)
        if sig in _seen:
            return False
        _seen[sig] = exp
    return True


def _reset_seen_for_tests() -> None:
    """Test helper — clear the redemption store between cases."""
    with _seen_lock:
        _seen.clear()
