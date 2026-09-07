"""Regressionstest fuer Finding B (Codex-Review 2026-09-08, PR #1476).

``SimulationRunner._correct_stale_run_state`` muss den tatsaechlich
verwaisten Ursprungs-Run in der ``RunRegistry`` treffen, nicht das zuletzt
angelegte (Replacement-)Manifest.

Nachgestellter Resume-Pfad (``_resume_or_restart_simulation_run`` in
``app/api/runs.py``): ``RunLifecycle.begin()`` legt das Replacement-Manifest
(``status="pending"``) an, BEVOR ``start_simulation()`` — und damit die
Stale-Korrektur fuer den verwaisten Ursprungs-Run — ueberhaupt laeuft. Ohne
den gezielten Run-ID-Fix in ``_correct_stale_run_state`` waehlt
``RunRegistry.get_latest_by_linked_id`` (sortiert nach ``updated_at``) das
soeben erst angelegte, juengere Replacement-Manifest statt des
tatsaechlich verwaisten, laenger laufenden Ursprungs-Runs.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from app.config import Config
from app.services.run_lifecycle import RunLifecycle
from app.services.run_registry import RunRegistry
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState
from app.services.simulation_runner import SimulationRunner

SIM_ID = "sim_stale_registry_targeting"


@pytest.fixture()
def registry_env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "run_registry"
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    os.makedirs(registry_dir, exist_ok=True)

    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(upload_root / "simulations"))
    monkeypatch.setattr(SimulationRunner, "_run_states", {})

    registry = RunRegistry()
    yield registry

    RunRegistry._instance = None


def test_stale_correction_targets_orphaned_run_not_replacement(registry_env):
    """Der verwaiste Ursprungs-Run (status='processing') wird korrigiert;
    das frisch angelegte Replacement-Manifest (status='pending') bleibt
    unangetastet — kein voruebergehendes failed-Event darauf."""
    registry = registry_env

    # 1. Der urspruengliche Run laeuft — er ist der Run, der beim
    #    Container-Restart verwaist.
    orphan = registry.create_run(
        run_type="simulation_run",
        entity_id=SIM_ID,
        status="processing",
        linked_ids={"simulation_id": SIM_ID},
    )

    # 2. Wie _resume_or_restart_simulation_run: RunLifecycle.begin() legt
    #    das Replacement-Manifest an, BEVOR start_simulation() (und damit
    #    die Stale-Korrektur) ueberhaupt laeuft.
    lifecycle = RunLifecycle.begin(
        registry,
        "simulation_run",
        SIM_ID,
        linked_ids={"simulation_id": SIM_ID},
    )
    lifecycle.__enter__()
    replacement_run_id = lifecycle.run_id
    assert replacement_run_id != orphan["run_id"]
    assert registry.get_run(replacement_run_id)["status"] == "pending"

    # 3. Die Stale-Korrektur laeuft (wie process_manager.start_simulation
    #    sie fuer einen mit toter PID aufgefundenen RUNNING/STARTING-
    #    Zustand ausloest).
    stale_state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.FAILED,
        error="Prozess-Neustart während des Runs",
        started_at=datetime.now().isoformat(),
    )
    SimulationRunner._correct_stale_run_state(stale_state)

    # 4. Der verwaiste Ursprungs-Run wurde korrigiert ...
    updated_orphan = registry.get_run(orphan["run_id"])
    assert updated_orphan["status"] == "failed"
    assert updated_orphan["termination_reason"] == "process_restart"

    # 5. ... das Replacement bleibt komplett unangetastet.
    untouched_replacement = registry.get_run(replacement_run_id)
    assert untouched_replacement["status"] == "pending"
