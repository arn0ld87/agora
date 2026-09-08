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


def _cross_stakeholder_payload(group_a: str, group_b: str, *, same_role_family: bool) -> dict:
    """High-Claim mit zwei agent_quote-Bindings, Rollenfamilie steuerbar.

    Review B7: reproduziert das Muster, das `validate_evidence_cross_references`
    bislang ueber den rohen `persona_stakeholder_group`-Wert zaehlte, waehrend
    der Hartanker `cross_stakeholder_for_high` bereits ueber `_role_family_key`
    normalisiert. `same_role_family=True` liefert fuer beide Records dieselbe
    `persona_role_family` — das muss trotz unterschiedlicher Schreibweise des
    Berufstitels als eine Gruppe zaehlen und damit die high-Aussage ablehnen.
    """
    evidence_id_a = "ev_1111111111111111111111111111111a"
    evidence_id_b = "ev_2222222222222222222222222222222b"
    role_family_a = "buergerschaft"
    role_family_b = "buergerschaft" if same_role_family else "verwaltung"
    return {
        "schema_version": 3,
        "report_id": "report-cross-stakeholder",
        "simulation_id": "run-cross-stakeholder",
        "evidence_index": {
            evidence_id_a: {
                "evidence_id": evidence_id_a,
                "producer_key": "agent:persona-a",
                "type": "agent_interview",
                "source": "report_tool",
                "snippet": "Zitat einer Persona.",
                "source_kind": "agent_quote",
                "persona_stakeholder_group": group_a,
                "persona_role_family": role_family_a,
            },
            evidence_id_b: {
                "evidence_id": evidence_id_b,
                "producer_key": "agent:persona-b",
                "type": "agent_interview",
                "source": "report_tool",
                "snippet": "Zitat einer weiteren Persona.",
                "source_kind": "agent_quote",
                "persona_stakeholder_group": group_b,
                "persona_role_family": role_family_b,
            },
        },
        "global_evidence_refs": [evidence_id_a, evidence_id_b],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Wirkungsanalyse",
                "section_summary": "Zusammenfassung der beobachteten Wirkung.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Die Zielgruppe reagiert breit gestuetzt positiv.",
                        "confidence_label": "high",
                        "confidence_score": 0.9,
                        "evidence": [
                            {
                                "evidence_id": evidence_id_a,
                                "match_score": 0.9,
                                "retrieval_score": 0.9,
                                "entailment": "SUPPORTED",
                                "supports_claim": True,
                                "contradicts_claim": False,
                            },
                            {
                                "evidence_id": evidence_id_b,
                                "match_score": 0.9,
                                "retrieval_score": 0.9,
                                "entailment": "SUPPORTED",
                                "supports_claim": True,
                                "contradicts_claim": False,
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_evidence_map_v3_rejects_high_claim_with_same_role_family_variant_spelling() -> None:
    # Review B7: "Bürger" und "bürger " sind derselbe Berufstitel in zwei
    # Schreibweisen UND dieselbe persona_role_family. Der Persistenz-Validator
    # muss das wie der Hartanker `cross_stakeholder_for_high` als eine
    # Stakeholder-Gruppe zaehlen und die high-Aussage ablehnen.
    payload = _cross_stakeholder_payload("Bürger", "bürger ", same_role_family=True)
    with pytest.raises(ValidationError, match="stuetzende Stakeholder-Gruppen"):
        EvidenceMapModel.model_validate(payload)


def test_evidence_map_v3_accepts_high_claim_with_two_distinct_role_families() -> None:
    # Gegenprobe: echte unterschiedliche Rollenfamilien bleiben gueltig.
    payload = _cross_stakeholder_payload("Bürger", "Verwaltungsmitarbeiterin", same_role_family=False)
    evidence_map = EvidenceMapModel.model_validate(payload)
    assert evidence_map.sections[0].claims[0].confidence_label == "high"
