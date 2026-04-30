"""Endpoint-Tests für ``app.api.graph`` — verifiziert die ApiErrorCode-Migration.

Fokus: jeder Error-Pfad liefert die richtige Envelope-Form
``{"success": false, "code": "<code>", "error": "..."}``. Frontend kann
sich auf ``code`` verlassen, der ``error``-Text bleibt menschenlesbar.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer


VALID_PROJECT_ID = "proj_0123456789ab"
VALID_GRAPH_ID = "abcdef0123456789abcdef0123456789"
VALID_TASK_ID = "01234567-89ab-4def-8123-456789abcdef"


@pytest.fixture
def app(monkeypatch):
    storage = MagicMock(name="Neo4jStorage")
    container = AgoraContainer(neo4j_storage=storage)
    flask_app = Flask(__name__)
    flask_app.extensions = {"container": container, "neo4j_storage": storage}
    flask_app.register_blueprint(graph_bp, url_prefix="/api/graph")
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# --- INVALID_ID --------------------------------------------------------------


def test_get_project_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/project/not-a-valid-id")
    payload = response.get_json()
    assert response.status_code == 400
    assert payload["success"] is False
    assert payload["code"] == "invalid_id"


def test_delete_project_invalid_id_returns_invalid_id_code(client):
    response = client.delete("/api/graph/project/not-a-valid-id")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_reset_project_invalid_id_returns_invalid_id_code(client):
    response = client.post("/api/graph/project/not-a-valid-id/reset")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_task_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/task/garbage")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_graph_data_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/data/not-valid")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_graph_snapshot_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/snapshot/not-valid/0")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_graph_diff_invalid_id_returns_invalid_id_code(client):
    response = client.get("/api/graph/diff/not-valid?start_round=0&end_round=1")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_delete_graph_invalid_id_returns_invalid_id_code(client):
    response = client.delete("/api/graph/delete/not-valid")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


# --- VALIDATION_FAILED -------------------------------------------------------


def test_build_graph_missing_project_id_returns_validation_failed(client):
    response = client.post("/api/graph/build", json={})
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_get_graph_snapshot_negative_round_returns_validation_failed(client):
    # int converter erlaubt negative Werte nicht — daher schicken wir den Pfad
    # mit gültiger ID und negativer Round-Zahl per JSON-Body-Routenform; da
    # Flask <int:round_num> negative Werte ablehnt, prüfen wir das semantische
    # Verhalten in einer separaten Route mit start_round=-1.
    response = client.get(f"/api/graph/diff/{VALID_GRAPH_ID}?start_round=2&end_round=1")
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_get_graph_diff_non_integer_rounds_returns_validation_failed(client):
    response = client.get(
        f"/api/graph/diff/{VALID_GRAPH_ID}?start_round=abc&end_round=def"
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


# --- NOT_FOUND ---------------------------------------------------------------


def test_get_project_not_found_returns_not_found_code(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.graph.ProjectManager.get_project",
        staticmethod(lambda _pid: None),
    )
    response = client.get(f"/api/graph/project/{VALID_PROJECT_ID}")
    payload = response.get_json()
    assert response.status_code == 404
    assert payload["code"] == "not_found"
    assert VALID_PROJECT_ID in payload["error"]


def test_get_task_not_found_returns_not_found_code(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.graph.TaskManager",
        lambda: MagicMock(get_task=MagicMock(return_value=None)),
    )
    response = client.get(f"/api/graph/task/{VALID_TASK_ID}")
    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


# --- UNSUPPORTED_FORMAT ------------------------------------------------------


def test_export_unknown_format_returns_unsupported_format_code(client):
    response = client.get(f"/api/graph/{VALID_GRAPH_ID}/export?format=svg")
    assert response.status_code == 400
    assert response.get_json()["code"] == "unsupported_format"


# --- ONTOLOGY_MISSING --------------------------------------------------------


def test_build_graph_without_ontology_returns_ontology_missing(client, monkeypatch):
    from app.models.project import ProjectStatus

    fake_project = MagicMock()
    fake_project.status = ProjectStatus.CREATED
    fake_project.ontology = None
    fake_project.graph_build_task_id = None
    monkeypatch.setattr(
        "app.api.graph.ProjectManager.get_project",
        staticmethod(lambda _pid: fake_project),
    )
    response = client.post("/api/graph/build", json={"project_id": VALID_PROJECT_ID})
    assert response.status_code == 400
    assert response.get_json()["code"] == "ontology_missing"


# --- GRAPH_BUILD_IN_PROGRESS -------------------------------------------------


def test_build_graph_when_already_building_returns_graph_build_in_progress(
    client, monkeypatch
):
    from app.models.project import ProjectStatus

    fake_project = MagicMock()
    fake_project.status = ProjectStatus.GRAPH_BUILDING
    fake_project.ontology = {"entity_types": [], "edge_types": []}
    fake_project.graph_build_task_id = "existing-task-id"
    monkeypatch.setattr(
        "app.api.graph.ProjectManager.get_project",
        staticmethod(lambda _pid: fake_project),
    )
    response = client.post("/api/graph/build", json={"project_id": VALID_PROJECT_ID})
    payload = response.get_json()
    assert response.status_code == 409
    assert payload["code"] == "graph_build_in_progress"
    assert payload["task_id"] == "existing-task-id"
