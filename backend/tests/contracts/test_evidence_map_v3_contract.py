"""Referenzielle Integrität der EvidenceMap v3."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.contracts import EvidenceMapModel


EVIDENCE_ID = "ev_0123456789abcdef0123456789abcdef"
UNKNOWN_ID = "ev_ffffffffffffffffffffffffffffffff"


def _evidence_map_payload() -> dict:
    return {
        "schema_version": 3,
        "report_id": "report-17",
        "simulation_id": "run-17",
        "evidence_index": {
            EVIDENCE_ID: {
                "evidence_id": EVIDENCE_ID,
                "producer_key": "graph-node:node-17",
                "type": "graph_fact",
                "source": "report_tool",
                "snippet": "Der Graph enthält einen belastbaren Fakt.",
                "source_kind": "graph_relation",
            }
        },
        "global_evidence_refs": [EVIDENCE_ID],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Wirkungsanalyse",
                "section_summary": "Zusammenfassung der beobachteten Wirkung.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Die Zielgruppe reagiert positiv auf den Ansatz.",
                        "confidence_label": "low",
                        "confidence_score": 0.4,
                        "evidence": [
                            {
                                "evidence_id": EVIDENCE_ID,
                                "match_score": 0.7,
                                "retrieval_score": 0.6,
                                "entailment": "RELATED_ONLY",
                                "supports_claim": False,
                                "contradicts_claim": False,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_evidence_map_v3_resolves_global_and_claim_bindings() -> None:
    evidence_map = EvidenceMapModel.model_validate(_evidence_map_payload())

    assert evidence_map.schema_version == 3
    assert evidence_map.global_evidence_refs == [EVIDENCE_ID]
    assert evidence_map.sections[0].claims[0].evidence[0].evidence_id == EVIDENCE_ID


def test_evidence_map_v3_rejects_mismatched_or_unknown_ids() -> None:
    mismatched_key = _evidence_map_payload()
    mismatched_key["evidence_index"] = {
        UNKNOWN_ID: deepcopy(mismatched_key["evidence_index"])[EVIDENCE_ID]
    }
    with pytest.raises(ValidationError, match="evidence_id"):
        EvidenceMapModel.model_validate(mismatched_key)

    unknown_global = _evidence_map_payload()
    unknown_global["global_evidence_refs"] = [UNKNOWN_ID]
    with pytest.raises(ValidationError, match="unbekannt|auflös|evidence"):
        EvidenceMapModel.model_validate(unknown_global)

    unknown_claim = _evidence_map_payload()
    unknown_claim["sections"][0]["claims"][0]["evidence"][0]["evidence_id"] = UNKNOWN_ID
    with pytest.raises(ValidationError, match="unbekannt|auflös|evidence"):
        EvidenceMapModel.model_validate(unknown_claim)
