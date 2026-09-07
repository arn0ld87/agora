"""Issue #1477 F1 — Response-Envelope fuer ``GET /api/report/<id>/evidence``.

Vorher stand diese Envelope-Form nur als handgeschriebenes TypeScript-
Interface (``EvidenceOmittedEnvelope`` in ``frontend/src/api/report.ts``).
Die Schema-Generierung kannte diese API-Grenze nicht, und ein fehlendes
``validation_errors`` haette den ``.length``-Zugriff im Template ungeprueft
erreicht. Dieser Test stellt sicher, dass ``EvidenceMapResponseModel`` die
Union beider Faelle (Erfolg vs. Degradierung) selbst durchsetzt — nicht der
Consumer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    EvidenceMapModel,
    EvidenceMapResponseModel,
    EvidenceOmissionModel,
)


def _minimal_evidence_map() -> EvidenceMapModel:
    return EvidenceMapModel(report_id="report_0001", simulation_id="sim_0001")


def _omission() -> EvidenceOmissionModel:
    return EvidenceOmissionModel(reason="contract_violation", detail="Testfall.")


class TestEvidenceMapResponseModelIsAUnion:
    def test_success_variant_dumps_without_evidence_omitted_key(self) -> None:
        envelope = EvidenceMapResponseModel(data=_minimal_evidence_map())
        dumped = envelope.model_dump(mode="json", exclude_none=True)
        assert "data" in dumped
        assert "evidence_omitted" not in dumped

    def test_omission_variant_dumps_without_data_key(self) -> None:
        envelope = EvidenceMapResponseModel(evidence_omitted=_omission())
        dumped = envelope.model_dump(mode="json", exclude_none=True)
        assert "evidence_omitted" in dumped
        assert "data" not in dumped
        # Issue #1477 F1: der Contract entscheidet, dass validation_errors
        # nie fehlt (default_factory=list), nicht das Template mit `?.`.
        assert dumped["evidence_omitted"]["validation_errors"] == []

    def test_neither_data_nor_evidence_omitted_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceMapResponseModel()

    def test_both_data_and_evidence_omitted_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceMapResponseModel(data=_minimal_evidence_map(), evidence_omitted=_omission())
