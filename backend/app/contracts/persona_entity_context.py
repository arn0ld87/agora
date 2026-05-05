"""
PersonaEntityContext-Contract v1 (Pydantic v2) — Single Source of Truth fuer
den Persona-Entity-Diff (Issue #69, EPIC-13-ST-02).

Liefert pro Persona, welche Entity-Eigenschaften aus dem Knowledge Graph
in das Profil eingeflossen sind (entity_id, label, type, properties,
relationships).

Aufruf zum Schema-Dump:
  cd backend && uv run python -m app.contracts.dump_schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=False)


class EntityRelationship(BaseModel):
    """Single relationship from the source entity to a related entity."""

    model_config = _STRICT
    relation_type: str = Field(..., description='Edge-Typ, z. B. "WORKS_AT", "OPPOSES"')
    target_uuid: str
    target_label: str = Field(..., description="Human-readable Name des Ziel-Knotens")
    target_type: str | None = Field(default=None, description="Entity-Type des Zielknotens")


class PersonaEntityContext(BaseModel):
    """
    Entity-Kontext fuer eine einzelne Persona.

    ``entity_properties`` nutzt dict[str, str|int|float|bool] (kein Any) damit
    extra="forbid" konsistent bleibt. Komplexe Werte sollen JSON-stringifiziert
    werden bevor sie hier ankommen.
    """

    model_config = _STRICT

    username: str
    simulation_id: str
    entity_uuid: str
    entity_label: str = Field(..., description="Human-readable Entity-Name")
    entity_type: str = Field(..., description='z. B. "PERSON", "ORGANIZATION", "Entity"')
    entity_summary: str | None = Field(default=None)
    entity_properties: dict[str, str | int | float | bool] = Field(default_factory=dict)
    relationships: list[EntityRelationship] = Field(default_factory=list)
    generated_at: datetime
    source: Literal["graph", "fallback"] = Field(
        default="graph",
        description='"graph" wenn Entity geladen werden konnte, "fallback" wenn nur '
        "uuid+type aus dem Profile selbst stammen (Legacy).",
    )


__all__ = ["EntityRelationship", "PersonaEntityContext"]
