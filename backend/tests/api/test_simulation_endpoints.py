"""Endpoint-Tests für ``app.api.simulation_*`` — verifiziert die ApiErrorCode-Migration.

Fokus: jeder migrierte Error-Pfad liefert Envelope mit ``code``. Die alte
Suite ``tests/test_simulation_api_routes.py`` testet weiter exakte Strings;
diese Suite testet die ``code``-Verträge zusätzlich, sodass Frontend-Mapper
sich auf semantische Codes verlassen können.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp


VALID_SIM_ID = "sim_0123456789ab"
VALID_GRAPH_ID = "abcdef0123456789abcdef0123456789"


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    storage = MagicMock(name="Neo4jStorage")
    app.extensions = {"neo4j_storage": storage}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


# --- INVALID_ID --------------------------------------------------------------


def test_get_simulation_invalid_id_returns_invalid_id(client):
    response = client.get("/api/simulation/not-a-sim")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_pause_invalid_id_returns_invalid_id(client):
    response = client.post("/api/simulation/not-a-sim/pause")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_resume_invalid_id_returns_invalid_id(client):
    response = client.post("/api/simulation/not-a-sim/resume")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_run_status_invalid_id_returns_invalid_id(client):
    response = client.get("/api/simulation/not-a-sim/run-status")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_get_entity_invalid_graph_id_returns_invalid_id(client):
    response = client.get("/api/simulation/entities/not-a-graph")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_metrics_invalid_id_returns_invalid_id(client):
    response = client.get("/api/simulation/not-a-sim/metrics")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_metrics_export_invalid_id_returns_invalid_id(client):
    response = client.get("/api/simulation/not-a-sim/metrics/export")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


def test_stream_invalid_id_returns_invalid_id(client):
    response = client.get("/api/simulation/not-a-sim/stream")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_id"


# --- VALIDATION_FAILED -------------------------------------------------------


def test_start_missing_simulation_id_returns_validation_failed(client):
    response = client.post("/api/simulation/start", json={})
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_start_invalid_platform_returns_validation_failed(client):
    response = client.post(
        "/api/simulation/start",
        json={"simulation_id": VALID_SIM_ID, "platform": "myspace"},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_start_invalid_max_rounds_returns_validation_failed(client):
    response = client.post(
        "/api/simulation/start",
        json={"simulation_id": VALID_SIM_ID, "max_rounds": -3},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_create_branch_missing_branch_name_returns_validation_failed(client):
    response = client.post(
        f"/api/simulation/{VALID_SIM_ID}/branch", json={}
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_persona_library_missing_payload_returns_validation_failed(client):
    response = client.post("/api/simulation/persona-library", json={})
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_metrics_invalid_window_returns_validation_failed(client):
    response = client.get(
        f"/api/simulation/{VALID_SIM_ID}/metrics?window_size_rounds=abc"
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_metrics_invalid_platform_returns_validation_failed(client):
    response = client.get(
        f"/api/simulation/{VALID_SIM_ID}/metrics?platform=myspace"
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_metrics_export_invalid_view_returns_validation_failed(client):
    response = client.get(
        f"/api/simulation/{VALID_SIM_ID}/metrics/export?view=galaxy"
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_interview_missing_agent_id_returns_validation_failed(client):
    response = client.post(
        "/api/simulation/interview",
        json={"simulation_id": VALID_SIM_ID},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


def test_interview_batch_missing_interviews_returns_validation_failed(client):
    response = client.post(
        "/api/simulation/interview/batch",
        json={"simulation_id": VALID_SIM_ID},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "validation_failed"


# --- UNSUPPORTED_FORMAT ------------------------------------------------------


def test_metrics_export_invalid_format_returns_unsupported_format(client):
    response = client.get(
        f"/api/simulation/{VALID_SIM_ID}/metrics/export?format=json"
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "unsupported_format"


# --- NOT_FOUND ---------------------------------------------------------------


def test_get_simulation_not_found_returns_not_found(client, monkeypatch):
    fake_manager = MagicMock(get_simulation=MagicMock(return_value=None))
    monkeypatch.setattr(
        "app.api.simulation_lifecycle.SimulationManager",
        lambda: fake_manager,
    )
    response = client.get(f"/api/simulation/{VALID_SIM_ID}")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["code"] == "not_found"
    assert VALID_SIM_ID in payload["error"]


def test_persona_template_delete_not_found_returns_not_found(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.simulation_profiles.PersonaLibrary",
        lambda: MagicMock(delete_template=MagicMock(return_value=False)),
    )
    response = client.delete("/api/simulation/persona-library/some-template-id")
    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


# --- SERVICE_UNAVAILABLE -----------------------------------------------------


def test_interview_env_not_alive_returns_service_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.check_env_alive",
        staticmethod(lambda _sid: False),
    )
    response = client.post(
        "/api/simulation/interview",
        json={
            "simulation_id": VALID_SIM_ID,
            "agent_id": 1,
            "prompt": "Hello?",
        },
    )
    assert response.status_code == 503
    assert response.get_json()["code"] == "service_unavailable"


# --- PERSONA_REVIEW_REQUIRED -------------------------------------------------


def test_start_persona_review_blocks_returns_persona_review_required(client, monkeypatch):
    from app.services.simulation_manager import SimulationStatus

    monkeypatch.setattr(
        "app.api.simulation_run.Config.PERSONA_REVIEW_ENABLED",
        True,
        raising=False,
    )
    fake_state = MagicMock()
    fake_state.status = SimulationStatus.READY
    fake_manager = MagicMock(get_simulation=MagicMock(return_value=fake_state))
    monkeypatch.setattr(
        "app.api.simulation_run.SimulationManager",
        lambda: fake_manager,
    )
    fake_review = {"allowed": False, "missing": [{"username": "u1"}]}
    fake_service = MagicMock(evaluate_start_gate=MagicMock(return_value=fake_review))
    monkeypatch.setattr(
        "app.api.simulation_run.PersonaReviewService",
        lambda _store: fake_service,
    )
    monkeypatch.setattr(
        "app.api.simulation_run.get_artifact_store",
        lambda: MagicMock(name="ArtifactStore"),
    )
    response = client.post(
        "/api/simulation/start",
        json={"simulation_id": VALID_SIM_ID, "platform": "parallel"},
    )
    assert response.status_code == 409
    payload = response.get_json()
    assert payload["code"] == "persona_review_required"
    assert payload["review"] == fake_review
