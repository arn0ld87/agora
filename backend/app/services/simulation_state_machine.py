"""Deklarative Transition-Tabelle für ``SimulationStatus``.

Single-Source-of-Truth-Modell für den Simulation-Lifecycle. Seit
EPIC-06-ST-02 (Issue #42) aktiv vom Manager und von den API-Routen
konsumiert: alle Statussetzungen laufen über ``SimulationManager._set_status``
und werden gegen :func:`assert_valid_transition` geprüft.

Erlaubte Übergänge:

- ``create_simulation`` → ``CREATED``
- ``prepare_simulation`` → ``PREPARING``, dann ``READY`` (Erfolg) oder ``FAILED``
- Retry nach Fehler: ``FAILED`` → ``PREPARING`` (User triggert prepare nochmal)
- Branching erzeugt einen READY-Branch in zwei Schritten: ``CREATED`` →
  ``PREPARING`` → ``READY`` (siehe ``branching_service.create_branch``)
- ``start_simulation`` → ``RUNNING``
- ``pause_simulation`` → ``PAUSED``
- ``resume_run`` → ``RUNNING`` (aus ``PAUSED`` oder ``STOPPED``)
- ``stop_run`` → ``STOPPED``
- automatischer Rundenabschluss → ``COMPLETED``
- Fehlerpfade in beliebiger Phase → ``FAILED``

Force-Reset: ``simulation_run.start_run`` mit ``force=True`` ruft
``SimulationManager._reset_to_ready`` auf — eine eigene Operation,
die explizit *kein* FSM-Übergang ist (sondern ein Lifecycle-Neustart
mit Cleanup von Runtime-Artefakten). Sie umgeht den Guard bewusst und
ist deshalb als separate Methode benannt, nicht als Flag-Parameter.
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
    # FAILED ist *fast* terminal: User darf einen fehlgeschlagenen Prepare
    # erneut anstoßen (Retry-Pattern). Andere Übergänge aus FAILED bleiben
    # untersagt — wer eine fertige FAILED-Simulation neu starten will,
    # muss durch den dokumentierten Force-Reset (``_reset_to_ready``).
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
    SimulationStatus.FAILED: frozenset({SimulationStatus.PREPARING}),
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
    """``True``, wenn der Status keine weiteren Übergänge zulässt.

    ``FAILED`` lässt zwar den Retry-Übergang zu ``PREPARING`` zu, ist
    aber sonst terminal — daher zählt es weiterhin zur Terminal-Menge.
    """
    return status in TERMINAL_STATES


class InvalidStatusTransition(ValueError):
    """Wird geworfen, wenn ein verbotener FSM-Übergang versucht wird."""

    def __init__(
        self, from_status: SimulationStatus, to_status: SimulationStatus
    ) -> None:
        allowed = sorted(s.value for s in get_allowed_next(from_status))
        super().__init__(
            f"Invalid simulation status transition "
            f"{from_status.value} -> {to_status.value}; "
            f"allowed from {from_status.value}: "
            f"{', '.join(allowed) if allowed else '(none)'}"
        )
        self.from_status = from_status
        self.to_status = to_status


def assert_valid_transition(
    from_status: SimulationStatus, to_status: SimulationStatus
) -> None:
    """Wirft :class:`InvalidStatusTransition`, wenn der Übergang verboten ist.

    Self-Übergänge (``X → X``) sind erlaubt, weil ein erneutes Setzen
    desselben Status semantisch ein No-Op ist und im Code an mehreren
    Stellen idempotent vorkommt (z.B. wiederholtes ``status = FAILED`` im
    Error-Pfad).
    """
    if from_status == to_status:
        return
    if not is_valid_transition(from_status, to_status):
        raise InvalidStatusTransition(from_status, to_status)


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "InvalidStatusTransition",
    "assert_valid_transition",
    "is_valid_transition",
    "get_allowed_next",
    "is_terminal",
]
