"""Vertrag der fragebezogenen Entitaetenauswahl (#1759, A5).

Beim ``max_agents``-Cap verteilte ``_cap_entities_across_types`` die Plaetze
reihum ueber die Typen, ohne Bezug zur Simulationsfrage. Die Hybrid-Auswahl
(``services/prepare_requirement_selection.py``) vergibt harte Mindestsitze fuer
in der Frage genannte Gruppen und fuer Entscheider und laesst die Restplaetze
von einem Auswahl-LLM nach Relevanz zur Frage ranken.

``EntityRelevanceResponse`` ist eine LLM-Antwort und geht als ``schema`` an
``LLMClient.chat_json``. ``EntitySelectionDecision`` haelt fest, warum eine
Entitaet einen Platz bekam; sie wandert in den ``PreparePersonaCheckpoint``.
Beide sind interner Zustand und ueberqueren die HTTP-API-Grenze nicht — sie
stehen deshalb nicht in ``dump_schemas.CONTRACTS``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_STRICT = ConfigDict(extra="forbid")

#: Warum eine Entitaet einen Persona-Platz hat.
SelectionBasis = Literal[
    "named_group",
    "decision_maker",
    "llm_relevance",
    "fallback_round_robin",
]


class EntityRelevanceItem(BaseModel):
    """Bewertung eines Kandidaten durch das Auswahl-LLM."""

    model_config = _STRICT

    candidate_index: int = Field(
        ge=1, description="1-basierte Nummer des Kandidaten aus der Kandidatenliste"
    )
    relevance: int = Field(
        ge=0,
        le=10,
        description=(
            "Relevanz fuer die Simulationsfrage: 0 = irrelevant, 10 = unverzichtbar"
        ),
    )
    reason: str = Field(
        description="Pflichtbegruendung in einem Satz: warum diese Relevanz fuer die Frage"
    )

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason darf nicht leer sein")
        return stripped


class EntityRelevanceResponse(BaseModel):
    """Antwortvertrag des Auswahl-LLM: eine Bewertung je Kandidat."""

    model_config = _STRICT

    items: list[EntityRelevanceItem] = Field(
        description="Genau eine Bewertung pro Kandidat der Liste"
    )


class EntitySelectionDecision(BaseModel):
    """Auswahlbegruendung zu einem vergebenen Persona-Platz (Checkpoint)."""

    model_config = _STRICT

    entity_uuid: str
    entity_name: str
    basis: SelectionBasis
    reason: str = Field(min_length=1)
    seats: int = Field(default=1, ge=1)


__all__ = [
    "EntityRelevanceItem",
    "EntityRelevanceResponse",
    "EntitySelectionDecision",
    "SelectionBasis",
]
