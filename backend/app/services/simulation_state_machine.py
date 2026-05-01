"""Deklarative Transition-Tabelle für ``SimulationStatus``.

Diese Datei ist das passive Single-Source-of-Truth-Modell für den
Simulation-Lifecycle. Sie wird in v0.7.0 nur von Tests konsumiert (siehe
``backend/tests/test_simulation_state_machine.py``) — der Manager-Code in
``simulation_manager.py``, ``api/simulation_run.py`` und ``api/runs.py``
betreibt seine Transitions aktuell ohne Guard. EPIC-06-ST-02 wird die
Helper später aktiv einbauen.

Erlaubte Übergänge spiegeln 1:1 das beobachtete Verhalten der existierenden
Aufrufstellen (Stand 2026-05-01, Commit a02cf3f):

- ``create_simulation`` → ``CREATED``
- ``prepare_simulation`` → ``PREPARING``, dann ``READY`` (Erfolg) oder ``FAILED``
- ``start_simulation`` → ``RUNNING``
- ``pause_simulation`` → ``PAUSED``
- ``resume_run`` → ``RUNNING`` (aus ``PAUSED`` oder ``STOPPED``)
- ``stop_run`` → ``STOPPED``
- automatischer Rundenabschluss → ``COMPLETED``
- Fehlerpfade in beliebiger Phase → ``FAILED``
- erneuter ``prepare`` aus ``READY`` ist idempotent (Manager prüft Status nicht)
"""

from __future__ import annotations

from .simulation_manager import SimulationStatus

ALLOWED_TRANSITIONS: dict[SimulationStatus, frozenset[SimulationStatus]] = {
    SimulationStatus.CREATED: frozenset(
        {SimulationStatus.PREPARING, SimulationStatus.FAILED}
    ),
    SimulationStatus.PREPARING: frozenset(
        {SimulationStatus.READY, SimulationStatus.FAILED}
    ),
    SimulationStatus.READY: frozenset(
        {
            SimulationStatus.RUNNING,
            SimulationStatus.PREPARING,
            SimulationStatus.FAILED,
        }
    ),
    SimulationStatus.RUNNING: frozenset(
        {
            SimulationStatus.PAUSED,
            SimulationStatus.STOPPED,
            SimulationStatus.COMPLETED,
            SimulationStatus.FAILED,
        }
    ),
    SimulationStatus.PAUSED: frozenset(
        {
            SimulationStatus.RUNNING,
            SimulationStatus.STOPPED,
            SimulationStatus.FAILED,
        }
    ),
    SimulationStatus.STOPPED: frozenset({SimulationStatus.RUNNING}),
    SimulationStatus.COMPLETED: frozenset(),
    SimulationStatus.FAILED: frozenset(),
}

TERMINAL_STATES: frozenset[SimulationStatus] = frozenset(
    {SimulationStatus.COMPLETED, SimulationStatus.FAILED}
)


def is_valid_transition(
    from_status: SimulationStatus, to_status: SimulationStatus
) -> bool:
    """``True``, wenn ``from_status`` → ``to_status`` in der Tabelle erlaubt ist."""
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def get_allowed_next(from_status: SimulationStatus) -> frozenset[SimulationStatus]:
    """Liefert die Menge aller erlaubten Folgestatus."""
    return ALLOWED_TRANSITIONS.get(from_status, frozenset())


def is_terminal(status: SimulationStatus) -> bool:
    """``True``, wenn der Status keine weiteren Übergänge zulässt."""
    return status in TERMINAL_STATES


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "is_valid_transition",
    "get_allowed_next",
    "is_terminal",
]
