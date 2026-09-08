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
    EvidenceCoverageEntry,
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
        dumped = envelope.to_payload()
        assert "data" in dumped
        assert "evidence_omitted" not in dumped

    def test_omission_variant_dumps_without_data_key(self) -> None:
        envelope = EvidenceMapResponseModel(evidence_omitted=_omission())
        dumped = envelope.to_payload()
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


class TestToPayloadKeepsNestedNulls:
    """``to_payload`` darf nur die ungesetzte TOP-LEVEL-Seite weglassen.

    Ein ``model_dump(exclude_none=True)`` wirkt rekursiv und wuerde die
    ``None``-Felder innerhalb jedes Evidence-Records und jedes
    Coverage-Ledger-Eintrags aus der Antwort entfernen — eine stille
    Wire-Aenderung gegenueber dem frueheren
    ``json_success(validated.model_dump(mode="json"))``.
    """

    @staticmethod
    def _map_with_nullable_ledger_entry() -> EvidenceMapModel:
        return EvidenceMapModel(
            report_id="report_0001",
            simulation_id="sim_0001",
            evidence_coverage_ledger=[
                EvidenceCoverageEntry(
                    source_result_id="result_0001",
                    fact="42 Prozent der Befragten",
                    status="dropped",
                    reason="Dedup-Treffer auf denselben Fakt.",
                )
            ],
        )

    def test_nested_none_fields_survive_the_dump(self) -> None:
        envelope = EvidenceMapResponseModel(data=self._map_with_nullable_ledger_entry())
        entry = envelope.to_payload()["data"]["evidence_coverage_ledger"][0]
        for field in ("normalized_value", "unit", "canonical_evidence_id"):
            assert field in entry, (
                f"'{field}' fehlt in der Wire-Form — to_payload() darf "
                "verschachtelte None-Felder nicht entfernen."
            )
            assert entry[field] is None
