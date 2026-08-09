"""Legacy-Evidence ohne rekonstruierbare Identität bleibt unbelegt."""

from app.services.evidence_identity import build_evidence_id
from app.services.evidence_migrations import (
    migrate_evidence_map_v2_to_v3,
    migrate_v2_to_v3,
    normalize_persisted_evidence_map,
)


def _legacy_report_tool_payload() -> dict:
    return {
        "schema_version": 2,
        "report_id": "legacy-report-17",
        "simulation_id": "run-17",
        "sections": [
            {
                "section_index": 1,
                "section_title": "Wirkungsanalyse",
                "section_summary": "Legacy-Abschnitt.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Die Zielgruppe reagiert positiv auf den Ansatz.",
                        "confidence_label": "low",
                        "confidence_score": 0.4,
                        "evidence": [
                            {
                                "type": "graph_fact",
                                "source": "report_tool",
                                "snippet": "LLM-generierter Auszug ohne stabilen Quellschlüssel.",
                                "source_kind": "graph_relation",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_legacy_report_tool_becomes_unresolved_hypothesis_not_claim() -> None:
    migrated = migrate_v2_to_v3(_legacy_report_tool_payload())

    assert migrated["claims"] == []
    assert migrated["evidence_index"] == {}
    assert any(
        hypothesis["hypothesis_text"]
        == "Die Zielgruppe reagiert positiv auf den Ansatz."
        and "legacy_unresolved" in hypothesis["rationale"]
        for hypothesis in migrated["hypotheses"]
    )


def test_short_legacy_claim_is_not_promoted_to_hypothesis() -> None:
    payload = _legacy_report_tool_payload()
    payload["sections"][0]["claims"][0]["claim_text"] = "kurz"

    migrated = migrate_evidence_map_v2_to_v3(payload)
    section = migrated["sections"][0]

    assert section["claims"] == []
    assert section["hypotheses"] == []


def test_missing_legacy_snippet_gets_explicit_placeholder() -> None:
    payload = _legacy_report_tool_payload()
    item = payload["sections"][0]["claims"][0]["evidence"][0]
    item.pop("snippet")
    item["producer_key"] = "graph-node:legacy-17"

    migrated = migrate_evidence_map_v2_to_v3(payload)
    record = next(iter(migrated["evidence_index"].values()))

    assert record["snippet"] == "[legacy evidence snippet missing]"


def test_current_map_resolves_global_evidence_additively() -> None:
    scope_id = "sim-current-17"
    existing_id = build_evidence_id(scope_id, "graph_relation", "graph-node:existing")
    global_id = build_evidence_id(scope_id, "graph_relation", "graph-node:global")
    payload = {
        "schema_version": 3,
        "report_id": "report-current-17",
        "simulation_id": scope_id,
        "evidence_index": {
            existing_id: {
                "evidence_id": existing_id,
                "producer_key": "graph-node:existing",
                "type": "graph_fact",
                "source": "graph",
                "snippet": "Bestehender Record.",
                "source_kind": "graph_relation",
            }
        },
        "global_evidence_refs": [],
        "global_evidence": [
            {
                "producer_key": "graph-node:global",
                "type": "graph_fact",
                "source": "graph",
                "snippet": "Globaler Record.",
                "source_kind": "graph_relation",
            }
        ],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Bestehend",
                "section_summary": "Bestehende Section bleibt unverändert.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Bestehende Bindung bleibt vollständig erhalten.",
                        "confidence_label": "low",
                        "confidence_score": 0.4,
                        "evidence": [
                            {"evidence_id": existing_id, "supports_claim": True}
                        ],
                    }
                ],
            }
        ],
    }

    normalized = normalize_persisted_evidence_map(payload)

    assert normalized["schema_version"] == 3
    assert normalized["sections"][0]["claims"][0]["evidence"][0]["evidence_id"] == existing_id
    assert normalized["evidence_index"][existing_id]["snippet"] == "Bestehender Record."
    assert normalized["evidence_index"][global_id]["snippet"] == "Globaler Record."
    assert normalized["global_evidence_refs"] == [global_id]
    assert "global_evidence" not in normalized
