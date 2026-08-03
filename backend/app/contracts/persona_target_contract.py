"""Persona-Ziel — Contract für den Nenner der Persona-Generierungsanzeige.

Issue #1034 · 2026-08-03

Der Fortschrittszähler „Erzeugt X / Y Personas…“ lief über seinen Nenner
hinaus: die Preview-Antwort von ``POST /api/simulation/prepare`` lieferte
``expected_entities_count`` — die Zahl der Entitäten. Generiert werden aber
Personas, deren Zahl erst später feststeht: entweder durch einen
``PersonaQuotaPlan`` oder durch den Persona-Floor
(``MIN_PERSONA_TABLE_ROWS``), der einen zu kleinen Entity-Pool per
Round-Robin hochskaliert. Sieben Entitäten wurden so zu fünfzig Personas,
während der Nenner bei sieben blieb.

Dieser Contract macht das tatsächliche Generierungsziel explizit und ist
für Preview (``api/simulation_prepare.py``) und Laufpfad
(``prepare_service._phase_generate_profiles``) dieselbe Quelle —
``prepare_service.compute_persona_target`` liefert ihn, damit Zähler und
Nenner nicht aus zwei unterschiedlichen Berechnungen stammen können.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class PersonaTargetContract(BaseModel):
    """Persona-Generierungsziel einer Simulation-Vorbereitung.

    ``persona_target_count`` ist der korrekte Nenner für den
    Fortschrittszähler — nicht ``entity_count``.
    """

    model_config = _STRICT

    entity_count: int = Field(
        ge=0,
        description=(
            "Entitäten nach Eignungsfilter und max_agents-Cap — die Basis, "
            "die der Floor bei Bedarf hochskaliert."
        ),
    )
    persona_target_count: int = Field(
        ge=0,
        description=(
            "Das tatsächliche Generierungsziel: mit Quota-Plan dessen Total "
            "nach Floor-Anhebung, sonst max(entity_count, floor)."
        ),
    )
    floor_applied: bool = Field(
        description=(
            "Wahr, wenn der Persona-Floor das Ziel über die Entitätenzahl "
            "angehoben hat — der Fall, der den Zähler-Nenner-Defekt auslöste."
        ),
    )
    floor: int = Field(
        ge=0,
        description=(
            "Der wirksame Floor: MIN_PERSONA_TABLE_ROWS, gedeckelt durch ein "
            "gesetztes max_agents > 0."
        ),
    )


__all__ = ["PersonaTargetContract"]
