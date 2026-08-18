"""Tests für POST /api/runs/<id>/cancel.

Regression für den Abbrechen-Button in Schritt 3: das Frontend
(``Step3Simulation.vue`` → ``cancelRun(props.simulationId)``) kennt nur die
``simulation_id`` und schickt sie an diesen Endpunkt. ``run_id`` und
``simulation_id`` haben unterschiedliche Formate (``run_``/``sim_`` + 12 Hex)
und werden unabhängig vergeben — kein ``create_run``-Aufruf im Repository setzt
``run_id`` explizit. Vor dem Fix scheiterte deshalb jeder Klick an
``validate_run_id`` mit HTTP 400, ohne irgendetwas abzubrechen.

**Prüfumfang:** diese Tests decken die ID-Auflösung und das gesetzte
Cancel-Flag ab — nicht die Terminierung des Simulations-Workers. Für
``run_type="simulation_run"`` liest niemand das Flag: ``is_cancel_requested``
hat backendweit genau einen Consumer (``report_agent/workflow.py``), und
``simulation_runner.py`` enthält kein Cancel-Signal. Ein Test, der hier
Worker-Terminierung assertierte, würde etwas behaupten, das der Produktivcode
nicht leistet. Der Defekt ist als
`#1082 <https://github.com/arn0ld87/agora/issues/1082>`_ ausgelagert.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.run_registry import RunRegistry
from app.services.sim.cancel_flag import clear_cancel, is_cancel_requested
from app.services.simulation_manager import SimulationManager


@pytest.fixture()
def env(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations")
    )
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    RunRegistry._instance = None
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)

    app = Flask(__name__)
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    yield {"client": app.test_client(), "registry": RunRegistry()}

    RunRegistry._instance = None


def _new_simulation_id() -> str:
    """Erzeugt eine ID im echten Produktivformat.

    ``SimulationManager`` vergibt ``f"sim_{uuid4().hex[:12]}"``; ein
    handgeschriebenes ``sim_test`` würde ``validate_simulation_id`` nicht
    passieren und den Auflösungspfad am Test vorbeiführen.
    """
    return f"sim_{uuid.uuid4().hex[:12]}"


def _create_processing_run(
    registry: RunRegistry, simulation_id: str
) -> dict[str, Any]:
    return registry.create_run(
        run_type="simulation_run",
        entity_id=simulation_id,
        status="processing",
        message="running",
        linked_ids={"simulation_id": simulation_id, "project_id": "proj_test"},
        metadata={},
    )


def test_cancel_accepts_simulation_id_and_sets_flag(env):
    """Kern der Regression: sim_-ID → 202 + gesetztes Cancel-Flag."""
    simulation_id = _new_simulation_id()
    run = _create_processing_run(env["registry"], simulation_id)
    clear_cancel(run["run_id"])

    resp = env["client"].post(f"/api/runs/{simulation_id}/cancel")

    assert resp.status_code == 202
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["status"] == "cancel_requested"
    # Die Antwort trägt die aufgelöste run_-ID, nicht die übergebene sim_-ID.
    assert payload["run_id"] == run["run_id"]
    assert payload["run_id"].startswith("run_")
    assert is_cancel_requested(run["run_id"]) is True

    clear_cancel(run["run_id"])


def test_cancel_still_accepts_run_id(env):
    """Der bestehende run_-Pfad bleibt unverändert."""
    simulation_id = _new_simulation_id()
    run = _create_processing_run(env["registry"], simulation_id)
    clear_cancel(run["run_id"])

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 202
    assert resp.get_json()["run_id"] == run["run_id"]
    assert is_cancel_requested(run["run_id"]) is True

    clear_cancel(run["run_id"])


def test_cancel_unknown_simulation_id_returns_404(env):
    """Formal gültige, aber unbekannte sim_-ID bleibt 404 — nicht 400, nicht 202."""
    resp = env["client"].post(f"/api/runs/{_new_simulation_id()}/cancel")

    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_cancel_rejects_malformed_id_with_400(env):
    """Weder run_- noch sim_-Format → weiterhin 400."""
    resp = env["client"].post("/api/runs/not-an-id/cancel")

    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_cancel_non_processing_run_returns_400(env):
    """Statusprüfung greift auch auf dem sim_-Pfad."""
    simulation_id = _new_simulation_id()
    run = env["registry"].create_run(
        run_type="simulation_run",
        entity_id=simulation_id,
        status="completed",
        message="done",
        linked_ids={"simulation_id": simulation_id, "project_id": "proj_test"},
        metadata={},
    )

    resp = env["client"].post(f"/api/runs/{simulation_id}/cancel")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["code"] == "run_not_active"
    assert is_cancel_requested(run["run_id"]) is False


# ---------------------------------------------------------------------------
# Issue #1176 — Phantom-Runs sind abbrechbar
# ---------------------------------------------------------------------------


def _create_pending_run(registry: RunRegistry, simulation_id: str) -> dict[str, Any]:
    """Ein Run, wie ``_register_start_run`` ihn anlegt — vor dem Prozessstart."""
    return registry.create_run(
        run_type="simulation_run",
        entity_id=simulation_id,
        status="pending",
        message="Simulation run queued",
        linked_ids={"simulation_id": simulation_id, "project_id": "proj_test"},
        metadata={},
    )


def test_cancel_beendet_einen_pending_run(env):
    """Vor #1176 antwortete die Route hier 400 ``run_not_active``.

    Ein Run in ``pending`` hat keinen Subprozess, den ein Cancel-Flag erreichen
    könnte — kooperativer Abbruch läuft ins Leere. Die Route lehnte ihn deshalb
    ab, womit er weder abbrechbar war (nicht aktiv) noch je aktiv wurde (der
    Start lief nie durch). Neun solcher Runs standen dauerhaft in der Liste.
    """
    simulation_id = _new_simulation_id()
    run = _create_pending_run(env["registry"], simulation_id)

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 200, resp.data
    assert resp.get_json()["status"] == "cancelled"
    assert env["registry"].get_run(run["run_id"])["status"] == "failed"


def test_cancel_lehnt_einen_bereits_beendeten_run_weiterhin_ab(env):
    """Gegenprobe: der neue Zweig darf nicht jeden Status durchlassen."""
    simulation_id = _new_simulation_id()
    run = _create_pending_run(env["registry"], simulation_id)
    env["registry"].update_run(run["run_id"], status="completed")

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "run_not_active"


# ---------------------------------------------------------------------------
# Review-Finding PR #1371, Befund 1 (BLOCKER): graph_build- und
# simulation_prepare-Runs verknüpfen NIE eine simulation_id
# (services/graph_build.py setzt project_id/graph_id/task_id; s. Docstring
# von ``_get_run_by_run_or_simulation_id`` weiter oben). Vor dem Fix
# scheiterte ``cancel_run`` für diese run_types unbedingt mit 409, BEVOR
# ``_request_cancel`` überhaupt lief — der kooperative Abbruchpfad in
# ``services/graph_build.py``/``graph_builder.py`` war über die API tot,
# obwohl er unit-getestet war (die Unit-Tests riefen ``request_cancel``
# direkt auf und liefen nie durch diese Route). Diese Tests fahren den
# ECHTEN Endpunktpfad, nicht die Service-Funktion.
# ---------------------------------------------------------------------------


def _create_processing_graph_build_run(registry: RunRegistry) -> dict[str, Any]:
    """Spiegelt ``services/graph_build.py``: linked_ids trägt project_id/graph_id/
    task_id, NIE simulation_id."""
    return registry.create_run(
        run_type="graph_build",
        entity_id="proj_test",
        status="processing",
        message="Graph build in progress",
        linked_ids={"project_id": "proj_test", "graph_id": "graph_test", "task_id": "task_test"},
        metadata={},
    )


def test_cancel_graph_build_run_ohne_simulation_id_setzt_flag(env):
    """Der BLOCKER-Fix: graph_build-Run ohne simulation_id-Verknüpfung muss
    über die echte Route abbrechbar sein — 202, nicht 409."""
    run = _create_processing_graph_build_run(env["registry"])
    clear_cancel(run["run_id"])

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 202, resp.get_json()
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["status"] == "cancel_requested"
    assert payload["run_id"] == run["run_id"]
    assert is_cancel_requested(run["run_id"]) is True

    clear_cancel(run["run_id"])


def _create_processing_prepare_run(registry: RunRegistry, simulation_id: str) -> dict[str, Any]:
    return registry.create_run(
        run_type="simulation_prepare",
        entity_id=simulation_id,
        status="processing",
        message="Simulation preparation in progress",
        linked_ids={"simulation_id": simulation_id, "project_id": "proj_test"},
        metadata={},
    )


def test_cancel_simulation_prepare_run_setzt_flag(env):
    """simulation_prepare verknüpft zwar eine simulation_id, sie ist aber
    nicht mehr Voraussetzung fürs Flag-Setzen (nur simulation_run erzwingt
    sie jetzt noch) — Regressionsschutz gegen ein zu enges Redesign."""
    simulation_id = _new_simulation_id()
    run = _create_processing_prepare_run(env["registry"], simulation_id)
    clear_cancel(run["run_id"])

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 202, resp.get_json()
    assert is_cancel_requested(run["run_id"]) is True

    clear_cancel(run["run_id"])


def test_cancel_simulation_run_ohne_simulation_id_bleibt_409(env):
    """Gegenprobe: für simulation_run bleibt die 409-Schranke bestehen —
    dort braucht der OASIS-Subprozesspfad die Verknüpfung fachlich."""
    run = env["registry"].create_run(
        run_type="simulation_run",
        entity_id="proj_test",
        status="processing",
        message="running",
        linked_ids={"project_id": "proj_test"},  # deliberate: keine simulation_id
        metadata={},
    )

    resp = env["client"].post(f"/api/runs/{run['run_id']}/cancel")

    assert resp.status_code == 409
    assert "missing simulation_id linkage" in resp.get_json().get("error", "")
    assert is_cancel_requested(run["run_id"]) is False
