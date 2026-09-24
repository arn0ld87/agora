"""Startvalidierung der Job-Lease-Zeiten (Issue #1472, Codex-P2 PR #1555).

Ein Heartbeat-Intervall von 0 ließe den Loop ohne Pause drehen, eines nahe
der TTL gäbe einen laufenden Job nach einem einzigen verspäteten Tick zum
Doppelstart frei. Beides soll beim Start auffallen, nicht im Betrieb.
"""

from __future__ import annotations

import pytest

from app.config import Config, validate_job_lease_timing


def test_defaults_are_valid():
    assert validate_job_lease_timing(
        Config.AGORA_JOB_LEASE_TTL_SECONDS,
        Config.AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS,
        Config.AGORA_JOB_LEASE_MAX_STALL_SECONDS,
    ) == []


@pytest.mark.parametrize(
    ("ttl", "interval", "stall", "name"),
    [
        (0, 20, 1800, "AGORA_JOB_LEASE_TTL_SECONDS"),
        (90, 0, 1800, "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS"),
        (90, -5, 1800, "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS"),
        (90, 20, 0, "AGORA_JOB_LEASE_MAX_STALL_SECONDS"),
    ],
)
def test_non_positive_values_are_rejected(ttl, interval, stall, name):
    errors = validate_job_lease_timing(ttl, interval, stall)
    assert len(errors) == 1
    assert name in errors[0]
    assert "> 0" in errors[0]


@pytest.mark.parametrize(("ttl", "interval"), [(90, 46), (90, 90), (30, 20)])
def test_interval_above_half_the_ttl_is_rejected(ttl, interval):
    errors = validate_job_lease_timing(ttl, interval, 1800)
    assert len(errors) == 1
    assert "at most half" in errors[0]


def test_interval_exactly_half_the_ttl_is_accepted():
    assert validate_job_lease_timing(90, 45, 1800) == []


def test_config_validate_reports_invalid_lease_timing(monkeypatch):
    monkeypatch.setattr(Config, "AGORA_JOB_LEASE_TTL_SECONDS", 30)
    monkeypatch.setattr(Config, "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS", 20)

    errors = Config.validate()

    assert any("AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS" in e for e in errors)
