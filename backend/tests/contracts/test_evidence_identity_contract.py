"""Vertragstests für kanonische Evidence-Identität und Claim-Bindings."""

from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError


EVIDENCE_ID = "ev_0123456789abcdef0123456789abcdef"


def _contract(name: str):
    contracts = importlib.import_module("app.contracts")
    return getattr(contracts, name)


def _record_payload() -> dict[str, object]:
    return {
        "evidence_id": EVIDENCE_ID,
        "producer_key": "graph-node:node-17",
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Der Graph enthält einen belastbaren Fakt.",
        "source_kind": "graph_relation",
    }


def test_build_evidence_id_is_deterministic_run_local_and_content_independent() -> None:
    module = importlib.import_module("app.services.evidence_identity")
    build_evidence_id = module.build_evidence_id

    first = build_evidence_id("run-17", "graph_relation", "report-tool:result-1")

    assert first == build_evidence_id(
        "run-17", "graph_relation", "report-tool:result-1"
    )
    assert first != build_evidence_id(
        "run-18", "graph_relation", "report-tool:result-1"
    )
    assert first != build_evidence_id(
        "run-17", "graph_relation", "report-tool:result-2"
    )
    assert len(first) == 35
    assert first.startswith("ev_")
    assert first[3:] == first[3:].lower()
    assert all(character in "0123456789abcdef" for character in first[3:])
    with pytest.raises(TypeError):
        build_evidence_id(
            "run-17",
            "graph_relation",
            "report-tool:result-1",
            snippet="LLM-Text darf keine Identität bilden",
        )


def test_evidence_record_requires_evidence_id_and_producer_key() -> None:
    EvidenceRecordModel = _contract("EvidenceRecordModel")

    for missing_field in ("evidence_id", "producer_key"):
        payload = _record_payload()
        payload.pop(missing_field)
        with pytest.raises(ValidationError, match=missing_field):
            EvidenceRecordModel.model_validate(payload)


def test_claim_binding_owns_claim_relative_fields_and_validates_scores() -> None:
    EvidenceRecordModel = _contract("EvidenceRecordModel")
    ClaimEvidenceBindingModel = _contract("ClaimEvidenceBindingModel")

    with pytest.raises(ValidationError, match="retrieval_score"):
        EvidenceRecordModel.model_validate(_record_payload() | {"retrieval_score": 0.74})

    binding = ClaimEvidenceBindingModel.model_validate(
        {
            "evidence_id": EVIDENCE_ID,
            "match_score": 0.81,
            "retrieval_score": 0.74,
            "entailment": "SUPPORTED",
            "entailment_reason": "Der Quellenfakt stützt den Claim.",
            "supports_claim": True,
            "contradicts_claim": False,
        }
    )
    assert binding.entailment.value == "SUPPORTED"
    assert binding.supports_claim is True

    with pytest.raises(ValidationError, match="retrieval_score"):
        ClaimEvidenceBindingModel.model_validate(
            {"evidence_id": EVIDENCE_ID, "retrieval_score": 1.01}
        )
