"""Tests für ``evidence_migrations.migrate_v1_to_v2`` (Sub-Slice 02a, Refs #107)."""

from __future__ import annotations

import copy

from app.services.evidence_migrations import (
    CURRENT_SCHEMA_VERSION,
    migrate_v1_to_v2,
)


def test_current_schema_version_is_2():
    assert CURRENT_SCHEMA_VERSION == 2


def test_migrate_none_returns_none():
    assert migrate_v1_to_v2(None) is None


def test_migrate_v1_lifts_to_v2():
    raw = {
        "schema_version": 1,
        "report_id": "report_abcdef123456",
        "sections": [
            {"section_index": 0, "claims": []},
            {"section_index": 1, "schema_version": 1, "claims": []},
        ],
        "global_evidence": [],
    }

    migrated = migrate_v1_to_v2(raw)

    assert migrated is not None
    assert migrated["schema_version"] == 2
    assert all(s["schema_version"] == 2 for s in migrated["sections"])
    # In-place-Mutation entspricht Plan-Snippet (PLAN.md Teil D.2).
    assert raw["schema_version"] == 2


def test_migrate_v2_is_idempotent():
    raw = {
        "schema_version": 2,
        "report_id": "report_abcdef123456",
        "sections": [{"section_index": 0, "schema_version": 2, "claims": []}],
        "global_evidence": [],
    }
    snapshot = copy.deepcopy(raw)

    migrated = migrate_v1_to_v2(raw)

    assert migrated is raw
    assert migrated == snapshot


def test_migrate_missing_schema_version_treated_as_v1():
    """Alte Reports ohne ``schema_version``-Schlüssel werden als v1 behandelt."""
    raw = {
        "report_id": "report_abcdef123456",
        "sections": [{"section_index": 0}],
        "global_evidence": [],
    }

    migrated = migrate_v1_to_v2(raw)

    assert migrated["schema_version"] == 2
    assert migrated["sections"][0]["schema_version"] == 2


def test_migrate_handles_missing_sections_key():
    raw = {"schema_version": 1, "report_id": "report_abcdef123456"}

    migrated = migrate_v1_to_v2(raw)

    assert migrated["schema_version"] == 2


def test_migrate_handles_null_sections():
    raw = {"schema_version": 1, "sections": None}

    migrated = migrate_v1_to_v2(raw)

    assert migrated["schema_version"] == 2


def test_migrate_round_trip_preserves_claim_payload():
    """Section-/Claim-Felder bleiben unverändert — der Migrator hebt nur das Schema-Tag."""
    raw = {
        "schema_version": 1,
        "report_id": "report_abcdef123456",
        "sections": [
            {
                "section_index": 0,
                "section_title": "Intro",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "demo",
                        "confidence_score": 0.62,
                        "confidence_label": "medium",
                        "evidence": [
                            {"type": "graph_metric", "source": "simulation_metrics"}
                        ],
                    }
                ],
            }
        ],
        "global_evidence": [],
    }
    expected_claim = copy.deepcopy(raw["sections"][0]["claims"][0])

    migrated = migrate_v1_to_v2(raw)

    assert migrated["sections"][0]["claims"][0] == expected_claim
