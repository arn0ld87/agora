"""Regressionstest für den B3-Fix (Issue-Review 2026-09-07):
``SimulationRunner.stop_simulation`` joint den Monitor-Thread der Simulation
mit Timeout, bevor es zurückkehrt.

Ohne den Join konnte ein Force-Restart (Stop direkt gefolgt von Start
derselben simulation_id) einen zweiten Monitor-Thread starten, während der
erste noch finalisierte — der Generation-Guard in monitor.py fängt die
Rest-Race ab, der Join verkleinert nur das Fenster und macht einen
langsamen Monitor-Shutdown als Warnung sichtbar.

``_stop_simulation_fn`` und die beteiligten Klassen-Attribute werden
gemockt; der Monitor-Thread ist ein Dummy mit join-Spy. Kein echter
Subprozess nötig — dieser Test prüft ausschließlich das Delegations- und
Join-Verhalten von SimulationRunner, nicht process_manager.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.sim.run_state_store import RunnerStatus, SimulationRunState
from app.services.simulation_runner import SimulationRunner

SIM_ID = "sim_stop_join_1"


class _FakeMonitorThread:
    """Thread-Dummy mit join-Spy: zeichnet das Timeout-Argument auf und
    schaltet ``is_alive`` wahlweise beim Join auf beendet (Normalfall) oder
    bleibt am Leben (Warn-Pfad, Monitor hängt)."""

    def __init__(self, alive_after_join: bool):
        self._alive_after_join = alive_after_join
        self._joined = False
        self.join_calls: list = []

    def is_alive(self):
        return self._alive_after_join if self._joined else True

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        self._joined = True


@pytest.fixture()
def stop_env(monkeypatch):
    state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.STOPPED,
        started_at=datetime.now().isoformat(),
    )
    stop_calls: dict = {}

    def fake_stop_simulation(simulation_id, **kwargs):
        stop_calls["simulation_id"] = simulation_id
        stop_calls["kwargs"] = kwargs
        return state

    monkeypatch.setattr(
        "app.services.simulation_runner._stop_simulation_fn",
        fake_stop_simulation,
    )
    monkeypatch.setattr(SimulationRunner, "_monitor_threads", {})
    monkeypatch.setattr(SimulationRunner, "_processes", {})
    monkeypatch.setattr(SimulationRunner, "_graph_memory_enabled", {})
    yield {"state": state, "stop_calls": stop_calls}


class TestStopJoinsMonitorThread:
    def test_stop_joins_alive_monitor_thread_with_timeout(self, stop_env):
        """Stop wartet auf den Monitor-Thread und übergibt das klassenseitige
        Timeout (grace_period + 2s, min 5s)."""
        fake_thread = _FakeMonitorThread(alive_after_join=False)
        SimulationRunner._monitor_threads[SIM_ID] = fake_thread

        result = SimulationRunner.stop_simulation(SIM_ID)

        assert result is stop_env["state"]
        assert fake_thread.join_calls == [
            SimulationRunner._MONITOR_JOIN_TIMEOUT_SECONDS
        ]
        # Delegation an process_manager bleibt unangetastet.
        assert stop_env["stop_calls"]["simulation_id"] == SIM_ID
        assert (
            stop_env["stop_calls"]["kwargs"]["run_state_dir"]
            == SimulationRunner.RUN_STATE_DIR
        )
        assert (
            stop_env["stop_calls"]["kwargs"]["processes"]
            is SimulationRunner._processes
        )

    def test_stop_returns_state_even_if_monitor_thread_stays_alive(
        self, stop_env
    ):
        """Ein Monitor, der das Timeout überdauert, blockiert den Stop nicht:
        join wird mit Timeout gerufen, die Warnung bleibt Log-Sache, der
        Aufrufer bekommt seinen Zustand."""
        hanging_thread = _FakeMonitorThread(alive_after_join=True)
        SimulationRunner._monitor_threads[SIM_ID] = hanging_thread

        result = SimulationRunner.stop_simulation(SIM_ID)

        assert result is stop_env["state"]
        assert hanging_thread.join_calls == [
            SimulationRunner._MONITOR_JOIN_TIMEOUT_SECONDS
        ]

    def test_stop_without_alive_monitor_thread_does_not_join(self, stop_env):
        """Kein Monitor-Eintrag → kein join; auch ein toter Eintrag wird
        nicht gejoint (is_alive-Check vor dem Join)."""
        dead_thread = _FakeMonitorThread(alive_after_join=False)
        dead_thread._joined = True  # is_alive() liefert False von Anfang an
        SimulationRunner._monitor_threads[SIM_ID] = dead_thread

        result = SimulationRunner.stop_simulation(SIM_ID)

        assert result is stop_env["state"]
        assert dead_thread.join_calls == []