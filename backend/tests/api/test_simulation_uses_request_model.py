"""Sub-Slice C — Verifikation, dass llm_model aus dem Request-Body an den
jeweiligen Service-Konstruktor durchgereicht wird.

Zwei reale Lücken wurden lokalisiert:

1. ``/api/simulation/generate-profiles`` (simulation_history.py): konstruierte
   ``OasisProfileGenerator()`` ohne ``model_name`` — das request-body-Feld
   ``llm_model`` wurde vollständig ignoriert.

2. ``_resume_report_generate`` (runs.py): konstruierte ``ReportAgent(...)``
   ebenfalls ohne ``model_name`` — der Resume-Pfad ignorierte jedes Model-Override.

Wege die bereits korrekt verdrahtet sind (Regression-Guards):
- ``/api/simulation/prepare`` → ``prepare_service`` → ``OasisProfileGenerator``
- ``/api/report/generate`` → ``ReportAgent``
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation_bp


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

VALID_GRAPH_ID = "abcdef0123456789abcdef0123456789"


@pytest.fixture
def sim_history_client(monkeypatch):
    """Flask test client with simulation blueprint + mocked neo4j storage."""
    app = Flask(__name__)
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 20
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    storage = MagicMock(name="Neo4jStorage")
    app.extensions = {"neo4j_storage": storage}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client(), storage


# ---------------------------------------------------------------------------
# Gap 1: /api/simulation/generate-profiles
# ---------------------------------------------------------------------------


def test_generate_profiles_endpoint_passes_llm_model_to_generator(
    sim_history_client, monkeypatch
):
    """POST /api/simulation/generate-profiles mit ``llm_model`` muss
    ``OasisProfileGenerator`` mit diesem model_name konstruieren.

    Vor dem Fix wurde ``OasisProfileGenerator()`` ohne Argumente aufgerufen,
    sodass das Frontend-gewählte Modell komplett ignoriert wurde.
    """
    client, storage = sim_history_client

    # EntityReader.filter_defined_entities mock
    fake_entity = MagicMock(name="EntityNode")
    fake_filtered = MagicMock()
    fake_filtered.filtered_count = 1
    fake_filtered.entity_types = {"Person"}
    fake_filtered.entities = [fake_entity]

    # OasisProfileGenerator mock
    fake_profile = MagicMock()
    fake_profile.to_reddit_format.return_value = {
        "user_id": 1,
        "username": "test_user",
        "name": "Test",
        "bio": "bio",
        "persona": "persona",
    }

    captured_model_name = {}

    class FakeProfileGenerator:
        def __init__(self, *args, **kwargs):
            captured_model_name["model_name"] = kwargs.get("model_name")

        def generate_profiles_from_entities(self, *args, **kwargs):
            return [fake_profile]

    monkeypatch.setattr(
        "app.api.simulation_history.EntityReader",
        lambda storage: MagicMock(
            filter_defined_entities=MagicMock(return_value=fake_filtered)
        ),
    )
    monkeypatch.setattr(
        "app.api.simulation_history.OasisProfileGenerator",
        FakeProfileGenerator,
    )

    response = client.post(
        "/api/simulation/generate-profiles",
        json={
            "graph_id": VALID_GRAPH_ID,
            "llm_model": "qwen3:14b",
            "platform": "reddit",
        },
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert captured_model_name.get("model_name") == "qwen3:14b", (
        f"OasisProfileGenerator wurde mit model_name={captured_model_name.get('model_name')!r} "
        f"konstruiert, erwartet 'qwen3:14b'"
    )


def test_generate_profiles_endpoint_falls_back_when_no_llm_model(
    sim_history_client, monkeypatch
):
    """Ohne ``llm_model`` im Body muss ``model_name=None`` weitergereicht
    werden (Env-Fallback im Generator selbst).
    """
    client, storage = sim_history_client

    fake_entity = MagicMock(name="EntityNode")
    fake_filtered = MagicMock()
    fake_filtered.filtered_count = 1
    fake_filtered.entity_types = {"Person"}
    fake_filtered.entities = [fake_entity]

    fake_profile = MagicMock()
    fake_profile.to_reddit_format.return_value = {
        "user_id": 1,
        "username": "test_user",
        "name": "Test",
        "bio": "bio",
        "persona": "persona",
    }

    captured_model_name = {}

    class FakeProfileGenerator:
        def __init__(self, *args, **kwargs):
            captured_model_name["model_name"] = kwargs.get("model_name")

        def generate_profiles_from_entities(self, *args, **kwargs):
            return [fake_profile]

    monkeypatch.setattr(
        "app.api.simulation_history.EntityReader",
        lambda storage: MagicMock(
            filter_defined_entities=MagicMock(return_value=fake_filtered)
        ),
    )
    monkeypatch.setattr(
        "app.api.simulation_history.OasisProfileGenerator",
        FakeProfileGenerator,
    )

    response = client.post(
        "/api/simulation/generate-profiles",
        json={"graph_id": VALID_GRAPH_ID},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    # model_name=None → OasisProfileGenerator nutzt Config.LLM_MODEL_NAME als Fallback
    assert captured_model_name.get("model_name") is None, (
        f"Erwartet model_name=None, erhielt {captured_model_name.get('model_name')!r}"
    )


# ---------------------------------------------------------------------------
# Gap 2: runs.py _resume_report_generate
# ---------------------------------------------------------------------------


def test_resume_report_generate_passes_llm_model_from_run_metadata():
    """``_resume_report_generate`` muss ``ReportAgent`` mit dem in der Run-Config
    gespeicherten ``llm_model`` konstruieren.

    Vor dem Fix wurde ``ReportAgent(...)`` ohne ``model_name`` aufgerufen.
    """
    from app.api.runs import _resume_report_generate
    from app.services.report_agent import ReportStatus

    captured_kwargs: dict = {}

    class FakeReportAgent:
        def __init__(self, *args, **kwargs):
            captured_kwargs.update(kwargs)

        def generate_report(self, *args, **kwargs):
            report = MagicMock()
            report.status = ReportStatus.COMPLETED
            report.report_id = "report_test_abc"
            return report

    run = {
        "run_id": "run_test_001",
        "run_type": "report_generate",
        "entity_id": "report_test_abc",
        "linked_ids": {
            "simulation_id": "sim_0123456789ab",
            "report_id": "report_test_abc",
        },
        "metadata": {"llm_model": "custom-model:7b"},
    }

    fake_state = MagicMock()
    fake_state.project_id = "proj_test"
    fake_project = MagicMock()
    fake_project.graph_id = VALID_GRAPH_ID
    fake_project.simulation_requirement = "Test requirement"
    fake_graph_tools = MagicMock()

    with (
        patch("app.api.runs.SimulationManager") as MockMgr,
        patch("app.api.runs.ProjectManager") as MockProjMgr,
        patch("app.api.runs.TaskManager") as MockTaskMgr,
        patch("app.api.runs.GraphToolsService", return_value=fake_graph_tools),
        patch("app.api.runs.ReportAgent", FakeReportAgent),
        patch("app.api.runs.ReportManager"),
        patch("app.api.runs.run_registry") as mock_registry,
        # LLMClient muss gemockt werden: ohne API-Key wirft der Konstruktor einen
        # ValueError, der seit Copilot PR #466 zu einem synchronen 422 führt.
        # Der Test prüft den Erfolgs-Pfad — daher simulieren wir einen validen Client.
        patch("app.api.runs.LLMClient") as MockLLMClient,
    ):
        MockLLMClient.return_value = MagicMock(name="FakeLLMClient")
        MockMgr.return_value.get_simulation.return_value = fake_state
        MockProjMgr.get_project.return_value = fake_project
        task_mock = MagicMock()
        MockTaskMgr.return_value.create_task.return_value = "task_001"
        MockTaskMgr.return_value.get_task.return_value = task_mock
        mock_registry.update_run.return_value = None

        # Simulate a Flask application context so current_app works
        app = Flask(__name__)
        fake_neo4j = MagicMock()
        app.extensions = {"neo4j_storage": fake_neo4j}

        with app.app_context():
            # _resume_report_generate spawns a thread; we need to run it sync
            # so we intercept at the thread level.
            import threading as _threading

            def capture_start(self):
                self.run()  # run inline instead of in background

            with patch.object(_threading.Thread, "start", capture_start):
                _resume_report_generate(run)

    assert "model_name" in captured_kwargs, (
        "ReportAgent wurde ohne model_name konstruiert. "
        f"Übergebene kwargs: {captured_kwargs}"
    )
    assert captured_kwargs["model_name"] == "custom-model:7b", (
        f"Erwartet model_name='custom-model:7b', erhielt {captured_kwargs.get('model_name')!r}"
    )
