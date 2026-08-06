"""Regressionstests für Budget-Enforcement in Report-Resume und Prepare (#984).

Vor dem Fix baute ``_resume_report_generate`` seinen ``LLMClient`` ohne
``run_id`` (kein Budget-Enforcer), und die Prepare-Phasen (Persona-/Config-
Generierung) erzeugten run-gebundene Clients ebenfalls ohne ``run_id`` —
harte Budgets wurden auf beiden Pfaden vollständig umgangen.
"""

from __future__ import annotations

import os
import threading as _threading
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.run_budget import BudgetExceededError
from app.services.run_registry import RunRegistry
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
    app.extensions = {}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    yield {
        "app": app,
        "client": app.test_client(),
        "registry": RunRegistry(),
    }

    RunRegistry._instance = None


def _create_report_run(registry: RunRegistry) -> dict[str, Any]:
    return registry.create_run(
        run_type="report_generate",
        entity_id="report_test",
        status="failed",
        message="failed once",
        metadata={"llm_model": "gpt-4o-mini", "simulation_id": "sim_test"},
        linked_ids={
            "report_id": "report_test",
            "simulation_id": "sim_test",
            "project_id": "proj_test",
        },
    )


class TestResumeReportBudget:
    def test_resume_builds_client_from_route_with_run_id(self, env):
        """Kern-Regression: Der Resume-Client entsteht via from_route MIT run_id,
        und ein hartes Budget beendet den Resume als stopped/termination_reason —
        nicht als failed."""
        run = _create_report_run(env["registry"])

        fake_sim_state = MagicMock()
        fake_sim_state.project_id = "proj_test"
        fake_sim_state.graph_id = "graph_test"
        fake_project = MagicMock()
        fake_project.graph_id = "graph_test"
        fake_project.simulation_requirement = "Test"

        from_route_calls: list[dict[str, Any]] = []

        def capture_from_route(route, **kwargs):
            from_route_calls.append({"route": route, **kwargs})
            return MagicMock(name="SharedLlmClient")

        fake_agent = MagicMock()
        fake_agent.generate_report.side_effect = BudgetExceededError("calls", 5, 4)

        def run_inline(self):
            self.run()

        with (
            patch("app.api.runs.SimulationManager") as mock_sm,
            patch("app.api.runs.ProjectManager") as mock_pm,
            patch("app.api.runs.StageModelRouter") as mock_router,
            patch("app.api.runs.GraphToolsService"),
            patch("app.api.runs.ReportAgent", return_value=fake_agent),
            patch.object(_threading.Thread, "start", run_inline),
        ):
            mock_sm.return_value.get_simulation.return_value = fake_sim_state
            mock_pm.get_project.return_value = fake_project
            mock_router.return_value.resolve.return_value = MagicMock(
                name="ResolvedRoute"
            )
            env["app"].extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

            with patch(
                "app.api.runs.LLMClient.from_route", side_effect=capture_from_route
            ):
                resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

        assert resp.status_code == 200, resp.get_json()

        # Client-Bindung: genau ein from_route-Aufruf, mit der run_id des Runs.
        assert len(from_route_calls) == 1
        assert from_route_calls[0].get("run_id") == run["run_id"]

        # Budgetabbruch endet als stopped + termination_reason, nicht failed.
        manifest = env["registry"].get_run(run["run_id"])
        assert manifest["status"] == "stopped", manifest
        assert manifest["termination_reason"] == "budget_calls"


class TestPrepareBudget:
    def test_prepare_job_marks_budget_abort_as_stopped(self, env):
        """Ein hartes Budget in den Prepare-Phasen endet stopped + reason —
        und der Prepare-Lauf reicht seine run_id an prepare_simulation durch."""
        from app.api.simulation_prepare import _PrepareInputs, _make_prepare_job

        run_record = env["registry"].create_run(
            run_type="simulation_prepare",
            entity_id="sim_test",
            status="pending",
            message="queued",
            linked_ids={"simulation_id": "sim_test", "project_id": "proj_test"},
        )

        manager = MagicMock()
        manager.prepare_simulation.side_effect = BudgetExceededError("tokens", 10, 5)
        manager.get_simulation.return_value = None
        task_manager = MagicMock()

        inputs = MagicMock(spec=_PrepareInputs)
        inputs.simulation_requirement = "Test"
        inputs.document_text = "Doc"
        inputs.entity_types = None
        inputs.use_llm_for_profiles = True
        inputs.parallel_profile_count = 1
        inputs.agent_language_override = None
        inputs.max_agents = None
        inputs.quota_plan = None

        job = _make_prepare_job(
            manager=manager,
            task_manager=task_manager,
            task_id="task_x",
            simulation_id="sim_test",
            inputs=inputs,
            storage=MagicMock(),
            llm_model="test-model",
            effective_llm_runtime=None,
            run_record=run_record,
        )
        job()

        # run_id wurde an die Phasen durchgereicht.
        _, call_kwargs = manager.prepare_simulation.call_args
        assert call_kwargs.get("run_id") == run_record["run_id"]

        # Reihenfolge #978/#841: fail_task lief, aber der Endzustand ist stopped.
        task_manager.fail_task.assert_called_once()
        manifest = env["registry"].get_run(run_record["run_id"])
        assert manifest["status"] == "stopped", manifest
        assert manifest["termination_reason"] == "budget_tokens"


class TestGeneratorRunBinding:
    def test_config_generator_binds_run_id(self, monkeypatch):
        """SimulationConfigGenerator baut seinen LLMClient run-gebunden."""
        captured: dict[str, Any] = {}

        class _FakeLLM:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(
            "app.services.simulation_config_generator.LLMClient", _FakeLLM
        )
        from app.services.simulation_config_generator import SimulationConfigGenerator

        SimulationConfigGenerator(
            api_key="test-key",
            base_url="http://localhost:11434/v1",
            model_name="test-model",
            run_id="run_cfg_1",
        )
        assert captured.get("run_id") == "run_cfg_1"

    def test_profile_generator_binds_run_id(self, monkeypatch):
        """OasisProfileGenerator baut den Persona-LLMClient run-gebunden."""
        captured: dict[str, Any] = {}

        class _FakeLLM:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def chat_json(self, **kwargs):
                raise RuntimeError("stop after construction")

        monkeypatch.setattr("app.llm.client.LLMClient", _FakeLLM)
        from app.services.oasis_profile_generator import OasisProfileGenerator

        gen = OasisProfileGenerator(
            api_key="test-key",
            base_url="http://localhost:11434/v1",
            model_name="test-model",
            run_id="run_pers_1",
        )
        monkeypatch.setattr(
            gen, "_build_individual_persona_prompt", lambda *a, **k: "p"
        )
        monkeypatch.setattr(gen, "_build_group_persona_prompt", lambda *a, **k: "p")
        monkeypatch.setattr(gen, "_get_system_prompt", lambda *a, **k: "s")

        try:
            gen._generate_profile_with_llm("Testperson", "person", "Summary", {}, "ctx")
        except Exception:  # noqa: BLE001 — Konstruktion vor dem ersten Call reicht
            pass

        assert captured.get("run_id") == "run_pers_1"
