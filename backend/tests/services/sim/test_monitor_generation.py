"""Regressionstests für den B3-Fix (Issue-Review 2026-09-07): ein veralteter
Monitor-Thread nach einem Force-Restart finalisiert nicht den neuen Lauf und
entfernt nicht den neuen Prozess-Eintrag.

Vor dem Fix tailte ``monitor_simulation`` in einem Daemon-Thread den
OASIS-Subprozess. Bei einem Force-Restart (``stop_simulation`` direkt
gefolgt von ``start_simulation`` für dieselbe simulation_id) startete der
zweite Monitor, während der erste noch sein eigenes Prozessende verarbeitete:
Der alte Monitor überschrieb den Run-State des neuen Laufs mit seinem
Endzustand und ``processes.pop`` entfernte den EINTRAG DES NEUEN Prozesses.

Der Fix dreifach: (1) Generation-Token pro Simulation — der alte Monitor
überspringt Finalisierung (Guard vor save_state/RunRegistry/Manifest), (2)
``processes.pop`` nur noch per Identitätscheck, (3) ``stop_simulation``
joint den Monitor-Thread (getestet in test_simulation_runner_stop_join.py).

Folgt dem Registry-/Manifest-Muster aus test_monitor_stop.py und
test_monitor_manifest_finalize.py (echte RunRegistry gegen ein Tempdir,
weil monitor.py RunRegistry innerhalb der Funktion importiert).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime

import pytest

from app.services.manifest_capture import ManifestCapture
from app.services.run_registry import RunRegistry
from app.services.sim.monitor import monitor_simulation
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState

SIM_ID = "sim_generation_1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("AGORA_INSTANCE_DIR", str(tmp_path))
    RunRegistry._instance = None
    monkeypatch.setattr(
        "app.services.simulation_ipc.write_control_state",
        lambda sim_id, **changes: changes,
    )
    yield tmp_path
    RunRegistry._instance = None


def _create_run_with_draft(tmp_path) -> str:
    """RunRegistry-Eintrag + Draft-Manifest anlegen (Muster aus
    test_monitor_manifest_finalize.py::_create_run_with_draft)."""
    run = RunRegistry().create_run(
        "simulation_run",
        SIM_ID,
        linked_ids={"simulation_id": SIM_ID},
    )
    run_id = run["run_id"]

    run_dir = os.path.join(str(tmp_path), "runs", run_id)
    ManifestCapture.capture_draft(
        run_id=run_id,
        run_dir=run_dir,
        seed_document_hash="sha256:abc",
        seed_document_filename="test.md",
        simulation_config_hash="sha256:def",
        graph_id="graph_001",
        agora_version="0.9.5",
        schema_version="1.0.0",
        random_seed=42,
        simulation_id_seed=SIM_ID,
    )
    return run_id


def _read_manifest_status(tmp_path, run_id) -> str:
    manifest_path = os.path.join(str(tmp_path), "runs", run_id, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)["status"]


class _FinishedProcess:
    """Bereits beendeter Prozess für synchrone Monitor-Direktaufrufe."""

    def __init__(self, returncode: int):
        self.returncode = returncode

    def poll(self):
        return self.returncode


class TestStaleMonitorAfterForceRestart:
    def test_stale_monitor_neither_finalizes_new_run_nor_pops_new_process(
        self, env
    ):
        """Kern-Regression B3: Force-Restart ersetzt ``processes[sim_id]``
        durch den neuen Subprozess, waehrend der alte Monitor-Thread (Generation
        1) noch laeuft. Der alte Monitor darf weder den neuen Prozess-Eintrag
        entfernen noch den Zustand des NEUEN Laufs mit seinem Endzustand
        ueberschreiben — nur der neue Monitor (Generation 2) finalisiert."""
        tmp_path = env
        run_id = _create_run_with_draft(tmp_path)
        registry_entry_before = RunRegistry().get_run(run_id)
        initial_status = registry_entry_before["status"]

        run_state_dir = str(tmp_path / "sims")
        sim_dir = tmp_path / "sims" / SIM_ID
        sim_dir.mkdir(parents=True)

        popen1 = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        popen2 = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
        )
        popen2.wait(timeout=10)

        processes = {SIM_ID: popen1}
        generations: dict = {SIM_ID: 1}
        state_old = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        state_new = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        saved_states = []
        thread_errors = []

        # Signalisiert, dass der alte Monitor seine lokale Prozess-Referenz
        # (popen1) gelesen hat — get_run_state laeuft im Monitor direkt nach
        # dem processes.get(), davor kann der Test den Eintrag ersetzen.
        monitor_read_state = threading.Event()

        def old_get_run_state(sim_id):
            monitor_read_state.set()
            return state_old

        def run_old_monitor():
            try:
                monitor_simulation(
                    SIM_ID,
                    run_state_dir=run_state_dir,
                    processes=processes,
                    graph_memory_enabled={},
                    action_queues={},
                    stdout_files={},
                    stderr_files={},
                    get_run_state=old_get_run_state,
                    save_state=lambda s: saved_states.append(s),
                    generation=1,
                    is_current_generation=lambda sid, gen: (
                        generations.get(sid) == gen
                    ),
                )
            except Exception as exc:  # noqa: BLE001 — Fehler darf der Test sehen
                thread_errors.append(exc)

        old_monitor = threading.Thread(target=run_old_monitor, daemon=True)
        try:
            old_monitor.start()
            assert monitor_read_state.wait(timeout=5), (
                "alter Monitor hat seinen Zustand nie gelesen — Testaufbau "
                "kaputt, nicht das Produkt"
            )

            # Force-Restart: neuer Prozess ersetzt den Eintrag, Generation
            # zaehlt hoch (SimulationRunner._on_monitor_start-Semantik).
            processes[SIM_ID] = popen2
            generations[SIM_ID] = 2
            popen1.terminate()

            old_monitor.join(timeout=15)
            assert not old_monitor.is_alive(), (
                "alter Monitor haengt nach Prozessende im Monitor-Loop"
            )
            assert not thread_errors

            # (1) Identitaetscheck: der neue Prozess-Eintrag bleibt unberuehrt
            assert processes[SIM_ID] is popen2

            # (2) Guard: der alte Monitor hat NICHT finalisiert — Zustand
            # des alten Laufs unangetastet, Registry und Manifest bleiben
            # auf dem Initialstand.
            assert state_old.runner_status == RunnerStatus.RUNNING
            assert state_old.completed_at is None
            registry_entry_after_stale = RunRegistry().get_run(run_id)
            assert registry_entry_after_stale["status"] == initial_status
            assert _read_manifest_status(tmp_path, run_id) == "draft"

            # Der NEUE Monitor (aktuelle Generation) finalisiert normal:
            # popen2 endete mit exit 0 → COMPLETED, Registry-Status und
            # finales Manifest gehoeren dem neuen Lauf.
            monitor_simulation(
                SIM_ID,
                run_state_dir=run_state_dir,
                processes=processes,
                graph_memory_enabled={},
                action_queues={},
                stdout_files={},
                stderr_files={},
                get_run_state=lambda sim_id: state_new,
                save_state=lambda s: saved_states.append(s),
                generation=2,
                is_current_generation=lambda sid, gen: (
                    generations.get(sid) == gen
                ),
            )

            assert state_new.runner_status == RunnerStatus.COMPLETED
            assert saved_states
            assert saved_states[-1] is state_new
            assert _read_manifest_status(tmp_path, run_id) == "final"

            # Der neue Monitor darf seinen eigenen Prozess-Eintrag entfernen —
            # der Identitaetscheck blockt nur den alten, nicht den aktuellen.
            assert SIM_ID not in processes
        finally:
            for proc in (popen1, popen2):
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)


class TestBackwardCompatibleDefaults:
    def test_monitor_without_generation_hook_finalizes_as_before(self, env):
        """Ohne ``is_current_generation`` (None) bleibt das alte Verhalten:
        alle bestehenden Direktaufrufe von monitor_simulation uebergeben die
        neuen Parameter nicht — der Guard muss dann inaktiv sein."""
        tmp_path = env
        run_id = _create_run_with_draft(tmp_path)
        run_state_dir = str(tmp_path / "sims")
        (tmp_path / "sims" / SIM_ID).mkdir(parents=True)

        state = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        saved_states = []

        monitor_simulation(
            SIM_ID,
            run_state_dir=run_state_dir,
            processes={SIM_ID: _FinishedProcess(returncode=0)},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=lambda sim_id: state,
            save_state=lambda s: saved_states.append(s),
        )

        assert state.runner_status == RunnerStatus.COMPLETED
        assert saved_states[-1] is state
        assert _read_manifest_status(tmp_path, run_id) == "final"