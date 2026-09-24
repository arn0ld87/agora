"""Issue #1557 (Codex P2 an PR #1571): Der Runner-Sync darf den i18n-Schlüssel
eines Simulationslaufs nicht verwerfen.

``monitor_simulation`` ruft alle zwei Sekunden ``save_state`` auf; der
Registry-Callback in ``SimulationRunner._save_run_state`` schrieb dabei
``message="Runner status: …"`` ohne ``message_key``. Seit ``update_run`` einen
fehlenden Schlüssel bei neuer Meldung bewusst leert, überlebte der beim Start
gesetzte ``run.simulation_run_started`` nur bis zum ersten Poll — Shelf und
Dossier fielen danach auf den englischen Klartext zurück. Zwei Ebenen:

1. Registry-Lebenszyklus queued → started → Runner-Poll → completed mit dem
   Schlüssel, den der Runner jetzt mitschickt.
2. Der Callback selbst: ``_save_run_state`` reicht den Schlüssel an
   ``update_run`` durch, und ``_correct_stale_run_state`` ebenfalls.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytest

from app.services.run_registry import RunRegistry
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState
from app.services import simulation_runner as runner_module
from app.services.simulation_runner import SimulationRunner, _runner_status_message_key

SIM_ID = "sim_message_key_1557"


def _reset_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunRegistry:
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(tmp_path))
    RunRegistry._instance = None
    return RunRegistry()


@pytest.mark.parametrize("status", list(RunnerStatus))
def test_every_runner_status_has_a_message_key(status: RunnerStatus) -> None:
    assert _runner_status_message_key(status) == f"run.runner_status_{status.value}"


def test_registry_lifecycle_keeps_localized_key_across_runner_polls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _reset_registry(tmp_path, monkeypatch)
    run = registry.create_run(
        run_type="simulation_run",
        entity_id=SIM_ID,
        message="Simulation run queued",
        message_key="run.simulation_run_queued",
    )
    run_id = run["run_id"]

    registry.update_run(
        run_id,
        status="processing",
        message="Simulation run started",
        message_key="run.simulation_run_started",
    )
    # Runner-Poll, wie ihn der Callback nach dem Fix schreibt.
    registry.update_run(
        run_id,
        status=RunnerStatus.RUNNING.value,
        progress=40,
        message=f"Runner status: {RunnerStatus.RUNNING.value}",
        message_key=_runner_status_message_key(RunnerStatus.RUNNING),
    )
    polled = registry.get_run(run_id)
    assert polled is not None
    assert polled["message_key"] == "run.runner_status_running"

    registry.update_run(
        run_id,
        status=RunnerStatus.COMPLETED.value,
        progress=100,
        message=f"Runner status: {RunnerStatus.COMPLETED.value}",
        message_key=_runner_status_message_key(RunnerStatus.COMPLETED),
    )
    finished = registry.get_run(run_id)
    assert finished is not None
    assert finished["message_key"] == "run.runner_status_completed"


class _RecordingRegistry:
    """RunRegistry-Doppel: liefert einen Lauf und zeichnet ``update_run`` auf."""

    calls: List[Dict[str, Any]] = []

    def __init__(self) -> None:
        pass

    def get_latest_by_linked_id(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {"run_id": "run_1557", "status": "processing", "linked_ids": {}}

    def list_runs(self, *_args: Any, **_kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "run_id": "run_1557",
                "run_type": "simulation_run",
                "status": "processing",
                "linked_ids": {"simulation_id": SIM_ID},
                "created_at": datetime.now().isoformat(),
            }
        ]

    def update_run(self, run_id: str, **updates: Any) -> Dict[str, Any]:
        type(self).calls.append({"run_id": run_id, **updates})
        return {"run_id": run_id, **updates}


@pytest.fixture()
def recording_registry(monkeypatch: pytest.MonkeyPatch) -> type[_RecordingRegistry]:
    _RecordingRegistry.calls = []
    monkeypatch.setattr(runner_module, "RunRegistry", _RecordingRegistry)
    monkeypatch.setattr(SimulationRunner, "_run_states", {})
    return _RecordingRegistry


def test_save_run_state_sync_propagates_runner_status_key(
    monkeypatch: pytest.MonkeyPatch, recording_registry: type[_RecordingRegistry]
) -> None:
    """Der Poll-Callback schickt den Schlüssel mit — der Startschlüssel wird
    durch einen Runner-Schlüssel ersetzt, nicht durch ``None``."""

    def fake_save(state: SimulationRunState, _base_dir: str, **callbacks: Any) -> None:
        callbacks["run_registry_sync"](state.simulation_id, {"progress_percent": 40})

    monkeypatch.setattr(runner_module, "_save_run_state_fn", fake_save)
    state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.RUNNING,
        started_at=datetime.now().isoformat(),
    )

    SimulationRunner._save_run_state(state)

    assert len(recording_registry.calls) == 1
    call = recording_registry.calls[0]
    assert call["message"] == "Runner status: running"
    assert call["message_key"] == "run.runner_status_running"


def test_stale_run_state_correction_propagates_runner_status_key(
    monkeypatch: pytest.MonkeyPatch, recording_registry: type[_RecordingRegistry]
) -> None:
    """Die Restart-Reconciliation (#1476) trägt denselben Schlüssel."""
    def fake_save(state: SimulationRunState, _base_dir: str, **callbacks: Any) -> None:
        callbacks["run_registry_sync"](state.simulation_id, {"progress_percent": 0})

    monkeypatch.setattr(runner_module, "_save_run_state_fn", fake_save)
    state = SimulationRunState(
        simulation_id=SIM_ID,
        runner_status=RunnerStatus.FAILED,
        started_at=datetime.now().isoformat(),
        error="process_restart",
    )

    SimulationRunner._correct_stale_run_state(state, requested_run_id="run_1557")

    keyed = [c for c in recording_registry.calls if "message_key" in c]
    assert keyed, recording_registry.calls
    assert keyed[-1]["message_key"] == "run.runner_status_failed"
    assert keyed[-1]["termination_reason"] == "process_restart"
