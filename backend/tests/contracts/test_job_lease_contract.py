"""Tests für ``JobLease`` (Issue #1472, Architekturentscheidung 2026-09-24).

Reiner Contract-Test: Ablauf-Arithmetik, Metadata-Round-Trip,
Rückwärtskompatibilität mit dem alten PID+Token-Stempel.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.contracts.job_lease_contract import (
    DEFAULT_LEASE_TTL_S,
    HEARTBEAT_AT_KEY,
    LEASE_TTL_KEY,
    OWNER_PID_KEY,
    OWNER_TOKEN_KEY,
    JobLease,
)
from app.jobs.identity import WORKER_PID_KEY, WORKER_TOKEN_KEY


def _lease(**overrides) -> JobLease:
    defaults = dict(
        owner_pid=4242,
        owner_token="tok-abc",
        heartbeat_at=datetime.now(UTC),
        lease_ttl_s=90,
    )
    defaults.update(overrides)
    return JobLease(**defaults)


class TestMetadataKeysStaySynchronizedWithIdentity:
    """``app.jobs.identity`` bleibt die Quelle der PID/Token-Manifest-Keys —
    dieser Test haelt beide Konstantenmengen synchron, ohne dass
    ``contracts/`` von ``jobs/`` importieren muss (siehe Moduldocstring von
    ``job_lease_contract.py``)."""

    def test_owner_pid_key_matches_worker_pid_key(self) -> None:
        assert OWNER_PID_KEY == WORKER_PID_KEY

    def test_owner_token_key_matches_worker_token_key(self) -> None:
        assert OWNER_TOKEN_KEY == WORKER_TOKEN_KEY


class TestIsExpired:
    def test_fresh_heartbeat_is_not_expired(self) -> None:
        lease = _lease(heartbeat_at=datetime.now(UTC), lease_ttl_s=90)
        assert lease.is_expired() is False

    def test_heartbeat_older_than_ttl_is_expired(self) -> None:
        lease = _lease(
            heartbeat_at=datetime.now(UTC) - timedelta(seconds=999), lease_ttl_s=90
        )
        assert lease.is_expired() is True

    def test_boundary_is_treated_as_not_yet_expired(self) -> None:
        """Exakt an der TTL-Grenze zaehlt noch als gueltig (>, nicht >=)."""
        now = datetime.now(UTC)
        lease = _lease(heartbeat_at=now - timedelta(seconds=90), lease_ttl_s=90)
        assert lease.is_expired(now=now) is False

    def test_one_second_past_the_boundary_is_expired(self) -> None:
        now = datetime.now(UTC)
        lease = _lease(heartbeat_at=now - timedelta(seconds=91), lease_ttl_s=90)
        assert lease.is_expired(now=now) is True

    def test_injected_now_is_used_instead_of_the_wall_clock(self) -> None:
        """Fake-Clock statt echtem Sleep — deterministisch testbar."""
        heartbeat = datetime(2026, 1, 1, tzinfo=UTC)
        lease = _lease(heartbeat_at=heartbeat, lease_ttl_s=60)

        just_inside = heartbeat + timedelta(seconds=59)
        just_outside = heartbeat + timedelta(seconds=61)

        assert lease.is_expired(now=just_inside) is False
        assert lease.is_expired(now=just_outside) is True


class TestMetadataRoundTrip:
    def test_to_metadata_uses_the_legacy_keys_for_pid_and_token(self) -> None:
        lease = _lease(owner_pid=777, owner_token="tok-xyz")
        metadata = lease.to_metadata()

        assert metadata[OWNER_PID_KEY] == 777
        assert metadata[OWNER_TOKEN_KEY] == "tok-xyz"
        assert HEARTBEAT_AT_KEY in metadata
        assert metadata[LEASE_TTL_KEY] == lease.lease_ttl_s

    def test_from_metadata_round_trips(self) -> None:
        original = _lease()
        parsed = JobLease.from_metadata(original.to_metadata())

        assert parsed is not None
        assert parsed.owner_pid == original.owner_pid
        assert parsed.owner_token == original.owner_token
        assert parsed.lease_ttl_s == original.lease_ttl_s
        assert parsed.heartbeat_at == original.heartbeat_at

    def test_from_metadata_none_returns_none(self) -> None:
        assert JobLease.from_metadata(None) is None

    def test_from_metadata_empty_dict_returns_none(self) -> None:
        assert JobLease.from_metadata({}) is None

    def test_legacy_stamp_without_heartbeat_returns_none(self) -> None:
        """Rückwärtskompatibilität (Anforderung 5): ein Manifest aus der Zeit
        vor diesem Slice trägt nur den PID+Token-Stempel — kein Parse-Fehler,
        sondern der erwartete "keine Lease-Semantik"-Fall."""
        legacy_metadata = {OWNER_PID_KEY: 123, OWNER_TOKEN_KEY: "old-token"}

        assert JobLease.from_metadata(legacy_metadata) is None

    def test_malformed_lease_data_returns_none_instead_of_raising(self) -> None:
        broken_metadata = {
            OWNER_PID_KEY: "not-an-int",
            OWNER_TOKEN_KEY: "tok",
            HEARTBEAT_AT_KEY: "not-a-timestamp",
            LEASE_TTL_KEY: 90,
        }

        assert JobLease.from_metadata(broken_metadata) is None


class TestValidation:
    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JobLease(
                owner_pid=1,
                owner_token="t",
                heartbeat_at=datetime.now(UTC),
                lease_ttl_s=1,
                unexpected="nope",
            )

    def test_non_positive_ttl_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _lease(lease_ttl_s=0)

    def test_default_ttl_is_positive(self) -> None:
        assert DEFAULT_LEASE_TTL_S > 0
