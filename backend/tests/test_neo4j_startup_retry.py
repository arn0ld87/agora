"""
Tests for Neo4jStorage startup-time connectivity retry.

When the Neo4j container is still warming up (Bolt-port not yet listening)
the driver raises ServiceUnavailable on the very first ``verify_connectivity``
call. Without retry the Flask app boots with ``neo4j_storage = None`` for
the entire process lifetime — the UI shows "Neo4j AUS" until manual restart.

Strategy: patch ``GraphDatabase.driver`` to return a MagicMock whose
``verify_connectivity`` raises ServiceUnavailable N times before succeeding.
"""

import pytest
from unittest.mock import MagicMock, patch
from neo4j.exceptions import ServiceUnavailable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_driver_mock(failures_before_success: int):
    """Driver mock whose verify_connectivity fails N times, then succeeds."""
    driver = MagicMock()
    side_effects = [ServiceUnavailable("Connection refused")] * failures_before_success
    side_effects.append(None)  # final success returns None
    driver.verify_connectivity = MagicMock(side_effect=side_effects)
    return driver


# ---------------------------------------------------------------------------
# Test 1: transient connect-refused — retry until success
# ---------------------------------------------------------------------------


def test_verify_connectivity_retries_until_success(monkeypatch):
    """Two ServiceUnavailable failures followed by success → init must succeed."""
    monkeypatch.setenv("NEO4J_STARTUP_RETRY_MAX", "5")
    monkeypatch.setenv("NEO4J_STARTUP_RETRY_DELAY", "0.01")

    from app.storage.neo4j_storage import Neo4jStorage

    inst = object.__new__(Neo4jStorage)
    inst._driver = _make_driver_mock(failures_before_success=2)

    with patch("app.storage.neo4j_storage.time.sleep"):
        inst._verify_connectivity()

    assert inst._driver.verify_connectivity.call_count == 3, (
        "Expected 2 retries + 1 success = 3 attempts"
    )


# ---------------------------------------------------------------------------
# Test 2: permanent failure — give up after configured max
# ---------------------------------------------------------------------------


def test_verify_connectivity_gives_up_after_max_retries(monkeypatch):
    """All attempts fail → ServiceUnavailable propagates after MAX retries."""
    monkeypatch.setenv("NEO4J_STARTUP_RETRY_MAX", "3")
    monkeypatch.setenv("NEO4J_STARTUP_RETRY_DELAY", "0.01")

    from app.storage.neo4j_storage import Neo4jStorage

    inst = object.__new__(Neo4jStorage)
    inst._driver = MagicMock()
    inst._driver.verify_connectivity = MagicMock(
        side_effect=ServiceUnavailable("permanent")
    )

    with patch("app.storage.neo4j_storage.time.sleep"):
        with pytest.raises(ServiceUnavailable):
            inst._verify_connectivity()

    # 1 initial attempt + 3 retries = 4
    assert inst._driver.verify_connectivity.call_count == 4
    inst._driver.close.assert_called()


# ---------------------------------------------------------------------------
# Test 3: non-retryable exception propagates immediately
# ---------------------------------------------------------------------------


def test_verify_connectivity_does_not_retry_auth_errors(monkeypatch):
    """A non-transient error (e.g. ValueError) must NOT trigger retries."""
    monkeypatch.setenv("NEO4J_STARTUP_RETRY_MAX", "5")
    monkeypatch.setenv("NEO4J_STARTUP_RETRY_DELAY", "0.01")

    from app.storage.neo4j_storage import Neo4jStorage

    inst = object.__new__(Neo4jStorage)
    inst._driver = MagicMock()
    inst._driver.verify_connectivity = MagicMock(side_effect=ValueError("bad auth"))

    with patch("app.storage.neo4j_storage.time.sleep") as mock_sleep:
        with pytest.raises(ValueError):
            inst._verify_connectivity()

    assert inst._driver.verify_connectivity.call_count == 1
    mock_sleep.assert_not_called()
