"""Tests for the signed-ticket utility (P0.2a)."""

from __future__ import annotations

import pytest

from app.utils import signed_ticket


SECRET = "test-secret-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _reset_consumed_set():
    signed_ticket._reset_seen_for_tests()
    yield
    signed_ticket._reset_seen_for_tests()


def test_issue_and_verify_roundtrip():
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60, now=1000.0)

    assert signed_ticket.verify(SECRET, ticket, "sse:sim_abc", now=1000.0)


def test_verify_rejects_after_expiry():
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60, now=1000.0)

    assert not signed_ticket.verify(SECRET, ticket, "sse:sim_abc", now=1061.0)


def test_verify_rejects_wrong_scope():
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60, now=1000.0)

    assert not signed_ticket.verify(SECRET, ticket, "download:report:42", now=1000.0)


def test_verify_rejects_tampered_signature():
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60, now=1000.0)
    head, _, tail = ticket.rpartition(".")
    bogus = f"{head}.{'0' * len(tail)}"

    assert not signed_ticket.verify(SECRET, bogus, "sse:sim_abc", now=1000.0)


def test_verify_rejects_wrong_secret():
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60, now=1000.0)

    assert not signed_ticket.verify("other-secret", ticket, "sse:sim_abc", now=1000.0)


def test_verify_rejects_garbage_input():
    assert not signed_ticket.verify(SECRET, "", "scope", now=1000.0)
    assert not signed_ticket.verify(SECRET, "not-a-ticket", "scope", now=1000.0)
    assert not signed_ticket.verify(SECRET, "v1.notanint.scope.sig", "scope", now=1000.0)
    assert not signed_ticket.verify(SECRET, "v0.1000.scope.sig", "scope", now=500.0)


def test_consume_succeeds_once_then_fails():
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60, now=1000.0)

    assert signed_ticket.consume(SECRET, ticket, "sse:sim_abc", now=1000.0)
    assert not signed_ticket.consume(SECRET, ticket, "sse:sim_abc", now=1001.0)


def test_consume_does_not_block_other_tickets():
    a = signed_ticket.issue(SECRET, "sse:sim_a", ttl_seconds=60, now=1000.0)
    b = signed_ticket.issue(SECRET, "sse:sim_b", ttl_seconds=60, now=1000.0)

    assert signed_ticket.consume(SECRET, a, "sse:sim_a", now=1000.0)
    assert signed_ticket.consume(SECRET, b, "sse:sim_b", now=1000.0)


def test_consume_seen_set_sweeps_expired_entries():
    early = signed_ticket.issue(SECRET, "sse:sim_a", ttl_seconds=10, now=1000.0)
    assert signed_ticket.consume(SECRET, early, "sse:sim_a", now=1000.0)

    # Internal store should still have the entry while not yet expired.
    assert len(signed_ticket._seen) == 1

    # Long after expiry, a fresh consume of any other ticket triggers sweep.
    later = signed_ticket.issue(SECRET, "sse:sim_b", ttl_seconds=10, now=2000.0)
    assert signed_ticket.consume(SECRET, later, "sse:sim_b", now=2000.0)
    assert len(signed_ticket._seen) == 1  # only the new one remains


def test_issue_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        signed_ticket.issue("", "scope")
    with pytest.raises(ValueError):
        signed_ticket.issue(SECRET, "")
    with pytest.raises(ValueError):
        signed_ticket.issue(SECRET, "scope.with.dot")
    with pytest.raises(ValueError):
        signed_ticket.issue(SECRET, "scope", ttl_seconds=0)
