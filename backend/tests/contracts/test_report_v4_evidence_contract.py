"""ReportV3-v4-Vertrag für eingebettete, auflösbare Evidence-Referenzen."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.contracts.report_v3 import ReportV3


EVIDENCE_ID = "ev_0123456789abcdef0123456789abcdef"
UNKNOWN_ID = "ev_ffffffffffffffffffffffffffffffff"


def _base_report() -> dict[str, object]:
    return {
        "schema_version": 4,
        "report_id": "report-17",
        "generated_at": "2026-08-09T10:00:00Z",
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
    }


REF_DTO_PAYLOADS: tuple[tuple[str, dict[str, object]], ...] = (
    (
        "personas",
        {
            "id": "persona-1",
            "voice_register": "neutral-de",
            "alter_range": "35–50",
            "beruf": "Projektleitung",
            "region": "DACH",
        },
    ),
    (
        "claims",
        {
            "id": "claim-1",
            "statement": "Die Zielgruppe reagiert positiv auf den Ansatz.",
            "confidence": "low",
            "aggregation_basis": "persona",
        },
    ),
    (
        "multipliers",
        {
            "id": "multiplier-1",
            "name": "Empfehlungen",
            "kategorie": "awareness",
            "reichweite_score": 6,
        },
    ),
    (
        "friction_points",
        {
            "id": "friction-1",
            "beschreibung": "Unklare Zuständigkeiten erschweren die Einführung.",
            "severity": "medium",
        },
    ),
    (
        "trust_signals",
        {
            "id": "trust-1",
            "beschreibung": "Ein unabhängiges Prüfsiegel erhöht das Vertrauen.",
            "signal_type": "authority",
        },
    ),
    (
        "change_recommendations",
        {
            "id": "change-1",
            "titel": "Zuständigkeiten klären",
            "beschreibung": "Verantwortlichkeiten werden sichtbar dokumentiert.",
            "priority": "high",
            "aufwand": "S",
        },
    ),
    (
        "project_impacts",
        {
            "id": "impact-1",
            "beschreibung": "Der Ansatz verkürzt die Abstimmungswege.",
            "confidence": "low",
        },
    ),
    (
        "positioning_variants",
        {
            "id": "positioning-1",
            "titel": "Sicher entscheiden",
            "claim_text": "Nachvollziehbare Evidenz für jede Entscheidung.",
        },
    ),
    (
        "content_ideas",
        {
            "id": "content-1",
            "titel": "Evidence Walkthrough",
            "format": "video",
        },
    ),
)


def _report_with_all_reference_dtos(evidence_id: str) -> dict[str, object]:
    payload = _base_report()
    for collection, dto in REF_DTO_PAYLOADS:
        payload[collection] = [deepcopy(dto) | {"evidence_refs": [evidence_id]}]
    return payload


def test_report_v3_uses_schema_version_four_and_embeds_evidence_index() -> None:
    report = ReportV3.model_validate(_report_with_all_reference_dtos(EVIDENCE_ID))

    assert report.schema_version == 4
    assert report.evidence_index[EVIDENCE_ID].evidence_id == EVIDENCE_ID


    previous_version = _base_report()
    previous_version["schema_version"] = 3
    with pytest.raises(ValidationError, match="schema_version"):
        ReportV3.model_validate(previous_version)


def test_report_v3_rejects_mismatched_evidence_index_key() -> None:
    payload = _base_report()
    record = payload["evidence_index"].pop(EVIDENCE_ID)
    payload["evidence_index"][UNKNOWN_ID] = record

    with pytest.raises(ValidationError, match="evidence_index-Key"):
        ReportV3.model_validate(payload)


def test_report_v3_rejects_unknown_evidence_refs_for_every_ref_dto() -> None:
    for collection, dto in REF_DTO_PAYLOADS:
        payload = _base_report()
        payload[collection] = [deepcopy(dto) | {"evidence_refs": [UNKNOWN_ID]}]
        with pytest.raises(
            ValidationError,
            match="unbekannt|auflös|evidence_refs",
        ):
            ReportV3.model_validate(payload)
