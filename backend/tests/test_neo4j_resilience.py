"""
Tests for Neo4j connection resilience — retry logic and health-state tracking.

Strategy: instantiate Neo4jStorage via ``object.__new__`` to bypass the real
driver/connectivity check, then inject a mock driver and call ``_call_with_retry``
directly.  ``time.sleep`` is always patched to keep the test suite fast.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from neo4j.exceptions import ServiceUnavailable, SessionExpired, TransientError

from app.storage.neo4j_storage import Neo4jStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage():
    """Return a Neo4jStorage instance with no real driver or schema."""
    inst = object.__new__(Neo4jStorage)
    inst._is_connected = True
    inst._last_error = None
    inst._last_success_ts = None
    inst._driver = MagicMock()
    return inst


# ---------------------------------------------------------------------------
# Test 1: transient failure 2x then success
# ---------------------------------------------------------------------------


def test_retry_succeeds_after_two_transient_failures(storage):
    """ServiceUnavailable on attempts 1 and 2; success on attempt 3."""
    sentinel = object()
    side_effects = [
        ServiceUnavailable("neo4j down"),
        ServiceUnavailable("neo4j still down"),
        sentinel,  # success on third attempt
    ]

    mock_func = MagicMock(side_effect=side_effects)

    with patch("app.utils.retry.time.sleep"):
        result = storage._call_with_retry(mock_func)

    assert result is sentinel, "Expected the successful return value"
    assert mock_func.call_count == 3, "Should have attempted exactly 3 times"


# ---------------------------------------------------------------------------
# Test 2: permanent failure raises after max retries
# ---------------------------------------------------------------------------


def test_permanent_failure_raises_after_max_retries(storage):
    """Every call raises ServiceUnavailable → exception propagates after MAX_RETRIES."""
    mock_func = MagicMock(side_effect=ServiceUnavailable("permanent failure"))

    with patch("app.utils.retry.time.sleep"):
        with pytest.raises(ServiceUnavailable):
            storage._call_with_retry(mock_func)

    assert mock_func.call_count == Neo4jStorage.MAX_RETRIES + 1, (
        f"Expected exactly {Neo4jStorage.MAX_RETRIES + 1} attempts"
    )


# ---------------------------------------------------------------------------
# Test 3: is_connected reflects recovery
# ---------------------------------------------------------------------------


def test_is_connected_updates_after_failure_and_recovery(storage):
    """
    After a permanent failure ``is_connected`` is False;
    after a subsequent success it flips back to True.
    """
    always_fail = MagicMock(side_effect=ServiceUnavailable("down"))

    with patch("app.utils.retry.time.sleep"):
        with pytest.raises(ServiceUnavailable):
            storage._call_with_retry(always_fail)

    assert storage.is_connected is False, "Should report disconnected after failure"
    assert storage.last_error is not None, "last_error should be set"

    # Now simulate recovery
    success_func = MagicMock(return_value="ok")
    result = storage._call_with_retry(success_func)

    assert result == "ok"
    assert storage.is_connected is True, "Should report connected after success"
    assert storage.last_error is None, "last_error should be cleared on success"
    assert isinstance(storage.last_success_ts, datetime), (
        "last_success_ts should be set to a datetime after success"
    )
    assert storage.last_success_ts.tzinfo is not None, (
        "last_success_ts must be timezone-aware (UTC)"
    )


# ---------------------------------------------------------------------------
# Test 4: non-transient exception is NOT retried
# ---------------------------------------------------------------------------


def test_non_transient_exception_is_not_retried(storage):
    """A plain ValueError must propagate immediately without any retry."""
    mock_func = MagicMock(side_effect=ValueError("bad query"))

    with patch("app.utils.retry.time.sleep") as mock_sleep:
        with pytest.raises(ValueError):
            storage._call_with_retry(mock_func)

    assert mock_func.call_count == 1, "Non-transient error must not be retried"
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: SessionExpired and TransientError are also retried
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("exc_type", [SessionExpired, TransientError])
def test_session_expired_and_transient_error_are_retried(storage, exc_type):
    """SessionExpired and TransientError should trigger the same retry path."""
    sentinel = "recovered"
    mock_func = MagicMock(side_effect=[exc_type("oops"), sentinel])

    with patch("app.utils.retry.time.sleep"):
        result = storage._call_with_retry(mock_func)

    assert result == sentinel
    assert mock_func.call_count == 2
