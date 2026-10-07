"""Vertrag fuer ``GET /api/simulation/<id>`` (Issue #1713 Slice S2).

Vor diesem Vertrag lieferte die Route unveraendert ``SimulationState.to_dict()``
zurueck: ``status`` blieb ``"running"``, auch nachdem der Monitor die
Simulation laengst beendet hatte, weil nur ``run_state.json``'s
``runner_status`` terminalisiert wird (``app.services.sim.monitor``),
niemals der persistierte ``SimulationState.status`` selbst. Dieser Vertrag
ergaenzt die Antwort additiv um ``runner_status`` und ``interview_env_alive``
und foermt den read-time-projizierten ``status``
(``app.services.simulation_manager.derive_effective_status``) — der
persistierte Zustand in ``state.json`` bleibt davon unberuehrt.

``RunnerStatusValue`` ist als Literal gespiegelt statt importiert, aus
demselben Grund wie ``SimulationStatusValue`` in
``simulation_record_contract.py``: kein Laufzeit-Import eines Service-Enums
in einen Contract. ``backend/tests/contracts/test_simulation_status_values.py``
haelt beide Wertemengen deckungsgleich mit ``RunnerStatus``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .simulation_record_contract import SimulationStatusValue

_STRICT = ConfigDict(extra="forbid")

RunnerStatusValue = Literal[
    "idle",
    "starting",
    "running",
    "paused",
    "stopping",
    "stopped",
    "completed",
    "failed",
    "ready",
]


class SimulationStatusResponse(BaseModel):
    """Antwort-Schema fuer ``GET /api/simulation/<id>``.

    Felder bis ``persona_floor`` entsprechen 1:1
    ``SimulationState.to_dict()``. ``run_instructions`` bleibt optional und
    wird nur bei ``status == "ready"`` gefuellt (unveraendertes Verhalten).
    """

    model_config = _STRICT

    simulation_id: str
    project_id: str
    graph_id: str
    enable_twitter: bool
    enable_reddit: bool
    status: SimulationStatusValue
    entities_count: int
    profiles_count: int
    entity_types: list[str]
    config_generated: bool
    config_reasoning: str
    current_round: int
    twitter_status: str
    reddit_status: str
    created_at: str
    updated_at: str
    error: Optional[str] = None
    source_simulation_id: Optional[str] = None
    root_simulation_id: Optional[str] = None
    branch_name: Optional[str] = None
    branch_depth: int
    persona_floor: Optional[int] = None
    # Rueckverweis auf den Personasatz (#1807). Nur bei einem Lauf aus einem
    # Satz gesetzt; sonst fehlt der Schluessel in der Antwort (``exclude_if``),
    # damit die Form fuer Laeufe ohne Satz und Altbestand unveraendert bleibt.
    persona_set_id: Optional[str] = Field(
        default=None, exclude_if=lambda value: value is None
    )
    run_instructions: Optional[dict[str, Any]] = None

    # Neu (#1713): Rohwert aus ``run_state.json`` (``None`` ohne Run-State)
    # und Interview-Umgebungsliveness, damit Consumer den projizierten
    # ``status`` gegen die zugrunde liegende Runner-Quelle nachvollziehen
    # koennen.
    runner_status: Optional[RunnerStatusValue] = None
    interview_env_alive: bool


__all__ = ["SimulationStatusResponse", "RunnerStatusValue"]
