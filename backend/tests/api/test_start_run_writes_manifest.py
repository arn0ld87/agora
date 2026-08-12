"""Issue #763 (Ticket 9) — POST /api/simulation/start schreibt ein Draft-Manifest.

Vor diesem Slice existierte die komplette Manifest-Infrastruktur
(ManifestCapture, Replay-/Export-Endpoint, Frontend-UI), aber kein einziger
Aufrufer im echten Run-Start-Pfad — ein neuer Run erzeugte kein manifest.json,
und Replay/Export scheiterten für ihn mit 400/404. Dieser Test fährt den
echten Start-Endpunkt (wie test_start_run_never_stuck_pending.py) und prüft,
dass anschließend ein manifest.json im Run-Verzeichnis liegt.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.llm_routing_contract import ResolvedRoute

VALID_SIM_ID = "sim_0123456789ab"
RUN_ID = "run_9763manifest"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("AGORA_INSTANCE_DIR", str(tmp_path))
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["TESTING"] = True
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    with app.test_request_context(), app.test_client() as test_client:
        yield test_client


def _stub_start_infra(monkeypatch) -> MagicMock:
    from app.services.simulation_manager import SimulationStatus

    state = MagicMock()
    state.status = SimulationStatus.READY
    state.project_id = "proj-x"
    state.graph_id = "graph_763"
    state.branch_name = None
    state.source_simulation_id = None
    state.root_simulation_id = None
    state.branch_depth = 0

    manager = MagicMock(get_simulation=MagicMock(return_value=state))
    manager.get_simulation_config.return_value = {"llm_model": "qwen3", "max_agents": 50}
    monkeypatch.setattr("app.api.simulation_run.SimulationManager", lambda: manager)

    registry = MagicMock()
    registry.create_run.return_value = {"run_id": RUN_ID}
    monkeypatch.setattr("app.api.simulation_run.run_registry", registry)
    monkeypatch.setattr("app.api.simulation_run.seed_run_stage_routing", MagicMock())
    monkeypatch.setattr("app.api.simulation_run._apply_budget_to_simulation", MagicMock())
    monkeypatch.setattr("app.api.simulation_run._simulation_run_artifacts", lambda _s: [])
    monkeypatch.setattr(
        "app.api.simulation_run._simulation_resume_capability",
        lambda _s, _st: {"resumable": False},
    )
    monkeypatch.setattr(
        "app.api.simulation_run.Config.PERSONA_REVIEW_ENABLED", False, raising=False
    )
    monkeypatch.setattr(
        "app.api.simulation_run._check_simulation_prepared", lambda _sid: (True, {})
    )

    resolved = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="conn-local",
        model="qwen3",
        base_url_sanitized="http://localhost:1234/v1",
        routing_version=1,
        provider_options={"base_url": "http://localhost:1234/v1"},
    )
    router = MagicMock()
    router.resolve.return_value = resolved
    router.lock_stage.return_value = resolved
    monkeypatch.setattr("app.api.simulation_run.StageModelRouter", lambda _rid: router)
    monkeypatch.setattr(
        "app.api.simulation_run.resolve_route_api_key", lambda _r, _rt: "sk-local"
    )
    monkeypatch.setattr(
        "app.api.simulation_run.build_route_subprocess_env", lambda _r, _k, _rid: {}
    )
    monkeypatch.setattr("app.api.simulation_run.get_artifact_store", lambda: MagicMock())
    monkeypatch.setattr(
        "app.api.simulation_common.get_artifact_store", lambda: MagicMock(), raising=False
    )

    runner = MagicMock()
    runner.start_simulation.return_value = MagicMock(
        to_dict=MagicMock(return_value={"simulation_id": VALID_SIM_ID})
    )
    monkeypatch.setattr("app.api.simulation_run.SimulationRunner", runner)
    return registry


def _start(client):
    return client.post(
        "/api/simulation/start",
        json={"simulation_id": VALID_SIM_ID, "platform": "parallel"},
    )


def test_erfolgreicher_start_schreibt_ein_draft_manifest(client, monkeypatch, tmp_path):
    """Kern des Slices: nach erfolgreichem Start liegt manifest.json vor."""
    _stub_start_infra(monkeypatch)

    response = _start(client)

    assert response.status_code == 200, response.data

    manifest_path = os.path.join(str(tmp_path), "runs", RUN_ID, "manifest.json")
    assert os.path.exists(manifest_path), (
        "kein manifest.json nach erfolgreichem Run-Start — "
        "ManifestCapture ist nicht verdrahtet"
    )

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["status"] == "draft"
    assert data["run_id"] == RUN_ID
    assert data["inputs"]["graph_id"] == "graph_763"
    assert data["routing"]["stages"]["simulation_rounds"]["model"] == "qwen3"
    assert data["routing"]["stages"]["simulation_rounds"]["provider"] == "conn-local"


def test_manifest_fehler_lässt_den_run_trotzdem_erfolgreich_starten(
    client, monkeypatch, tmp_path
):
    """Best-Effort-Garantie: ein kaputter Manifest-Schreibvorgang darf den
    bereits erfolgreich gestarteten Run nicht zu Fall bringen."""
    _stub_start_infra(monkeypatch)
    monkeypatch.setattr(
        "app.api.simulation_run.ManifestCapture.capture_draft_best_effort",
        MagicMock(side_effect=RuntimeError("sollte geschluckt werden")),
    )

    response = _start(client)

    assert response.status_code == 200, response.data
