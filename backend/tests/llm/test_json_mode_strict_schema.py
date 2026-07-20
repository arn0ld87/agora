"""Regressionstests für _enforce_openai_strict_schema (backend/app/llm/json_mode.py).

Root-Cause-Regression (Report-Rescue 2026-07-20):
Der Strict-Schema-Sanitizer strippte ``title`` positionsblind — auch dort, wo
``title`` der NAME einer Property ist (``properties: {"title": {...}}``) und
nicht ein JSON-Schema-Metadaten-Keyword auf einem Objekt-Knoten. Dadurch verlor
das an Google/OpenAI gesendete Schema die Pflicht-Property ``title``; die
LLM-Antwort ohne ``title`` scheiterte danach an der vollständigen
Pydantic-Validierung (``12 validation errors for PlanResponse`` — alle
``…title: Field required``), was den kompletten Report-Lauf auf ``failed``
zog.

Diese Tests pinnen die positionsbewusste Unterscheidung:
- ``title`` als Property-NAME muss überleben (properties + required).
- ``title`` als Metadaten-Keyword auf einem Objekt-Knoten wird weiter gestrippt.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.llm.json_mode import _enforce_openai_strict_schema
from app.services.report_agent.schemas import PlanResponse


class _SectionLike(BaseModel):
    """Minimalmodell mit einer Property, die zufällig ``title`` heißt."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, description="Abschnittstitel")
    description: str = Field(default="—", description="Inhaltsbeschreibung")


def test_property_named_title_survives_strict_sanitize() -> None:
    """Eine Property namens ``title`` darf NICHT gestrippt werden."""
    out = _enforce_openai_strict_schema(_SectionLike)

    props = out["properties"]
    assert "title" in props, (
        "Property-Name 'title' wurde fälschlich gestrippt — "
        f"vorhandene Properties: {sorted(props)}"
    )
    assert "description" in props
    # OpenAI/Google strict-mode: jede Property muss in required[] stehen.
    assert set(out["required"]) == {"title", "description"}


def test_object_level_title_metadata_is_still_dropped() -> None:
    """Das Objekt-Metadatum ``title`` (Sibling von type/properties) bleibt weg."""
    out = _enforce_openai_strict_schema(_SectionLike)

    # Pydantic setzt auf Objekt-Ebene "title": "_SectionLike" — reines Metadatum.
    assert "title" not in {k for k in out if k != "properties"}
    # Auch im Feld-Schema selbst ist "title" ein Pydantic-Metadatum → gestrippt.
    assert "title" not in out["properties"]["title"]


def test_plan_response_schema_keeps_title_in_sections() -> None:
    """Regression: PlanResponse-Schema behält title top-level und je Section."""
    out = _enforce_openai_strict_schema(PlanResponse)

    assert "title" in out["properties"], "top-level title-Property fehlt"
    assert "title" in out["required"]

    section_schema = out["properties"]["sections"]["items"]
    assert "title" in section_schema["properties"], (
        "Section-Property 'title' wurde gestrippt — Gemini kann sie nicht liefern"
    )
    assert "title" in section_schema["required"]
