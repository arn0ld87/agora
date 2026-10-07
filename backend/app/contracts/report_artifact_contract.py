"""Antwort-Envelopes der Berichts-Artefakte (Issue #1804, Etappe 5).

``evidence_density.json`` (#1779) und ``stance_analysis.json`` (#1778) liegen je
Bericht im Berichtsordner. Diese Modelle fixieren die Wire-Form der beiden
lesenden Endpunkte ``GET /api/report/<id>/evidence-density`` und
``GET /api/report/<id>/stance-analysis``.

Dieselbe Linie wie ``EvidenceMapResponseModel``: genau zwei Varianten, jede mit
genau einem Pflichtfeld. Ist die gespeicherte Datei vertragswidrig, antwortet
der Endpunkt mit HTTP 200 und ``artifact_omitted`` statt mit leeren Zahlen —
ein Altbestand, der den Vertrag verletzt, ist von einem Bericht ohne Daten
sonst nicht zu unterscheiden. Eine fehlende Datei ist dagegen HTTP 404 (wie
bei einer fehlenden Evidence-Map).
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler, RootModel
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .evidence_density_contract import EvidenceDensity
from .stance_analysis_contract import StanceAnalysis

_STRICT = ConfigDict(extra="forbid")

#: Welches Artefakt nicht ausgeliefert werden konnte.
ReportArtifactKind = Literal["evidence_density", "stance_analysis"]


class ReportArtifactOmissionModel(BaseModel):
    """Warum ein Berichts-Artefakt nicht ausgeliefert wurde.

    Gesetzt genau dann, wenn die Datei vorliegt, aber den Vertrag verletzt
    (beschädigtes JSON oder Schemaverstoß). ``reason`` ist der stabile
    Schlüssel, aus dem die Oberfläche per vue-i18n übersetzt; ``detail`` ist
    kein UI-Text.
    """

    model_config = _STRICT

    artifact: ReportArtifactKind
    reason: Literal["contract_violation"]
    detail: str = Field(min_length=1)
    #: Die ersten Validierungsfehler als ``loc: msg`` — belegt die Einstufung,
    #: ohne die verworfenen Rohdaten mitzuliefern.
    validation_errors: list[str] = Field(default_factory=list, max_length=5)


def _as_one_of(schema: JsonSchemaValue) -> JsonSchemaValue:
    # Zwei Varianten mit disjunkten Pflichtfeldern: ``oneOf`` ist die präzisere
    # Aussage als Pydantics Standard ``anyOf`` (siehe EvidenceMapResponseModel).
    if "anyOf" in schema:
        schema["oneOf"] = schema.pop("anyOf")
    return schema


class EvidenceDensityResponseSuccessVariant(BaseModel):
    """Erfolgsvariante von ``EvidenceDensityResponseModel``."""

    model_config = _STRICT
    success: Literal[True] = Field(
        description="Pflichtfeld ohne Default, damit es im JSON-Schema in `required` steht.",
    )
    data: EvidenceDensity


class EvidenceDensityResponseOmittedVariant(BaseModel):
    """Degradations-Variante von ``EvidenceDensityResponseModel``."""

    model_config = _STRICT
    success: Literal[True] = Field(
        description="Pflichtfeld ohne Default, damit es im JSON-Schema in `required` steht.",
    )
    artifact_omitted: ReportArtifactOmissionModel


class EvidenceDensityResponseModel(
    RootModel[Union[EvidenceDensityResponseSuccessVariant, EvidenceDensityResponseOmittedVariant]]
):
    """Envelope für ``GET /api/report/<id>/evidence-density``."""

    root: Union[EvidenceDensityResponseSuccessVariant, EvidenceDensityResponseOmittedVariant]

    @classmethod
    def for_data(cls, data: EvidenceDensity) -> "EvidenceDensityResponseModel":
        return cls(root=EvidenceDensityResponseSuccessVariant(success=True, data=data))

    @classmethod
    def for_omission(
        cls, artifact_omitted: ReportArtifactOmissionModel
    ) -> "EvidenceDensityResponseModel":
        return cls(
            root=EvidenceDensityResponseOmittedVariant(
                success=True, artifact_omitted=artifact_omitted
            )
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return _as_one_of(handler(core_schema))

    def to_payload(self) -> dict[str, Any]:
        """Wire-Form: nur der gesetzte Top-Level-Schlüssel."""
        return self.root.model_dump(mode="json")


class StanceAnalysisResponseSuccessVariant(BaseModel):
    """Erfolgsvariante von ``StanceAnalysisResponseModel``."""

    model_config = _STRICT
    success: Literal[True] = Field(
        description="Pflichtfeld ohne Default, damit es im JSON-Schema in `required` steht.",
    )
    data: StanceAnalysis


class StanceAnalysisResponseOmittedVariant(BaseModel):
    """Degradations-Variante von ``StanceAnalysisResponseModel``."""

    model_config = _STRICT
    success: Literal[True] = Field(
        description="Pflichtfeld ohne Default, damit es im JSON-Schema in `required` steht.",
    )
    artifact_omitted: ReportArtifactOmissionModel


class StanceAnalysisResponseModel(
    RootModel[Union[StanceAnalysisResponseSuccessVariant, StanceAnalysisResponseOmittedVariant]]
):
    """Envelope für ``GET /api/report/<id>/stance-analysis``."""

    root: Union[StanceAnalysisResponseSuccessVariant, StanceAnalysisResponseOmittedVariant]

    @classmethod
    def for_data(cls, data: StanceAnalysis) -> "StanceAnalysisResponseModel":
        return cls(root=StanceAnalysisResponseSuccessVariant(success=True, data=data))

    @classmethod
    def for_omission(
        cls, artifact_omitted: ReportArtifactOmissionModel
    ) -> "StanceAnalysisResponseModel":
        return cls(
            root=StanceAnalysisResponseOmittedVariant(
                success=True, artifact_omitted=artifact_omitted
            )
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return _as_one_of(handler(core_schema))

    def to_payload(self) -> dict[str, Any]:
        """Wire-Form: nur der gesetzte Top-Level-Schlüssel."""
        return self.root.model_dump(mode="json")


__all__ = [
    "EvidenceDensityResponseModel",
    "EvidenceDensityResponseOmittedVariant",
    "EvidenceDensityResponseSuccessVariant",
    "ReportArtifactKind",
    "ReportArtifactOmissionModel",
    "StanceAnalysisResponseModel",
    "StanceAnalysisResponseOmittedVariant",
    "StanceAnalysisResponseSuccessVariant",
]
