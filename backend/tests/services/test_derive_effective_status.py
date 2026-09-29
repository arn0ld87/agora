"""Tests fuer ``derive_effective_status`` (Issue #1713 Slice S2).

``GET /api/simulation/<id>`` meldete nach Simulationsende weiter "running",
weil der Monitor nur ``run_state.json``'s ``runner_status`` terminalisiert,
niemals den persistierten ``SimulationState.status``. Dieser Helfer ist die
reine Lesezeit-Projektion, die die Route jetzt anwendet — ohne den
persistierten Zustand zu veraendern.
"""
from __future__ import annotations

import pytest

from app.services.simulation_manager import SimulationStatus, derive_effective_status
from app.services.sim.run_state_store import RunnerStatus


@pytest.mark.parametrize(
    "runner_status,expected",
    [
        (RunnerStatus.COMPLETED, SimulationStatus.COMPLETED),
        (RunnerStatus.FAILED, SimulationStatus.FAILED),
        (RunnerStatus.STOPPED, SimulationStatus.STOPPED),
    ],
)
def test_running_status_follows_terminal_runner_status(runner_status, expected):
    assert derive_effective_status(SimulationStatus.RUNNING, runner_status) is expected


@pytest.mark.parametrize(
    "runner_status",
    [
        RunnerStatus.IDLE,
        RunnerStatus.STARTING,
        RunnerStatus.RUNNING,
        RunnerStatus.PAUSED,
        RunnerStatus.STOPPING,
        RunnerStatus.READY,
    ],
)
def test_running_status_unchanged_for_non_terminal_runner_status(runner_status):
    assert (
        derive_effective_status(SimulationStatus.RUNNING, runner_status)
        is SimulationStatus.RUNNING
    )


def test_running_status_unchanged_without_run_state():
    assert (
        derive_effective_status(SimulationStatus.RUNNING, None) is SimulationStatus.RUNNING
    )


@pytest.mark.parametrize(
    "status",
    [
        SimulationStatus.CREATED,
        SimulationStatus.PREPARING,
        SimulationStatus.READY,
        SimulationStatus.PAUSED,
        SimulationStatus.STOPPED,
        SimulationStatus.CANCELLED_PARTIAL,
        SimulationStatus.COMPLETED,
        SimulationStatus.FAILED,
        SimulationStatus.INTERRUPTED,
    ],
)
def test_non_running_status_never_projected(status):
    """Insbesondere: ein bereits FAILED-Status bleibt FAILED, auch wenn der
    Runner nachtraeglich COMPLETED meldet — kein Ueberschreiben eines
    terminalen persistierten Zustands durch die Runner-Projektion."""
    for runner_status in (RunnerStatus.COMPLETED, RunnerStatus.FAILED, RunnerStatus.STOPPED, None):
        assert derive_effective_status(status, runner_status) is status
