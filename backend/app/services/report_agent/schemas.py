from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...contracts import (
    EvidenceMapModel,
    ReportV3,
    Persona,
    Segment,
    Claim,
    Multiplier,
    FrictionPoint,
    TrustSignal,
    ChangeRecommendation,
    ProjectImpact,
    PositioningVariant,
    ContentIdea,
    DataGap,
)
from ..evidence_migrations import CURRENT_SCHEMA_VERSION, migrate_v1_to_v2

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Plan-Response DTO (M11.8d) — strict schema for planning.py::plan_outline()
# ---------------------------------------------------------------------------

class PlanSection(BaseModel):
    """Ein Abschnitt im generierten Report-Outline."""

    model_config = _STRICT

    title: str = Field(min_length=1, description="Abschnittstitel")
    description: str = Field(
        default="—",
        description="Kurze Inhaltsbeschreibung des Abschnitts (mind. 1 Zeichen)",
    )


class PlanResponse(BaseModel):
    """Strukturierte LLM-Antwort für die Report-Outline-Planung.

    Wird als ``schema=PlanResponse`` an :func:`LLMClient.chat_json` übergeben.
    Strict-json_schema-Mode erzwingt dieses Format bei kompatiblen Providern;
    bei Fallback-Providern greift llm_client.py automatisch auf json_object zurück.
    """

    model_config = _STRICT

    title: str = Field(min_length=1, description="Reporttitel")
    summary: str = Field(
        default="—",
        description="Kurze Zusammenfassung des Reports",
    )
    sections: list[PlanSection] = Field(
        default_factory=list,
        description="Liste der geplanten Abschnitte",
    )


# ---------------------------------------------------------------------------
# Section-Metadata DTO (M11.8d) — strict schema for workflow.py section metadata
# ---------------------------------------------------------------------------

class SectionKeyTakeaway(BaseModel):
    """Ein einzelnes Key-Takeaway aus einem Report-Abschnitt."""

    model_config = _STRICT

    statement: str = Field(min_length=1)
    confidence: str = Field(
        default="medium",
        description="Einschätzungsqualität: low | medium | high",
    )


class SectionMetadata(BaseModel):
    """Strukturierte Metadaten zu einem generierten Report-Abschnitt.

    Wird via ``chat_json(schema=SectionMetadata)`` aus dem Markdown-Text
    des ReACT-generierten Abschnitts extrahiert.
    """

    model_config = _STRICT

    section_title: str = Field(min_length=1)
    key_takeaways: list[SectionKeyTakeaway] = Field(
        default_factory=list,
        description="Zentrale Erkenntnisse des Abschnitts (max. 5)",
    )
    data_gaps: list[str] = Field(
        default_factory=list,
        description="Identifizierte Datenlücken (optional)",
    )


# ---------------------------------------------------------------------------
# Section-type → DTO mapper (M11.8d)
# ---------------------------------------------------------------------------

_SECTION_KEYWORD_MAP: dict[str, type[BaseModel]] = {
    # ReportV3 Pflichtabschnitt-DTOs
    "persona": Persona,
    "personas": Persona,
    "zielgrupp": Persona,
    "segment": Segment,
    "segments": Segment,
    "claim": Claim,
    "claims": Claim,
    "befund": Claim,
    "multipli": Multiplier,
    "multiplier": Multiplier,
    "hebel": Multiplier,
    "friction": FrictionPoint,
    "reibung": FrictionPoint,
    "hindernis": FrictionPoint,
    "trust": TrustSignal,
    "vertrauen": TrustSignal,
    "empfehlung": ChangeRecommendation,
    "recommendation": ChangeRecommendation,
    "handlung": ChangeRecommendation,
    "impact": ProjectImpact,
    "auswirkung": ProjectImpact,
    "wirkung": ProjectImpact,
    "position": PositioningVariant,
    "positionierung": PositioningVariant,
    "content": ContentIdea,
    "inhalt": ContentIdea,
    "datenlücke": DataGap,
    "datenlücken": DataGap,
    "data gap": DataGap,
    "data_gap": DataGap,
    "datagap": DataGap,
    "lücke": DataGap,
}


def _section_schema_for(section_title: str) -> type[BaseModel]:
    """Liefert das passende Pydantic-DTO für einen Abschnittstitel.

    Sucht case-insensitiv nach Schlüsselwörtern im Titel.
    Fallback: :class:`SectionMetadata` (allgemeine Metadaten).

    Args:
        section_title: Titel des generierten Abschnitts.

    Returns:
        Pydantic-Modell-Klasse, die als ``schema=`` an ``chat_json`` übergeben
        werden kann.
    """
    lower = section_title.lower()
    for keyword, schema_cls in _SECTION_KEYWORD_MAP.items():
        if keyword in lower:
            return schema_cls
    return SectionMetadata


__all__ = [
    # Evidence / migration helpers
    "EvidenceMapModel",
    "CURRENT_SCHEMA_VERSION",
    "migrate_v1_to_v2",
    # ReportV3 container + 11 Pflichtabschnitt-DTOs
    "ReportV3",
    "Persona",
    "Segment",
    "Claim",
    "Multiplier",
    "FrictionPoint",
    "TrustSignal",
    "ChangeRecommendation",
    "ProjectImpact",
    "PositioningVariant",
    "ContentIdea",
    "DataGap",
    # M11.8d — Plan-Response DTOs
    "PlanSection",
    "PlanResponse",
    # M11.8d — Section-Metadata DTOs + mapper
    "SectionKeyTakeaway",
    "SectionMetadata",
    "_section_schema_for",
]
