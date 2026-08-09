"""Tests für POST /api/runs/<id>/resume und POST /api/runs/<id>/stop.

Sub-Slice 35 / Task 28 / Layer 7 — Closes #64.

Abgedeckte Szenarien (Negativpfade; keine echten Dispatcher-Calls):
  1  POST /api/runs/does-not-exist/resume → 404
  2  POST /api/runs/<id>/resume mit unbekanntem run_type → 409
  3  POST /api/runs/none/stop → 400 (ungültiges Format) bzw. 404
  4  POST /api/runs/<id>/stop mit run_type="graph_build" → 409
  5  POST /api/runs/<id>/stop mit simulation_run aber ohne linked simulation_id → 409
  6  Resume 409-Pfad liefert {success:false, error:...}-Envelope
  7  POST /api/runs/<id>/resume report_generate ohne LLM-Key → synchrones 422
     (Copilot PR #466 — kein stiller None-Fallback mit asynchronem Fail)
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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

    artifact_store = InMemoryArtifactStore()

    app = Flask(__name__)
    app.extensions = {"artifact_store": artifact_store}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    registry = RunRegistry()

    yield {
        "app": app,
        "client": app.test_client(),
        "registry": registry,
        "artifact_store": artifact_store,
    }

    RunRegistry._instance = None


def _create_run(
    registry: RunRegistry,
    *,
    run_type: str = "simulation_run",
    entity_id: str = "sim_test",
    simulation_id: str | None = "sim_test",
    project_id: str = "proj_test",
    status: str = "completed",
    message: str = "ok",
    metadata: dict[str, Any] | None = None,
    linked_ids: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if linked_ids is None:
        linked_ids = {}
        if simulation_id is not None:
            linked_ids["simulation_id"] = simulation_id
        linked_ids["project_id"] = project_id

    return registry.create_run(
        run_type=run_type,
        entity_id=entity_id,
        status=status,
        message=message,
        linked_ids=linked_ids,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Test 1: Resume auf nicht-existierenden Run → 404
# ---------------------------------------------------------------------------

def test_resume_unknown_run_returns_404(env):
    # run_[12 hex chars] — gültiges Format, aber kein solcher Eintrag im Registry
    resp = env["client"].post("/api/runs/run_000000000000/resume")

    assert resp.status_code == 404
    payload = resp.get_json()
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Test 2: Resume mit unbekanntem run_type → 409
# ---------------------------------------------------------------------------

def test_resume_unsupported_run_type_returns_409(env):
    run = _create_run(env["registry"], run_type="custom_xyz", status="stopped")

    resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Unsupported run type" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 3: Stop auf nicht-existierenden Run
# ---------------------------------------------------------------------------

def test_stop_unknown_run_returns_404(env):
    # Ungültiges ID-Format → 400; gültiges Format aber kein Eintrag → 404.
    # Wir testen beides: einmal ungültiges Format, einmal gültiges aber fehlendes.
    resp_bad_format = env["client"].post("/api/runs/none/stop")
    assert resp_bad_format.status_code == 400

    resp_missing = env["client"].post("/api/runs/run_aabbccddeeff/stop")
    assert resp_missing.status_code == 404
    payload = resp_missing.get_json()
    assert payload["success"] is False


# ---------------------------------------------------------------------------
# Test 4: Stop auf run_type != simulation_run → 409
# ---------------------------------------------------------------------------

def test_stop_non_simulation_run_returns_409(env):
    run = _create_run(env["registry"], run_type="graph_build", status="processing")

    resp = env["client"].post(f"/api/runs/{run['run_id']}/stop")

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Stop is only supported for simulation_run" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 5: Stop auf simulation_run ohne linked simulation_id → 409
# ---------------------------------------------------------------------------

def test_stop_simulation_run_without_simulation_id_returns_409(env):
    run = _create_run(
        env["registry"],
        run_type="simulation_run",
        status="processing",
        linked_ids={"project_id": "proj_test"},  # deliberate: kein simulation_id
    )

    resp = env["client"].post(f"/api/runs/{run['run_id']}/stop")

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "missing simulation_id linkage" in payload.get("error", "")


# ---------------------------------------------------------------------------
# Test 6: Resume-Fehler liefert {success:false, error:...}-Envelope
# ---------------------------------------------------------------------------

def test_resume_response_uses_json_success_envelope(env):
    """Prüft, dass der handle_api_errors-Decorator auf /resume greift.

    Wir triggern den 409-Pfad (unbekannter run_type), da dieser von
    resume_run() als json_error zurückgegeben wird und dennoch das
    Standard-Envelope nutzt — ohne einen echten Dispatcher zu starten.
    """
    run = _create_run(env["registry"], run_type="unsupported_type", status="failed")

    resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

    assert resp.status_code == 409
    payload = resp.get_json()
    # Pflicht-Envelope-Felder
    assert "success" in payload
    assert payload["success"] is False
    assert "error" in payload
    # Kein Leer-String
    assert payload["error"]


# ---------------------------------------------------------------------------
# Test 7: Resume report_generate ohne LLM-Key → synchrones 422
# Copilot PR #466 — kein stiller None-Fallback mit asynchronem Fail
# ---------------------------------------------------------------------------


def test_resume_report_generate_returns_422_when_llm_client_unavailable(env):
    """POST /api/runs/<id>/resume für report_generate mit model_name, aber ohne
    konfigurierten API-Key → synchrones 422 zurück, kein asynchrones Fail im Thread.

    Verifikation: LLMClient.from_route wirft ValueError (kein Key) →
    der Endpunkt antwortet sofort mit 422 statt still None zu setzen
    und erst im Worker-Thread zu scheitern.
    """
    from unittest.mock import MagicMock

    run = _create_run(
        env["registry"],
        run_type="report_generate",
        entity_id="report_test",
        simulation_id="sim_test",
        status="failed",
        metadata={"llm_model": "gpt-4o-mini", "simulation_id": "sim_test"},
        linked_ids={
            "report_id": "report_test",
            "simulation_id": "sim_test",
            "project_id": "proj_test",
        },
    )

    fake_sim_state = MagicMock()
    fake_sim_state.project_id = "proj_test"
    fake_sim_state.graph_id = "graph_test"

    fake_project = MagicMock()
    fake_project.graph_id = "graph_test"
    fake_project.simulation_requirement = "Test"

    fake_locked_route = ResolvedRoute(
        stage="report_generation",
        provider_id="openai",
        model="gpt-4o-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )

    with (
        patch("app.api.runs.SimulationManager") as mock_sm,
        patch("app.api.runs.ProjectManager") as mock_pm,
        patch("app.api.runs.StageModelRouter") as mock_router,
        patch(
            "app.api.runs.LLMClient.from_route",
            side_effect=ValueError("no API key configured"),
        ) as mock_from_route,
    ):
        mock_sm.return_value.get_simulation.return_value = fake_sim_state
        mock_pm.get_project.return_value = fake_project
        mock_router.return_value.resolve.return_value = fake_locked_route
        # neo4j_storage ist im env-Fixture nicht gesetzt — in app.extensions hinterlegen
        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

        resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

    assert resp.status_code == 422, (
        f"Erwartete 422 bei fehlendem LLM-Key, erhalten: {resp.status_code} — {resp.get_json()}"
    )
    payload = resp.get_json()
    assert payload["success"] is False
    assert payload.get("error")
    assert payload["code"] == "llm_client_unavailable"
    mock_router.assert_called_once_with(run["run_id"])
    mock_router.return_value.resolve.assert_called_once_with("report_generation")
    mock_from_route.assert_called_once()
    route_args, route_kwargs = mock_from_route.call_args
    assert route_args == (fake_locked_route,)
    assert route_kwargs["run_id"] == run["run_id"]


# ---------------------------------------------------------------------------
# Test 8-10: Restart eines simulation_prepare-Runs nutzt den Store-Key statt
# dem .env-Fallback (#798 — Opus-Review-Folgebefund zu #778).
#
# _restart_simulation_prepare übergab manager.prepare_simulation(...) bisher
# ohne llm_runtime; _resolve_llm_connection(None) fiel dadurch beim Restart
# eines Fremd-Provider-Runs still auf Config.LLM_API_KEY/LLM_BASE_URL zurück.
# ---------------------------------------------------------------------------

import threading as _threading  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from app.contracts.llm_routing_contract import ResolvedRoute  # noqa: E402
from app.services.llm_runtime import RuntimeLlmConfig  # noqa: E402


def _run_restart_prepare_sync(run, **prepare_mock_kwargs):
    """Helper: ruft _restart_simulation_prepare(run) mit synchronem Thread auf.

    Gibt (MockMgr, call_kwargs) zurück, wobei call_kwargs die kwargs des
    manager.prepare_simulation(...)-Aufrufs sind.
    """
    from app.api.runs import _restart_simulation_prepare

    def capture_start(self):
        self.run()  # inline statt background

    with patch.object(_threading.Thread, "start", capture_start):
        _restart_simulation_prepare(run)


def test_resume_simulation_prepare_uses_store_key_for_foreign_provider(env):
    """Restart gegen einen Fremd-Provider mit hinterlegtem Store-Key muss
    ``manager.prepare_simulation`` mit einem ``llm_runtime`` aufrufen, der den
    Store-Key trägt — nicht ``llm_runtime=None`` (führt zum .env-Fallback).
    """
    run = _create_run(
        env["registry"],
        run_type="simulation_prepare",
        entity_id="sim_test",
        simulation_id="sim_test",
        status="failed",
    )

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_state.graph_id = "graph_test"
    fake_state.branch_name = "main"

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Test requirement"

    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )

    with (
        patch("app.api.runs.SimulationManager") as MockMgr,
        patch("app.api.runs.ProjectManager") as MockProjMgr,
        patch("app.api.runs.TaskManager") as MockTaskMgr,
        patch("app.api.runs.run_registry") as mock_registry,
        patch("app.api.runs.seed_run_stage_routing"),
        patch("app.api.runs.StageModelRouter") as MockRouter,
        patch(
            "app.api.runs.resolve_route_api_key",
            return_value="store-resolved-key-value",
        ),
    ):
        MockMgr.return_value.get_simulation.return_value = fake_state
        MockMgr.return_value.get_simulation_config.return_value = {"llm_model": "gpt-4o"}
        MockProjMgr.get_project.return_value = fake_project
        MockTaskMgr.return_value.create_task.return_value = "task_001"
        mock_registry.create_run.return_value = {"run_id": "run_new_001"}
        mock_registry.update_run.return_value = None

        router_instance = MockRouter.return_value
        router_instance.resolve.return_value = resolved_route
        router_instance.lock_stage.return_value = resolved_route

        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

        with env["app"].app_context():
            _run_restart_prepare_sync(run)

        assert MockMgr.return_value.prepare_simulation.called
        call_kwargs = MockMgr.return_value.prepare_simulation.call_args.kwargs

    assert "llm_runtime" in call_kwargs
    llm_runtime = call_kwargs["llm_runtime"]
    assert llm_runtime is not None, (
        "Restart darf llm_runtime nicht None lassen — das fällt in "
        "_resolve_llm_connection(None) still auf Config.LLM_API_KEY zurück (#798)"
    )
    assert llm_runtime.api_key == "store-resolved-key-value", (
        f"Erwartet Store-Key aus der Settings-DB, erhalten: {llm_runtime.api_key!r}"
    )
    assert llm_runtime.provider == "openai"
    assert llm_runtime != RuntimeLlmConfig(), (
        "llm_runtime darf nicht der leere Default sein — das wäre äquivalent "
        "zum alten .env-Fallback-Verhalten"
    )


def test_resume_simulation_prepare_falls_back_to_local_no_auth_key(env):
    """Restart gegen einen lokalen No-Auth-Endpoint ohne Store-Key darf keinen
    ValueError werfen und muss den lokalen Platzhalter-Key setzen.
    """
    from app.utils.endpoints import LOCAL_NO_AUTH_API_KEY

    run = _create_run(
        env["registry"],
        run_type="simulation_prepare",
        entity_id="sim_test",
        simulation_id="sim_test",
        status="failed",
    )

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_state.graph_id = "graph_test"
    fake_state.branch_name = "main"

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Test requirement"

    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="openai_compatible",
        model="qwen3:14b",
        base_url_sanitized="http://localhost:11434/v1",
        routing_version=1,
    )

    with (
        patch("app.api.runs.SimulationManager") as MockMgr,
        patch("app.api.runs.ProjectManager") as MockProjMgr,
        patch("app.api.runs.TaskManager") as MockTaskMgr,
        patch("app.api.runs.run_registry") as mock_registry,
        patch("app.api.runs.seed_run_stage_routing"),
        patch("app.api.runs.StageModelRouter") as MockRouter,
        patch("app.api.runs.resolve_route_api_key", return_value=None),
    ):
        MockMgr.return_value.get_simulation.return_value = fake_state
        MockMgr.return_value.get_simulation_config.return_value = {"llm_model": "qwen3:14b"}
        MockProjMgr.get_project.return_value = fake_project
        MockTaskMgr.return_value.create_task.return_value = "task_001"
        mock_registry.create_run.return_value = {"run_id": "run_new_002"}
        mock_registry.update_run.return_value = None

        router_instance = MockRouter.return_value
        router_instance.resolve.return_value = resolved_route
        router_instance.lock_stage.return_value = resolved_route

        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

        with env["app"].app_context():
            _run_restart_prepare_sync(run)

        assert MockMgr.return_value.prepare_simulation.called
        call_kwargs = MockMgr.return_value.prepare_simulation.call_args.kwargs

    llm_runtime = call_kwargs["llm_runtime"]
    assert llm_runtime is not None
    assert llm_runtime.api_key == LOCAL_NO_AUTH_API_KEY


def test_resume_simulation_prepare_raises_without_key_for_non_local_endpoint(env):
    """Fremd-Provider ohne Store-Key und ohne lokalen Endpoint muss hart
    ablehnen — kein stiller .env-Fallback (#798, analog #778).
    """
    run = _create_run(
        env["registry"],
        run_type="simulation_prepare",
        entity_id="sim_test",
        simulation_id="sim_test",
        status="failed",
    )

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_state.graph_id = "graph_test"
    fake_state.branch_name = "main"

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Test requirement"

    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )

    with (
        patch("app.api.runs.SimulationManager") as MockMgr,
        patch("app.api.runs.ProjectManager") as MockProjMgr,
        patch("app.api.runs.TaskManager") as MockTaskMgr,
        patch("app.api.runs.run_registry") as mock_registry,
        patch("app.api.runs.seed_run_stage_routing"),
        patch("app.api.runs.StageModelRouter") as MockRouter,
        patch("app.api.runs.resolve_route_api_key", return_value=None),
    ):
        MockMgr.return_value.get_simulation.return_value = fake_state
        MockMgr.return_value.get_simulation_config.return_value = {"llm_model": "gpt-4o"}
        MockProjMgr.get_project.return_value = fake_project
        MockTaskMgr.return_value.create_task.return_value = "task_001"
        mock_registry.create_run.return_value = {"run_id": "run_new_003"}
        # Persistenz erfolgreich (truthy Dict) — dies ist der Erfolgsfall aus
        # #841. Der Persistenzfehler-Fall (None/Exception) wird separat in
        # test_resume_simulation_prepare_raises_internal_error_when_run_update_returns_none
        # und ..._raises (Issue #844) abgedeckt.
        mock_registry.update_run.return_value = {"run_id": "run_new_003", "status": "failed"}

        router_instance = MockRouter.return_value
        router_instance.resolve.return_value = resolved_route
        router_instance.lock_stage.return_value = resolved_route

        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

        with env["app"].app_context():
            with pytest.raises(ValueError, match="provider_override"):
                _run_restart_prepare_sync(run)

        assert not MockMgr.return_value.prepare_simulation.called

    # Issue #841 — verwaister pending-Run-Datensatz muss auf dem Guard-Pfad
    # als "failed" markiert werden (new_run existiert bereits, Task noch nicht).
    assert mock_registry.update_run.call_count == 1
    update_call = mock_registry.update_run.call_args
    assert update_call.args[0] == "run_new_003"
    assert update_call.kwargs["status"] == "failed"
    assert "provider_override" in update_call.kwargs["message"]
    assert "provider_override" in update_call.kwargs["error"]
    assert not MockTaskMgr.return_value.create_task.called


# ---------------------------------------------------------------------------
# Test 11-12: Issue #844 — Persistenzfehler von update_run im Restart-Guard
#
# Der Restart-Pfad hat an dieser Stelle noch keinen Task (der wird erst nach
# dem Guard erzeugt, Zeile ~579 in runs.py). Liefert update_run() None oder
# wirft es eine Exception, darf der Guard NICHT den regulären
# ValueError("provider_override...") werfen — das würde vortäuschen, der Run
# sei sauber als "failed" persistiert worden. Stattdessen muss ein interner
# Persistenzfehler propagiert werden, und es darf weiterhin kein Task
# erzeugt und kein prepare_simulation gestartet werden.
# ---------------------------------------------------------------------------


def test_resume_simulation_prepare_raises_internal_error_when_run_update_returns_none(env):
    """update_run() liefert None (Run-Manifest zwischenzeitlich verschwunden) im
    Restart-Guard → interner Persistenzfehler statt irreführendem
    ValueError("provider_override..."). Kein Task wird erzeugt,
    prepare_simulation wird nicht gestartet.
    """
    from app.utils.api_errors import ApiErrorCode

    run = _create_run(
        env["registry"],
        run_type="simulation_prepare",
        entity_id="sim_test",
        simulation_id="sim_test",
        status="failed",
    )

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_state.graph_id = "graph_test"
    fake_state.branch_name = "main"

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Test requirement"

    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )

    with (
        patch("app.api.runs.SimulationManager") as MockMgr,
        patch("app.api.runs.ProjectManager") as MockProjMgr,
        patch("app.api.runs.TaskManager") as MockTaskMgr,
        patch("app.api.runs.run_registry") as mock_registry,
        patch("app.api.runs.seed_run_stage_routing"),
        patch("app.api.runs.StageModelRouter") as MockRouter,
        patch("app.api.runs.resolve_route_api_key", return_value=None),
    ):
        MockMgr.return_value.get_simulation.return_value = fake_state
        MockMgr.return_value.get_simulation_config.return_value = {"llm_model": "gpt-4o"}
        MockProjMgr.get_project.return_value = fake_project
        MockTaskMgr.return_value.create_task.return_value = "task_001"
        mock_registry.create_run.return_value = {"run_id": "run_new_004"}
        mock_registry.update_run.return_value = None

        router_instance = MockRouter.return_value
        router_instance.resolve.return_value = resolved_route
        router_instance.lock_stage.return_value = resolved_route

        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

        with env["app"].app_context():
            with pytest.raises(RuntimeError) as exc_info:
                _run_restart_prepare_sync(run)

        assert exc_info.value.args and exc_info.value.args[0] == ApiErrorCode.INTERNAL_ERROR
        # Die irreführende 422-Provider-Key-Meldung darf nicht auftauchen.
        assert "provider_override" not in str(exc_info.value)
        assert not MockMgr.return_value.prepare_simulation.called
        assert not MockTaskMgr.return_value.create_task.called


def test_resume_simulation_prepare_raises_internal_error_when_run_update_raises(env):
    """update_run() wirft einen I/O-/Persistenzfehler im Restart-Guard →
    interner Persistenzfehler statt Maskierung als normaler Guard-Fall.
    Kein Task wird erzeugt, prepare_simulation wird nicht gestartet.
    """
    from app.utils.api_errors import ApiErrorCode

    run = _create_run(
        env["registry"],
        run_type="simulation_prepare",
        entity_id="sim_test",
        simulation_id="sim_test",
        status="failed",
    )

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_state.graph_id = "graph_test"
    fake_state.branch_name = "main"

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Test requirement"

    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
    )

    with (
        patch("app.api.runs.SimulationManager") as MockMgr,
        patch("app.api.runs.ProjectManager") as MockProjMgr,
        patch("app.api.runs.TaskManager") as MockTaskMgr,
        patch("app.api.runs.run_registry") as mock_registry,
        patch("app.api.runs.seed_run_stage_routing"),
        patch("app.api.runs.StageModelRouter") as MockRouter,
        patch("app.api.runs.resolve_route_api_key", return_value=None),
    ):
        MockMgr.return_value.get_simulation.return_value = fake_state
        MockMgr.return_value.get_simulation_config.return_value = {"llm_model": "gpt-4o"}
        MockProjMgr.get_project.return_value = fake_project
        MockTaskMgr.return_value.create_task.return_value = "task_001"
        mock_registry.create_run.return_value = {"run_id": "run_new_005"}
        mock_registry.update_run.side_effect = OSError("disk full: /uploads/run_registry/run_new_005.json")

        router_instance = MockRouter.return_value
        router_instance.resolve.return_value = resolved_route
        router_instance.lock_stage.return_value = resolved_route

        env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

        with env["app"].app_context():
            with pytest.raises(RuntimeError) as exc_info:
                _run_restart_prepare_sync(run)

        assert exc_info.value.args and exc_info.value.args[0] == ApiErrorCode.INTERNAL_ERROR
        assert "provider_override" not in str(exc_info.value)
        assert "disk full" not in str(exc_info.value)
        assert not MockMgr.return_value.prepare_simulation.called
        assert not MockTaskMgr.return_value.create_task.called
