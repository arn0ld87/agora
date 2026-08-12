"""Issue #763 (Ticket 9) — Draft-Manifest wird beim Run-Ende finalisiert.

``monitor_simulation`` setzt den Terminalstatus (COMPLETED/FAILED/STOPPED),
aber vor diesem Slice blieb ein einmal geschriebenes Draft-Manifest für immer
``status="draft"`` — ``capture_final`` wurde nie aufgerufen. Diese Tests
decken die isolierte Hilfsfunktion ab, die das nachholt.

Folgt dem etablierten Registry-Test-Muster aus test_monitor_cancel.py: eine
echte RunRegistry gegen ein Tempdir statt eines Mocks, weil ``monitor.py``
``RunRegistry`` innerhalb der Funktion importiert (Modul-Level-Patch würde
nicht greifen).
"""

from __future__ import annotations

import json
import os

import pytest

from app.services.manifest_capture import ManifestCapture
from app.services.run_registry import RunRegistry
from app.services.sim.monitor import _finalize_manifest_for_simulation
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState

SIM_ID = "sim_finalize_1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("AGORA_INSTANCE_DIR", str(tmp_path))
    RunRegistry._instance = None
    yield tmp_path
    RunRegistry._instance = None


def _create_run_with_draft(tmp_path) -> str:
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


def test_finalizes_manifest_on_completed(env):
    """S1: bei COMPLETED wird das Draft-Manifest final."""
    run_id = _create_run_with_draft(env)

    state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.COMPLETED,
        started_at="2026-08-12T10:00:00",
        completed_at="2026-08-12T10:30:00",
        current_round=10,
    )

    _finalize_manifest_for_simulation(SIM_ID, state)

    manifest_path = os.path.join(str(env), "runs", run_id, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["status"] == "final"
    assert data["runtime"]["rounds_completed"] == 10
    assert data["runtime"]["termination_reason"] == "completed"
    assert data["runtime"]["duration_seconds"] == 1800


def test_finalizes_manifest_on_failed(env):
    """S2: bei FAILED trägt das finale Manifest termination_reason=error."""
    run_id = _create_run_with_draft(env)

    state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.FAILED,
        started_at="2026-08-12T10:00:00",
        completed_at="2026-08-12T10:05:00",
        current_round=2,
    )

    _finalize_manifest_for_simulation(SIM_ID, state)

    manifest_path = os.path.join(str(env), "runs", run_id, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["status"] == "final"
    assert data["runtime"]["termination_reason"] == "error"


def test_no_run_found_does_not_raise(env):
    """S3: kein passender Run in der Registry → still, kein Fehler."""
    state = SimulationRunState(
        simulation_id="sim_unknown_no_run",
        runner_status=RunnerStatus.COMPLETED,
    )

    _finalize_manifest_for_simulation("sim_unknown_no_run", state)
    # Kein Assert nötig — bestehen heißt: keine Exception.


def test_missing_draft_manifest_does_not_raise(env):
    """S4: kein Draft-Manifest vorhanden → still, kein Fehler (best-effort)."""
    RunRegistry().create_run(
        "simulation_run",
        SIM_ID,
        linked_ids={"simulation_id": SIM_ID},
    )
    # Kein capture_draft — Datei existiert nicht.

    state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.COMPLETED,
        started_at="2026-08-12T10:00:00",
    )

    _finalize_manifest_for_simulation(SIM_ID, state)

    manifest_path = os.path.join(str(env), "runs", SIM_ID, "manifest.json")
    assert not os.path.exists(manifest_path), (
        "ohne Draft darf kein Manifest neu entstehen — best-effort heißt "
        "'nichts tun', nicht 'stillschweigend ein leeres Manifest anlegen'"
    )


def test_budget_abort_gets_budget_termination_reason_not_user_cancel(env):
    """Codex-Fund: STOPPED wird pauschal als user_cancel gemappt — auch für
    Budget-Aborts, wo termination_reason den Budget-Grund tragen muss."""
    run_id = _create_run_with_draft(env)

    state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.STOPPED,
        started_at="2026-08-12T10:00:00",
        completed_at="2026-08-12T10:10:00",
        current_round=5,
    )

    _finalize_manifest_for_simulation(
        SIM_ID, state, termination_reason_override="budget_tokens"
    )

    manifest_path = os.path.join(str(env), "runs", run_id, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["runtime"]["termination_reason"] == "budget_tokens"
