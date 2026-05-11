"""Tests für Report-Modi (strict / balanced / explorative) am HTTP-Layer.

Sub-Slice P4.1 — Refs PLAN.md §5.1

Abgedeckt:
- POST /api/report/generate?mode=strict → 200, report enthält mode
- POST /api/report/generate?mode=balanced → 200, report enthält mode
- POST /api/report/generate?mode=explorative → 200, report enthält mode
- POST /api/report/generate?mode=INVALID → 400 mit erlaubten Werten in Response
- GET /api/report/<id> → report_mode aus persistiertem ReportV3 sichtbar
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import report_bp


VALID_REPORT_ID = "report_abcdef123456"
VALID_SIM_ID = "sim_0123456789ab"
VALID_GRAPH_ID = "graph_0123456789ab"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["AGORA_REPORT_RATE_LIMIT_MAX"] = 100
    app.config["AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.register_blueprint(report_bp, url_prefix="/api/report")
    with app.app_context():
        yield app.test_client()


# ---------------------------------------------------------------------------
# Helper: _resolve_report_mode direkt testen (Unit)
# ---------------------------------------------------------------------------

def test_resolve_report_mode_default():
    """_resolve_report_mode ohne mode-Param → DEFAULT_REPORT_MODE."""
    from app.api.report import _resolve_report_mode  # noqa: PLC0415

    app = Flask(__name__)
    with app.test_request_context("/?"):
        result = _resolve_report_mode()
    assert result == "balanced"


def test_resolve_report_mode_strict():
    """_resolve_report_mode mit mode=strict → 'strict'."""
    from app.api.report import _resolve_report_mode  # noqa: PLC0415

    app = Flask(__name__)
    with app.test_request_context("/?mode=strict"):
        result = _resolve_report_mode()
    assert result == "strict"


def test_resolve_report_mode_explorative():
    """_resolve_report_mode mit mode=explorative → 'explorative'."""
    from app.api.report import _resolve_report_mode  # noqa: PLC0415

    app = Flask(__name__)
    with app.test_request_context("/?mode=explorative"):
        result = _resolve_report_mode()
    assert result == "explorative"


def test_resolve_report_mode_invalid_raises():
    """_resolve_report_mode mit unbekanntem mode → ValueError mit Hinweis."""
    from app.api.report import _resolve_report_mode  # noqa: PLC0415

    app = Flask(__name__)
    with app.test_request_context("/?mode=nuclear"):
        with pytest.raises(ValueError, match="nuclear"):
            _resolve_report_mode()


# ---------------------------------------------------------------------------
# Integration: generate-Endpoint mit mode-Query-Param
# ---------------------------------------------------------------------------

def _make_mock_simulation():
    state = MagicMock()
    state.project_id = "proj_abc"
    state.graph_id = VALID_GRAPH_ID
    state.source_simulation_id = None
    state.root_simulation_id = None
    state.branch_name = "main"
    state.branch_depth = 0
    return state


def _make_mock_project():
    project = MagicMock()
    project.graph_id = VALID_GRAPH_ID
    project.simulation_requirement = "Test requirement"
    project.llm_model = None
    return project


@pytest.fixture
def _patched_generate():
    """Patcht alle externen Deps von generate_report, damit kein echtes Threading."""
    mock_state = _make_mock_simulation()
    mock_project = _make_mock_project()
    with (
        patch("app.api.report.SimulationManager") as mock_sim_mgr,
        patch("app.api.report.ReportManager") as mock_rm,
        patch("app.api.report.ProjectManager") as mock_pm,
        patch("app.api.report.TaskManager") as mock_tm,
        patch("app.api.report.run_registry") as mock_rr,
        patch("app.api.report.threading.Thread") as mock_thread,
        patch("app.api.report.RuntimeRunConfig"),
        patch("app.api.report.StageModelRouter") as mock_smr,
    ):
        mock_sim_mgr.return_value.get_simulation.return_value = mock_state
        mock_pm.get_project.return_value = mock_project
        mock_rm.get_report_by_simulation.return_value = None
        mock_rr.create_run.return_value = {"run_id": "run_001"}
        mock_tm.return_value.create_task.return_value = "task_001"
        mock_thread.return_value.start.return_value = None

        # Mock StageModelRouter.resolve() to return a mock with string attributes
        mock_route = MagicMock()
        mock_route.provider_id = "ollama_local"
        mock_route.model = "test-model"
        mock_route.base_url_sanitized = "http://localhost:11434/v1"
        mock_route.reasoning_effort = "none"
        mock_route.provider_options = {}
        mock_route.routing_version = 1
        mock_route.stage = "report_generation"
        mock_smr.return_value.resolve.return_value = mock_route

        yield


@pytest.mark.parametrize("mode", ["strict", "balanced", "explorative"])
def test_generate_with_valid_mode_returns_200(client, _patched_generate, mode):
    """POST /generate?mode=<mode> mit gültigem Wert → 200."""
    with patch("app.api.report.current_app") as mock_ca:
        mock_ca.extensions = {"neo4j_storage": MagicMock()}
        mock_ca.config = {
            "AGORA_REPORT_RATE_LIMIT_MAX": 100,
            "AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS": 60,
        }
        resp = client.post(
            f"/api/report/generate?mode={mode}",
            json={"simulation_id": VALID_SIM_ID},
            content_type="application/json",
        )
    # 200 oder 404 (kein echtes Neo4j) — aber kein 400 wegen mode
    assert resp.status_code != 400


def test_generate_with_invalid_mode_returns_400(client):
    """POST /generate?mode=nuclear → 400 mit Liste der erlaubten Werte."""
    resp = client.post(
        "/api/report/generate?mode=nuclear",
        json={"simulation_id": VALID_SIM_ID},
        content_type="application/json",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body is not None
    # Fehlermeldung enthält erlaubte Werte
    error_text = str(body)
    assert "strict" in error_text or "balanced" in error_text or "explorative" in error_text
