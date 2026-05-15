from __future__ import annotations

from functools import cache

from pydantic import BaseModel, ConfigDict, Field, create_model

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


class _TableMetadataBase(BaseModel):
    model_config = _STRICT


@cache
def _make_table_metadata(item_cls: type[BaseModel]) -> type[BaseModel]:
    """Create a strict section metadata wrapper for list-shaped ReportV3 DTOs."""
    return create_model(
        f"{item_cls.__name__}Table",
        __base__=_TableMetadataBase,
        __module__=__name__,
        items=(list[item_cls], Field(description=f"Liste von {item_cls.__name__}-Einträgen")),
    )


# ---------------------------------------------------------------------------
# Plan-Response DTO (M11.8d) — strict schema for planning.py::plan_outline()
# ---------------------------------------------------------------------------

class PlanSection(BaseModel):
    """Ein Abschnitt im generierten Report-Outline."""

    model_config = _STRICT

    title: str = Field(min_length=1, description="Abschnittstitel")
    description: str = Field(
        min_length=1,
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
        min_length=1,
        description="Kurze Zusammenfassung des Reports",
    )
    sections: list[PlanSection] = Field(
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
        description="Zentrale Erkenntnisse des Abschnitts (max. 5)",
    )
    data_gaps: list[str] = Field(
        description="Identifizierte Datenlücken (leer wenn keine vorhanden)",
    )


# ---------------------------------------------------------------------------
# Section-type → DTO mapper (M11.8d)
# ---------------------------------------------------------------------------

_SECTION_TITLE_MAP: dict[str, type[BaseModel]] = {
    # ReportV3 Pflichtabschnitt-DTOs
    "segment-tabelle": _make_table_metadata(Segment),
    "persona-tabelle": _make_table_metadata(Persona),
    "multiplikator-auswertung": _make_table_metadata(Multiplier),
    "top 10 reibungspunkte": _make_table_metadata(FrictionPoint),
    "top 10 vertrauenssignale": _make_table_metadata(TrustSignal),
    "top 10 änderungen": _make_table_metadata(ChangeRecommendation),
    "projektwirkung": _make_table_metadata(ProjectImpact),
    "positionierung": _make_table_metadata(PositioningVariant),
    "content-ideen": _make_table_metadata(ContentIdea),
    "datenlücken": _make_table_metadata(DataGap),
}


def _section_schema_for(section_title: str) -> type[BaseModel]:
    """Liefert das passende Pydantic-DTO für einen Abschnittstitel.

    Mappt nur bekannte Pflichtabschnitt-Titel auf ReportV3-DTOs. Freie
    Abschnittstitel wie ``Persona Reaction Analysis`` bekommen bewusst das
    generische :class:`SectionMetadata`, statt ein vollständiges Persona-Objekt
    zu erzwingen.

    Args:
        section_title: Titel des generierten Abschnitts.

    Returns:
        Pydantic-Modell-Klasse, die als ``schema=`` an ``chat_json`` übergeben
        werden kann.
    """
    lower = section_title.strip().lower()
    return _SECTION_TITLE_MAP.get(lower, SectionMetadata)


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
    # M11.8d — Section-Metadata DTOs
    "SectionKeyTakeaway",
    "SectionMetadata",
]
