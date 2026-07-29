"""Tests für ``evidence_migrations.migrate_v1_to_v2`` (Sub-Slice 02a, Refs #107)
und ``migrate_medium_seed_only_claims_to_low`` (Issue #963)."""

from __future__ import annotations

import copy

from app.services.evidence_migrations import (
    CURRENT_SCHEMA_VERSION,
    migrate_medium_seed_only_claims_to_low,
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


# ---------------------------------------------------------------------------
# migrate_medium_seed_only_claims_to_low (Issue #963)
# ---------------------------------------------------------------------------


def _seed_only_map(claims):
    return {
        "schema_version": 2,
        "report_id": "report_abcdef123456",
        "sections": [
            {
                "section_index": 1,
                "section_title": "Kontext",
                "claims": claims,
                "hypotheses": [],
                "data_gaps": [],
            }
        ],
        "global_evidence": [],
    }


def _claim(label, evidence):
    return {
        "claim_id": "claim_01",
        "claim_text": "Nutzer bevorzugen A.",
        "confidence_label": label,
        "evidence": evidence,
    }


_SEED = {"source_kind": "seed_corpus", "source": "seed"}
_GRAPH = {"source_kind": "graph_relation", "source": "graph"}
_QUOTE = {"source_kind": "agent_quote", "quote": "Wörtliches Zitat."}
_QUOTE_EMPTY = {"source_kind": "agent_quote", "quote": ""}
_QUOTE_MISSING = {"source_kind": "agent_quote"}


def test_medium_seed_only_claim_becomes_low():
    raw = _seed_only_map([_claim("medium", [_SEED])])

    migrated = migrate_medium_seed_only_claims_to_low(raw)

    assert migrated["sections"][0]["claims"][0]["confidence_label"] == "low"


def test_medium_graph_relation_only_claim_becomes_low():
    raw = _seed_only_map([_claim("medium", [_GRAPH])])

    migrated = migrate_medium_seed_only_claims_to_low(raw)

    assert migrated["sections"][0]["claims"][0]["confidence_label"] == "low"


def test_medium_quote_without_quote_field_becomes_low():
    for quote_evidence in (_QUOTE_EMPTY, _QUOTE_MISSING):
        raw = _seed_only_map([_claim("medium", [quote_evidence, _SEED])])

        migrated = migrate_medium_seed_only_claims_to_low(raw)

        assert migrated["sections"][0]["claims"][0]["confidence_label"] == "low"


def test_medium_agent_grounded_claim_stays_medium():
    raw = _seed_only_map([_claim("medium", [_QUOTE, _SEED])])

    migrated = migrate_medium_seed_only_claims_to_low(raw)

    assert migrated["sections"][0]["claims"][0]["confidence_label"] == "medium"


def test_medium_label_matching_is_case_insensitive():
    raw = _seed_only_map([_claim("Medium", [_SEED]), _claim("MEDIUM", [_QUOTE, _SEED])])

    migrated = migrate_medium_seed_only_claims_to_low(raw)

    claims = migrated["sections"][0]["claims"]
    assert claims[0]["confidence_label"] == "low"
    assert claims[1]["confidence_label"] == "MEDIUM"


def test_migrate_medium_seed_only_is_idempotent():
    raw = _seed_only_map([_claim("medium", [_SEED]), _claim("medium", [_QUOTE, _SEED])])
    once = migrate_medium_seed_only_claims_to_low(copy.deepcopy(raw))

    twice = migrate_medium_seed_only_claims_to_low(copy.deepcopy(once))

    assert twice == once


def test_migrate_medium_seed_only_none_returns_none():
    assert migrate_medium_seed_only_claims_to_low(None) is None


def test_migrate_medium_seed_only_keeps_non_dict_claims_untouched():
    raw = _seed_only_map(["not-a-dict-claim", _claim("medium", [_SEED])])

    migrated = migrate_medium_seed_only_claims_to_low(raw)

    claims = migrated["sections"][0]["claims"]
    assert claims[0] == "not-a-dict-claim"
    assert claims[1]["confidence_label"] == "low"


def test_migrate_medium_seed_only_ignores_high_and_verified_claims():
    raw = _seed_only_map([_claim("high", [_SEED]), _claim("verified", [_GRAPH])])

    migrated = migrate_medium_seed_only_claims_to_low(raw)

    claims = migrated["sections"][0]["claims"]
    assert claims[0]["confidence_label"] == "high"
    assert claims[1]["confidence_label"] == "verified"


def test_migrate_medium_seed_only_skips_non_dict_sections():
    raw = {"schema_version": 2, "sections": ["not-a-dict-section", None]}

    migrated = migrate_medium_seed_only_claims_to_low(raw)

    assert migrated["sections"] == ["not-a-dict-section", None]
