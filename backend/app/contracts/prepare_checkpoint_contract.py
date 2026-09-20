"""Prepare-Persona-Checkpoint-Contract (Issue #1472c).

Rein interner Zustandsvertrag — analog ``GraphBuildCheckpoint``
(Slice 1.3, #1472b): lebt unter ``contracts/`` wie jedes strukturierte
Pydantic-Modell dieses Repos, überquert aber nie die HTTP-API-Grenze und
wird deshalb bewusst NICHT in ``dump_schemas.CONTRACTS`` aufgenommen.

Hintergrund (siehe ``prepare_checkpoint.py`` und ``prepare_entities.py``,
``_cap_entities_across_types``): der Graph-Lesepfad für Phase 1 hat kein
``ORDER BY``. Ein erneuter Read beim Resume kann deshalb eine andere
Typ-Verteilung liefern als der unterbrochene Versuch. Der Checkpoint
fixiert deshalb nicht nur die generierten Profile, sondern auch die beim
Original-Versuch getroffene Cap-/Quota-Auswahl (als Entity-UUID-Listen) —
ein Resume darf diese Auswahl nur noch per UUID nachschlagen, nie neu
berechnen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class PreparePersonaCheckpoint(BaseModel):
    """Fortschritts-Checkpoint der Persona-Generierung (Phase 2 von ``prepare_simulation``).

    ``completed_profiles`` ist per Generierungs-INDEX geschlüsselt (String,
    weil JSON-Objektschlüssel immer Strings sind), nicht per Entity-UUID:
    dieselbe Entity kann durch Quota-Expansion (``_expand_entities_for_quota``)
    mehrfach in ``expanded_entity_uuids`` stehen, und jede Wiederholung
    bekommt bewusst einen eigenen demografischen Slot (anderes Alter,
    Geschlecht, …) — eine UUID-Zuordnung würde allen Wiederholungen
    zwangsläufig dasselbe Profil aufprägen und die demografische Streuung
    der Wiederholungen zerstören.

    Die Validitäts-Anker (``graph_id``, ``defined_entity_types``,
    ``max_agents``, ``persona_floor``, ``use_llm_for_profiles``,
    ``effective_quota_plan``) spiegeln exakt die Parameter, die die
    Cap-/Quota-Auswahl bestimmen. Weicht auch nur einer beim erneuten
    Aufruf ab, ist der Checkpoint für DIESEN Versuch nicht mehr gültig
    (siehe ``prepare_checkpoint.checkpoint_is_resumable``) — ein
    angebotenes Resume, das doch neu würfelt, wäre schlimmer als keins.
    """

    model_config = _STRICT

    simulation_id: str
    graph_id: str
    defined_entity_types: Optional[list[str]] = None
    max_agents: Optional[int] = None
    persona_floor: int
    use_llm_for_profiles: bool
    effective_quota_plan: Optional[dict[str, Any]] = None

    # Fixierte Auswahl aus Phase 1 (Cap) bzw. der Quota-Expansion — siehe
    # Moduldocstring. Reihenfolge ist bedeutungstragend: der Index in
    # ``expanded_entity_uuids`` ist der ``user_id``/Generierungs-Index.
    primary_entity_uuids: list[str] = Field(default_factory=list)
    reserve_entity_uuids: list[str] = Field(default_factory=list)
    expanded_entity_uuids: list[str] = Field(default_factory=list)

    entities_count: int = 0
    entity_types: list[str] = Field(default_factory=list)

    # Bereits generierte Profile, Schlüssel = str(Generierungs-Index).
    completed_profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)

    updated_at: datetime

    def with_completed_profile(
        self, index: int, profile: dict[str, Any]
    ) -> "PreparePersonaCheckpoint":
        """Liefert einen neuen Checkpoint mit einem zusätzlich abgeschlossenen Profil.

        Unveränderlich (kein In-Place-Mutate) — der Aufrufer hält die jeweils
        aktuelle Referenz selbst in seiner Closure, analog
        ``GraphBuildCheckpoint.with_completed_chunk``.
        """
        updated = {**self.completed_profiles, str(index): profile}
        return self.model_copy(
            update={"completed_profiles": updated, "updated_at": datetime.now(UTC)}
        )


__all__ = ["PreparePersonaCheckpoint"]
