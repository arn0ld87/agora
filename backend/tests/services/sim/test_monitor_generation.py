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


class _AlwaysRunningProcess:
    """Prozess, der nie beendet — treibt die while-Schleife beliebig oft an."""

    def poll(self):
        return None


class _FakeFile:
    """Minimaler Datei-Stub für stdout_files/stderr_files-Cleanup-Tests."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


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


class TestStaleGenerationSkipsLoopWrite:
    """Codex-Review PR #1474, Finding 1: Generation vor JEDEM Write prüfen —
    nicht nur im Terminal-Pfad, sondern auch vor ``save_state`` innerhalb der
    while-Schleife."""

    def test_stale_after_first_iteration_stops_save_state_and_terminal_path(
        self, env, monkeypatch
    ):
        """Wird die Generation MITTEN in der Schleife veraltet (Force-Restart
        während der alte Monitor noch eine Iteration läuft), darf
        ``save_state`` danach nicht mehr aufgerufen werden — und der
        Terminal-Pfad (Exit-Code-Auswertung, Manifest-Finalisierung) darf gar
        nicht erst laufen."""
        tmp_path = env
        run_id = _create_run_with_draft(tmp_path)
        run_state_dir = str(tmp_path / "sims")
        (tmp_path / "sims" / SIM_ID).mkdir(parents=True)

        # Kein echtes Sleep in Tests — die Schleife soll ohne Wartezeit
        # mehrfach durchlaufen.
        monkeypatch.setattr("app.services.sim.monitor.time.sleep", lambda _s: None)

        state = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        saved_states = []
        calls = {"n": 0}

        def is_current_generation(sim_id, generation):
            calls["n"] += 1
            return calls["n"] == 1  # nur die erste Iteration gilt noch als aktuell

        monitor_simulation(
            SIM_ID,
            run_state_dir=run_state_dir,
            processes={SIM_ID: _AlwaysRunningProcess()},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=lambda sim_id: state,
            save_state=lambda s: saved_states.append(s),
            generation=1,
            is_current_generation=is_current_generation,
        )

        assert len(saved_states) == 1
        assert state.runner_status == RunnerStatus.RUNNING
        assert state.completed_at is None
        assert _read_manifest_status(tmp_path, run_id) == "draft"


class TestStaleGenerationSkipsExceptionFinalization:
    """Codex-Review PR #1474, Finding 1: der except-Handler darf bei
    veralteter Generation weder Metriken mutieren noch ``save_state`` noch
    ``_finalize_manifest_for_simulation`` aufrufen."""

    def test_stale_generation_exception_path_skips_failed_write(
        self, env, monkeypatch
    ):
        tmp_path = env
        run_id = _create_run_with_draft(tmp_path)
        run_state_dir = str(tmp_path / "sims")
        sim_dir = tmp_path / "sims" / SIM_ID
        (sim_dir / "twitter").mkdir(parents=True)
        (sim_dir / "twitter" / "actions.jsonl").write_text("{}\n", encoding="utf-8")

        def _boom(*args, **kwargs):
            raise RuntimeError("boom in loop body")

        monkeypatch.setattr("app.services.sim.monitor.read_action_log_chunk", _boom)

        finalize_calls = []
        monkeypatch.setattr(
            "app.services.sim.monitor._finalize_manifest_for_simulation",
            lambda *a, **kw: finalize_calls.append((a, kw)),
        )

        state = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )
        saved_states = []

        monitor_simulation(
            SIM_ID,
            run_state_dir=run_state_dir,
            processes={SIM_ID: _AlwaysRunningProcess()},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=lambda sim_id: state,
            save_state=lambda s: saved_states.append(s),
            generation=1,
            is_current_generation=lambda sid, gen: False,
        )

        assert not saved_states
        assert state.runner_status == RunnerStatus.RUNNING
        assert not finalize_calls
        assert _read_manifest_status(tmp_path, run_id) == "draft"


class TestStaleGenerationDoesNotCleanUpForeignResources:
    """Codex-Review PR #1474, Finding 2: Cleanup im finally-Block nur für die
    eigenen Ressourcen, die der ueberholte Monitor selbst vorgefunden hat —
    nicht fuer die vom NEUEN Lauf inzwischen eingetragenen."""

    def test_stale_monitor_leaves_new_action_queue_and_files_and_graph_memory_untouched(
        self, env, monkeypatch
    ):
        tmp_path = env
        _create_run_with_draft(tmp_path)
        run_state_dir = str(tmp_path / "sims")
        (tmp_path / "sims" / SIM_ID).mkdir(parents=True)

        old_action_queue = object()
        old_stdout = _FakeFile()
        old_stderr = _FakeFile()
        new_action_queue = object()
        new_stdout = _FakeFile()
        new_stderr = _FakeFile()

        action_queues = {SIM_ID: old_action_queue}
        stdout_files = {SIM_ID: old_stdout}
        stderr_files = {SIM_ID: old_stderr}
        graph_memory_enabled = {SIM_ID: True}

        def swap_in_new_run(*args, **kwargs):
            """Simuliert einen Force-Restart waehrend der alte Monitor noch
            seine erste Schleifeniteration ausfuehrt — der neue Lauf ersetzt
            seine eigenen Eintraege, waehrend der alte Monitor noch laeuft."""
            action_queues[SIM_ID] = new_action_queue
            stdout_files[SIM_ID] = new_stdout
            stderr_files[SIM_ID] = new_stderr
            return None

        monkeypatch.setattr(
            "app.services.sim.monitor._budget_supervision", swap_in_new_run
        )
        stop_updater_calls = []
        monkeypatch.setattr(
            "app.services.graph_memory_updater.GraphMemoryManager.stop_updater",
            lambda sim_id: stop_updater_calls.append(sim_id),
        )

        state = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        monitor_simulation(
            SIM_ID,
            run_state_dir=run_state_dir,
            processes={SIM_ID: _AlwaysRunningProcess()},
            graph_memory_enabled=graph_memory_enabled,
            action_queues=action_queues,
            stdout_files=stdout_files,
            stderr_files=stderr_files,
            get_run_state=lambda sim_id: state,
            save_state=lambda s: None,
            generation=1,
            is_current_generation=lambda sid, gen: False,
        )

        # Die neuen Eintraege des NEUEN Laufs bleiben unangetastet.
        assert action_queues[SIM_ID] is new_action_queue
        assert stdout_files[SIM_ID] is new_stdout
        assert stderr_files[SIM_ID] is new_stderr
        assert not new_stdout.closed
        assert not new_stderr.closed

        # Der alte Monitor schliesst auch sein EIGENES Handle nicht mehr
        # selbst (es gehoert nicht mehr zum aktuellen Dict-Eintrag) — der
        # Identitaetscheck ist bewusst rein additiv (kein zusaetzliches
        # Schliessen fremder/verwaister Handles im Scope dieses Fixes).
        assert not old_stdout.closed

        # Graph-Memory-Updater des NEUEN Laufs bleibt am Leben.
        assert not stop_updater_calls
        assert graph_memory_enabled[SIM_ID] is True


class TestNonStaleGenerationStillCleansUpFully:
    """Positivfall (Codex-Review PR #1474): ohne Ueberholung muss der
    Cleanup unveraendert vollstaendig laufen — die Guards duerfen normale
    Laeufe nicht ausbremsen."""

    def test_non_stale_monitor_pops_and_closes_own_resources(self, env, monkeypatch):
        tmp_path = env
        run_id = _create_run_with_draft(tmp_path)
        run_state_dir = str(tmp_path / "sims")
        (tmp_path / "sims" / SIM_ID).mkdir(parents=True)

        own_action_queue = object()
        own_stdout = _FakeFile()
        own_stderr = _FakeFile()

        action_queues = {SIM_ID: own_action_queue}
        stdout_files = {SIM_ID: own_stdout}
        stderr_files = {SIM_ID: own_stderr}
        graph_memory_enabled = {SIM_ID: True}

        stop_updater_calls = []
        monkeypatch.setattr(
            "app.services.graph_memory_updater.GraphMemoryManager.stop_updater",
            lambda sim_id: stop_updater_calls.append(sim_id),
        )

        state = SimulationRunState(
            simulation_id=SIM_ID,
            runner_status=RunnerStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        monitor_simulation(
            SIM_ID,
            run_state_dir=run_state_dir,
            processes={SIM_ID: _FinishedProcess(returncode=0)},
            graph_memory_enabled=graph_memory_enabled,
            action_queues=action_queues,
            stdout_files=stdout_files,
            stderr_files=stderr_files,
            get_run_state=lambda sim_id: state,
            save_state=lambda s: None,
            generation=1,
            is_current_generation=lambda sid, gen: True,
        )

        assert stop_updater_calls == [SIM_ID]
        assert SIM_ID not in action_queues
        assert SIM_ID not in stdout_files
        assert SIM_ID not in stderr_files
        assert SIM_ID not in graph_memory_enabled
        assert own_stdout.closed
        assert own_stderr.closed
        assert state.runner_status == RunnerStatus.COMPLETED
        assert _read_manifest_status(tmp_path, run_id) == "final"