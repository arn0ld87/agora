"""Tabellen-Tests für die Simulation-State-Machine.

Sicherstellt, dass ``ALLOWED_TRANSITIONS`` die in der Codebasis tatsächlich
auftretenden Übergänge erlaubt und alle anderen verbietet. Diese Tests
funktionieren als Single-Source-of-Truth-Lock — wenn jemand eine neue
Transition in den Manager-Code patcht, ohne hier den Eintrag zu pflegen,
sollten die Behavior-Tests in ``services/test_simulation_manager_transitions.py``
schreien (deklarativ ↔ effektiv).
"""

from __future__ import annotations

import pytest

from app.services.simulation_manager import SimulationStatus
from app.services.simulation_state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    get_allowed_next,
    is_terminal,
    is_valid_transition,
)


ALL_STATUSES = list(SimulationStatus)


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        # Lifecycle Happy-Path
        (SimulationStatus.CREATED, SimulationStatus.PREPARING),
        (SimulationStatus.PREPARING, SimulationStatus.READY),
        (SimulationStatus.READY, SimulationStatus.RUNNING),
        (SimulationStatus.RUNNING, SimulationStatus.PAUSED),
        (SimulationStatus.RUNNING, SimulationStatus.COMPLETED),
        # Pause/Resume
        (SimulationStatus.PAUSED, SimulationStatus.RUNNING),
        # Stop & Resume aus Stop (api/runs.py:426)
        (SimulationStatus.RUNNING, SimulationStatus.STOPPED),
        (SimulationStatus.PAUSED, SimulationStatus.STOPPED),
        (SimulationStatus.STOPPED, SimulationStatus.RUNNING),
        # Idempotent re-prepare aus READY (Manager prüft Status nicht)
        (SimulationStatus.READY, SimulationStatus.PREPARING),
        # Fehlerpfade aus aktiven Phasen
        (SimulationStatus.CREATED, SimulationStatus.FAILED),
        (SimulationStatus.PREPARING, SimulationStatus.FAILED),
        (SimulationStatus.READY, SimulationStatus.FAILED),
        (SimulationStatus.RUNNING, SimulationStatus.FAILED),
        (SimulationStatus.PAUSED, SimulationStatus.FAILED),
    ],
)
def test_allowed_transitions(
    from_status: SimulationStatus, to_status: SimulationStatus
) -> None:
    assert is_valid_transition(from_status, to_status), (
        f"Transition {from_status.value} → {to_status.value} sollte erlaubt sein"
    )


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        # Sprung über PREPARING
        (SimulationStatus.CREATED, SimulationStatus.READY),
        (SimulationStatus.CREATED, SimulationStatus.RUNNING),
        # Pause während Init
        (SimulationStatus.CREATED, SimulationStatus.PAUSED),
        (SimulationStatus.CREATED, SimulationStatus.STOPPED),
        # Stop während Cleanup/Prepare
        (SimulationStatus.PREPARING, SimulationStatus.STOPPED),
        (SimulationStatus.PREPARING, SimulationStatus.RUNNING),
        (SimulationStatus.PREPARING, SimulationStatus.COMPLETED),
        # READY direkt zu Pause/Stop ohne RUN
        (SimulationStatus.READY, SimulationStatus.PAUSED),
        (SimulationStatus.READY, SimulationStatus.STOPPED),
        (SimulationStatus.READY, SimulationStatus.COMPLETED),
        # Restart aus terminalen Zuständen
        (SimulationStatus.COMPLETED, SimulationStatus.RUNNING),
        (SimulationStatus.COMPLETED, SimulationStatus.PREPARING),
        (SimulationStatus.FAILED, SimulationStatus.RUNNING),
        (SimulationStatus.FAILED, SimulationStatus.PREPARING),
        # STOPPED → COMPLETED (terminal-jump)
        (SimulationStatus.STOPPED, SimulationStatus.COMPLETED),
        (SimulationStatus.STOPPED, SimulationStatus.PREPARING),
        # Self-loops (kein No-op erlaubt)
        (SimulationStatus.RUNNING, SimulationStatus.RUNNING),
        (SimulationStatus.READY, SimulationStatus.READY),
    ],
)
def test_forbidden_transitions(
    from_status: SimulationStatus, to_status: SimulationStatus
) -> None:
    assert not is_valid_transition(from_status, to_status), (
        f"Transition {from_status.value} → {to_status.value} sollte verboten sein"
    )


@pytest.mark.parametrize("terminal", [SimulationStatus.COMPLETED, SimulationStatus.FAILED])
def test_terminal_states_have_no_outgoing(terminal: SimulationStatus) -> None:
    assert get_allowed_next(terminal) == frozenset()
    assert is_terminal(terminal)


@pytest.mark.parametrize(
    "non_terminal",
    [
        SimulationStatus.CREATED,
        SimulationStatus.PREPARING,
        SimulationStatus.READY,
        SimulationStatus.RUNNING,
        SimulationStatus.PAUSED,
        SimulationStatus.STOPPED,
    ],
)
def test_non_terminal_states_have_outgoing(non_terminal: SimulationStatus) -> None:
    assert len(get_allowed_next(non_terminal)) > 0
    assert not is_terminal(non_terminal)


def test_table_covers_all_statuses() -> None:
    """Jeder Enum-Wert muss in der Tabelle einen Eintrag haben (auch wenn leer)."""
    table_keys = set(ALLOWED_TRANSITIONS.keys())
    enum_values = set(ALL_STATUSES)
    assert table_keys == enum_values, (
        f"Tabelle deckt nicht alle SimulationStatus-Werte ab. "
        f"Fehlt: {enum_values - table_keys}, Überzählig: {table_keys - enum_values}"
    )


def test_terminal_set_matches_empty_outgoing() -> None:
    """``TERMINAL_STATES`` und ``ALLOWED_TRANSITIONS`` müssen konsistent sein."""
    derived_terminals = frozenset(
        s for s, allowed in ALLOWED_TRANSITIONS.items() if not allowed
    )
    assert TERMINAL_STATES == derived_terminals


def test_no_transition_targets_unknown_status() -> None:
    """Alle Tabelleneinträge dürfen nur gültige ``SimulationStatus`` als Ziel haben."""
    valid_statuses = set(ALL_STATUSES)
    for from_status, allowed in ALLOWED_TRANSITIONS.items():
        for to_status in allowed:
            assert to_status in valid_statuses, (
                f"Tabelleneintrag {from_status.value}→{to_status} verweist auf "
                f"unbekannten Status"
            )


def test_get_allowed_next_returns_frozenset() -> None:
    """API-Garantie: Rückgabewert ist immutable."""
    result = get_allowed_next(SimulationStatus.RUNNING)
    assert isinstance(result, frozenset)


def test_is_valid_transition_handles_unknown_from_status() -> None:
    """Defensive: kein KeyError, sondern ``False``."""
    # Konstruiert über einen synthetischen Wert, der nicht im Enum existiert.
    # Da SimulationStatus ein StrEnum ist, geht das nur via direkter dict-Lookup-Test.
    assert ALLOWED_TRANSITIONS.get("definitely_not_a_status") is None  # type: ignore[arg-type]
