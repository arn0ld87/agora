"""Issue #1804 — Response-Envelopes der Berichts-Artefakte.

Die Exklusivität der beiden Fälle (Daten vs. ``artifact_omitted``) setzt der
Vertrag selbst durch, nicht der Consumer — dieselbe Linie wie bei
``EvidenceMapResponseModel`` (#1477).
"""

from __future__ import annotations

import jsonschema
import pytest
from pydantic import ValidationError

from app.contracts.evidence_density_contract import EvidenceDensity
from app.contracts.report_artifact_contract import (
    EvidenceDensityResponseModel,
    ReportArtifactOmissionModel,
    StanceAnalysisResponseModel,
)
from app.contracts.stance_analysis_contract import StanceAnalysis

MODELS = [
    (EvidenceDensityResponseModel, EvidenceDensity(), "evidence_density"),
    (StanceAnalysisResponseModel, StanceAnalysis(applicable=False), "stance_analysis"),
]


def _omission(artifact: str) -> ReportArtifactOmissionModel:
    return ReportArtifactOmissionModel(
        artifact=artifact,  # type: ignore[arg-type]
        reason="contract_violation",
        detail="Testfall.",
    )


@pytest.mark.parametrize(("model", "data", "artifact"), MODELS)
class TestResponseEnvelopeIsAUnion:
    def test_success_variant_dumps_only_data(self, model, data, artifact) -> None:
        payload = model.for_data(data).to_payload()
        assert payload["success"] is True
        assert "data" in payload
        assert "artifact_omitted" not in payload

    def test_omission_variant_dumps_only_artifact_omitted(self, model, data, artifact) -> None:
        payload = model.for_omission(_omission(artifact)).to_payload()
        assert payload["success"] is True
        assert "data" not in payload
        assert payload["artifact_omitted"]["artifact"] == artifact
        # Der Vertrag entscheidet, dass validation_errors nie fehlt.
        assert payload["artifact_omitted"]["validation_errors"] == []

    def test_neither_variant_is_rejected(self, model, data, artifact) -> None:
        with pytest.raises(ValidationError):
            model.model_validate({"success": True})

    def test_both_variants_at_once_are_rejected(self, model, data, artifact) -> None:
        payload = {
            "success": True,
            "data": data.model_dump(mode="json"),
            "artifact_omitted": _omission(artifact).model_dump(mode="json"),
        }
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    def test_missing_success_key_is_rejected(self, model, data, artifact) -> None:
        with pytest.raises(ValidationError):
            model.model_validate({"data": data.model_dump(mode="json")})

    def test_json_schema_is_one_of_and_requires_success(self, model, data, artifact) -> None:
        schema = model.model_json_schema()
        assert "oneOf" in schema and "anyOf" not in schema
        for variant in schema["oneOf"]:
            ref = variant["$ref"].split("/")[-1]
            assert "success" in schema["$defs"][ref]["required"]

    def test_wire_form_validates_against_the_json_schema(self, model, data, artifact) -> None:
        schema = model.model_json_schema()
        jsonschema.validate(model.for_data(data).to_payload(), schema)
        jsonschema.validate(model.for_omission(_omission(artifact)).to_payload(), schema)


def test_omission_rejects_more_than_five_validation_errors() -> None:
    with pytest.raises(ValidationError):
        ReportArtifactOmissionModel(
            artifact="evidence_density",
            reason="contract_violation",
            detail="x",
            validation_errors=[str(i) for i in range(6)],
        )
