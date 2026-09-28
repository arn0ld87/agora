"""Regressionstests für Issue #1669 (CodeQL ``py/path-injection``).

Deckt die Module ab, für die es keine passende bestehende Testdatei gibt:
``action_log_reader.get_all_actions``, ``SimulationRunner.get_console_log``,
``SimulationManager._get_simulation_dir`` und ``get_simulation_posts`` (API).
Jedes Modul bekommt mindestens einen Negativfall (``../``-haltige ID →
``PathTraversalError``/HTTP 400) und einen Positivfall mit einer normalen ID.

Bereits durch bestehende Testdateien abgedeckt (nicht hier dupliziert):
``interview_client`` (``tests/services/sim/test_interview_client.py``),
``interview_direct`` (``tests/services/sim/test_interview_direct.py``),
``event_bus._simulation_abs_dir`` (``tests/services/test_event_bus.py``),
``app._resolve_spa_static_file`` (``tests/test_spa_path_traversal.py``, deckt
mehr Faelle ab als der frühere ``_resolve_spa_static_target``-Testblock hier).
``branching_service.py`` braucht keinen eigenen Test: ``source_dir``/
``branch_dir`` stammen ausschließlich aus dem hier getesteten
``SimulationManager._get_simulation_dir``.
"""

from __future__ import annotations

import os

import pytest
from flask import Flask

from app.api import simulation_bp
from app.services.simulation_manager import SimulationManager
from app.services.simulation_runner import SimulationRunner
from app.services.sim.action_log_reader import get_all_actions
from app.utils.path_safety import PathTraversalError

NORMAL_SIM_ID = "sim_0123456789ab"


# ---------------------------------------------------------------------------
# action_log_reader.get_all_actions
# ---------------------------------------------------------------------------


class TestGetAllActionsPathInjection:
    def test_rejects_traversal_id(self, tmp_path) -> None:
        with pytest.raises(PathTraversalError):
            get_all_actions("../escape", str(tmp_path))

    def test_accepts_normal_id_returns_empty_when_missing(self, tmp_path) -> None:
        assert get_all_actions(NORMAL_SIM_ID, str(tmp_path)) == []


# ---------------------------------------------------------------------------
# SimulationRunner.get_console_log
# ---------------------------------------------------------------------------


class TestGetConsoleLogPathInjection:
    def test_rejects_traversal_id(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(
            "app.services.simulation_runner.read_console_log", lambda *a, **k: []
        )
        with pytest.raises(PathTraversalError):
            SimulationRunner.get_console_log("../escape")

    def test_accepts_normal_id_without_log_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
        monkeypatch.setattr(
            "app.services.simulation_runner.read_console_log", lambda *a, **k: []
        )
        result = SimulationRunner.get_console_log(NORMAL_SIM_ID)
        assert result["lines"] == []
        assert result["total_lines"] == 0


# ---------------------------------------------------------------------------
# SimulationManager._get_simulation_dir
# ---------------------------------------------------------------------------


class TestSimulationManagerGetSimulationDirPathInjection:
    def test_rejects_traversal_id(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
        manager = SimulationManager.__new__(SimulationManager)
        with pytest.raises(PathTraversalError):
            manager._get_simulation_dir("../escape")

    def test_accepts_normal_id_and_creates_dir(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
        manager = SimulationManager.__new__(SimulationManager)
        result = manager._get_simulation_dir(NORMAL_SIM_ID)
        assert result == os.path.realpath(str(tmp_path / NORMAL_SIM_ID))
        assert os.path.isdir(result)


# ---------------------------------------------------------------------------
# GET /api/simulation/<simulation_id>/posts — platform allowlist
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 1000
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


class TestSimulationPostsPlatformAllowlist:
    def test_rejects_traversal_platform(self, client) -> None:
        response = client.get(
            f"/api/simulation/{NORMAL_SIM_ID}/posts?platform=../../etc"
        )
        assert response.status_code == 400
        assert response.get_json()["success"] is False

    def test_accepts_normal_platform(self, client) -> None:
        response = client.get(f"/api/simulation/{NORMAL_SIM_ID}/posts?platform=reddit")
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
        assert body["data"]["posts"] == []
