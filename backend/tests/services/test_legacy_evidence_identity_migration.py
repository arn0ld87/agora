"""Legacy-Evidence ohne rekonstruierbare Identität bleibt unbelegt."""

from app.services.evidence_migrations import migrate_v2_to_v3


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
