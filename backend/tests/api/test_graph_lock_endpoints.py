"""Sperre an den bestehenden Schreib-Endpunkten (Issue #1808, ADR-0022 §6).

Löschen und Zurücksetzen antworten für einen Graphen, den eine Simulation
verwendet, mit HTTP 409 und dem Code ``graph_locked``; ein freier Graph wird
wie bisher gelöscht bzw. zurückgesetzt.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer
from app.contracts.simulation_record_contract import SimulationRecord

GRAPH_ID = "abcdef0123456789abcdef0123456789"
PROJECT_ID = "proj_0123456789ab"


class _Repo:
    def __init__(self, *records: SimulationRecord) -> None:
        self._records = list(records)

    def list(self, project_id=None):
        return list(self._records)


@pytest.fixture
def storage():
    return MagicMock(name="Neo4jStorage")


@pytest.fixture
def client(monkeypatch, storage):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {
        "container": AgoraContainer(neo4j_storage=storage),
        "neo4j_storage": storage,
    }
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    return app.test_client()


def _use(monkeypatch, *records: SimulationRecord, projects=()):
    monkeypatch.setattr("app.services.graph_lock._default_repository", lambda: _Repo(*records))
    monkeypatch.setattr(
        "app.services.graph_lock._default_project_lister",
        lambda: [SimpleNamespace(project_id=p, graph_id=g) for p, g in projects],
    )


def _sim(**kw):
    return SimulationRecord(simulation_id="sim_0123456789ab", status="completed", **kw)


def test_delete_graph_used_by_simulation_returns_409_with_users(client, monkeypatch, storage):
    _use(monkeypatch, _sim(graph_id=GRAPH_ID))

    response = client.delete(f"/api/graph/delete/{GRAPH_ID}")

    assert response.status_code == 409
    body = response.get_json()
    assert body["success"] is False
    assert body["code"] == "graph_locked"
    assert [u["simulation_id"] for u in body["used_by"]] == ["sim_0123456789ab"]
    storage.delete_graph.assert_not_called()


def test_delete_graph_of_project_used_by_simulation_returns_409(client, monkeypatch, storage):
    _use(monkeypatch, _sim(project_id=PROJECT_ID), projects=[(PROJECT_ID, GRAPH_ID)])

    response = client.delete(f"/api/graph/delete/{GRAPH_ID}")

    assert response.status_code == 409
    assert response.get_json()["code"] == "graph_locked"
    storage.delete_graph.assert_not_called()


def test_delete_free_graph_still_deletes(client, monkeypatch, storage):
    _use(monkeypatch)

    response = client.delete(f"/api/graph/delete/{GRAPH_ID}")

    assert response.status_code == 200
    storage.delete_graph.assert_called_once_with(GRAPH_ID)


def test_reset_project_with_simulation_returns_409_and_keeps_project(client, monkeypatch):
    _use(monkeypatch, _sim(project_id=PROJECT_ID))
    project = SimpleNamespace(project_id=PROJECT_ID, graph_id=GRAPH_ID)

    with (
        patch("app.api.graph.ProjectManager.get_project", return_value=project),
        patch("app.api.graph.ProjectManager.save_project") as save,
    ):
        response = client.post(f"/api/graph/project/{PROJECT_ID}/reset")

    assert response.status_code == 409
    assert response.get_json()["code"] == "graph_locked"
    save.assert_not_called()
    assert project.graph_id == GRAPH_ID


def test_delete_project_with_simulation_returns_409_and_keeps_project(client, monkeypatch):
    _use(monkeypatch, _sim(project_id=PROJECT_ID))
    project = SimpleNamespace(project_id=PROJECT_ID, graph_id=None)

    with (
        patch("app.api.graph.ProjectManager.get_project", return_value=project),
        patch("app.api.graph.ProjectManager.delete_project") as delete,
    ):
        response = client.delete(f"/api/graph/project/{PROJECT_ID}")

    assert response.status_code == 409
    assert response.get_json()["code"] == "graph_locked"
    delete.assert_not_called()


def test_delete_free_project_still_deletes(client, monkeypatch):
    _use(monkeypatch)
    project = SimpleNamespace(project_id=PROJECT_ID, graph_id=GRAPH_ID)

    with (
        patch("app.api.graph.ProjectManager.get_project", return_value=project),
        patch("app.api.graph.ProjectManager.delete_project", return_value=True) as delete,
    ):
        response = client.delete(f"/api/graph/project/{PROJECT_ID}")

    assert response.status_code == 200
    delete.assert_called_once_with(PROJECT_ID)
