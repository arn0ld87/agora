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
    # @require_scope greift sobald AGORA_AUTH_TOKEN gesetzt ist. Diese Tests
    # prüfen Validierungs-/ID-Logik, nicht Auth — Open-Mode erzwingen.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
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
    """Weder lebender Worker noch persistierte Personas → 503."""
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.check_env_alive",
        staticmethod(lambda _sid: False),
    )
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.direct_interviews_available",
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


def test_interview_env_not_alive_uses_direct_path_when_personas_exist(client, monkeypatch):
    """Geschlossene Umgebung + persistierte Personas → Direktpfad statt 503."""
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.check_env_alive",
        staticmethod(lambda _sid: False),
    )
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.direct_interviews_available",
        staticmethod(lambda _sid: True),
    )
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.interview_agent",
        staticmethod(
            lambda **_kwargs: {
                "success": True,
                "agent_id": 1,
                "prompt": "Hello?",
                "mode": "direct",
                "result": {"agent_id": 1, "platform": "reddit", "response": "Passt."},
                "timestamp": "2026-08-01T12:00:00",
            }
        ),
    )
    response = client.post(
        "/api/simulation/interview",
        json={
            "simulation_id": VALID_SIM_ID,
            "agent_id": 1,
            "prompt": "Hello?",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["mode"] == "direct"
    assert payload["data"]["result"]["response"] == "Passt."


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


# --- _echo_result envelope: top-level error surfacing (#1000) ---------------
#
# _echo_result mirrors the interview result's internal ``success`` flag at the
# envelope level but always returns HTTP 200 (legacy shape). On failure, the
# frontend's response interceptor only reads top-level ``error``/``code`` —
# without mirroring those out of ``data``, a failed interview surfaced as a
# generic "Netzwerkfehler" instead of the real provider error.


def _mock_interview_backend_available(monkeypatch):
    """Shared setup: pretend the closed-environment direct path is available."""
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.check_env_alive",
        staticmethod(lambda _sid: False),
    )
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.direct_interviews_available",
        staticmethod(lambda _sid: True),
    )


def test_interview_batch_success_envelope_preserves_data(client, monkeypatch):
    """Erfolgsfall: kein top-level error/code, data bleibt vollstaendig erhalten."""
    _mock_interview_backend_available(monkeypatch)
    fake_result = {
        "success": True,
        "interviews_count": 1,
        "mode": "direct",
        "result": {
            "interviews_count": 1,
            "results": {
                "reddit_1": {
                    "agent_id": 1,
                    "platform": "reddit",
                    "response": "Klingt gut.",
                }
            },
        },
        "timestamp": "2026-08-01T12:00:00",
    }
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.interview_agents_batch",
        staticmethod(lambda **_kwargs: fake_result),
    )
    response = client.post(
        "/api/simulation/interview/batch",
        json={
            "simulation_id": VALID_SIM_ID,
            "interviews": [{"agent_id": 1, "prompt": "Hallo?"}],
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "error" not in payload
    assert "code" not in payload
    assert payload["data"] == fake_result


def test_interview_batch_ipc_error_surfaces_top_level_error(client, monkeypatch):
    """IPC-Fehlerform: result traegt bereits top-level ``error`` — wird gespiegelt."""
    _mock_interview_backend_available(monkeypatch)
    fake_result = {
        "success": False,
        "interviews_count": 2,
        "error": "IPC-Antwort ausgeblieben",
        "timestamp": "2026-08-01T12:00:00",
    }
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.interview_agents_batch",
        staticmethod(lambda **_kwargs: fake_result),
    )
    response = client.post(
        "/api/simulation/interview/batch",
        json={
            "simulation_id": VALID_SIM_ID,
            "interviews": [
                {"agent_id": 1, "prompt": "Hallo?"},
                {"agent_id": 2, "prompt": "Und du?"},
            ],
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "IPC-Antwort ausgeblieben"
    assert payload["data"] == fake_result


def test_interview_batch_direct_path_per_agent_error_surfaces_top_level(
    client, monkeypatch
):
    """Wichtigster Fall (#1000): Direktpfad legt Fehler nur pro Agent unter
    ``data.result.results[<key>].error`` ab und setzt nie ein top-level
    ``error`` — genau das liess den Provider-Fehler im Frontend als
    "Netzwerkfehler" erscheinen. Muss top-level ankommen."""
    _mock_interview_backend_available(monkeypatch)
    provider_error = "Error code: 400 - Please pass a valid API key"
    fake_result = {
        "success": False,
        "interviews_count": 1,
        "mode": "direct",
        "result": {
            "interviews_count": 1,
            "results": {
                "reddit_1": {
                    "agent_id": 1,
                    "platform": "reddit",
                    "prompt": "Hallo?",
                    "response": None,
                    "timestamp": "2026-08-01T12:00:00",
                    "simulated": True,
                    "mode": "direct",
                    "error": provider_error,
                }
            },
        },
        "timestamp": "2026-08-01T12:00:00",
    }
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.interview_agents_batch",
        staticmethod(lambda **_kwargs: fake_result),
    )
    response = client.post(
        "/api/simulation/interview/batch",
        json={
            "simulation_id": VALID_SIM_ID,
            "interviews": [{"agent_id": 1, "prompt": "Hallo?"}],
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == provider_error
    assert "code" not in payload
    assert payload["data"] == fake_result


def test_interview_batch_code_field_is_mirrored_when_present(client, monkeypatch):
    """``code`` ist Teil des Vertrags (``InterviewEnvelope``), auch wenn kein
    aktueller ``SimulationRunner``-Pfad ihn setzt — die Mirroring-Logik selbst
    muss trotzdem am Endpunkt strukturgleich zum Ist-Verhalten bleiben."""
    _mock_interview_backend_available(monkeypatch)
    fake_result = {
        "success": False,
        "error": "Rate limit exceeded",
        "code": "rate_limited",
        "timestamp": "2026-08-01T12:00:00",
    }
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.interview_agents_batch",
        staticmethod(lambda **_kwargs: fake_result),
    )
    response = client.post(
        "/api/simulation/interview/batch",
        json={
            "simulation_id": VALID_SIM_ID,
            "interviews": [{"agent_id": 1, "prompt": "Hallo?"}],
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Rate limit exceeded"
    assert payload["code"] == "rate_limited"
    assert payload["data"] == fake_result


def test_interview_single_success_envelope_preserves_data(client, monkeypatch):
    """Der ``/interview``-Einzelendpunkt teilt sich ``_echo_result`` mit
    ``/interview/batch`` — dieselbe Envelope-Form muss auch hier gelten."""
    _mock_interview_backend_available(monkeypatch)
    fake_result = {
        "success": True,
        "agent_id": 1,
        "mode": "direct",
        "result": {"agent_id": 1, "platform": "reddit", "response": "Passt."},
        "timestamp": "2026-08-01T12:00:00",
    }
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.interview_agent",
        staticmethod(lambda **_kwargs: fake_result),
    )
    response = client.post(
        "/api/simulation/interview",
        json={"simulation_id": VALID_SIM_ID, "agent_id": 1, "prompt": "Hallo?"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "error" not in payload
    assert "code" not in payload
    assert payload["data"] == fake_result


def test_interview_all_success_envelope_preserves_data(client, monkeypatch):
    """``/interview/all`` teilt sich ebenfalls ``_echo_result`` — vierter der
    vier betroffenen Endpunkte aus #1005."""
    _mock_interview_backend_available(monkeypatch)
    fake_result = {
        "success": True,
        "mode": "direct",
        "result": {"results": {"reddit_1": {"agent_id": 1, "response": "Klar."}}},
        "timestamp": "2026-08-01T12:00:00",
    }
    monkeypatch.setattr(
        "app.api.simulation_interviews.SimulationRunner.interview_all_agents",
        staticmethod(lambda **_kwargs: fake_result),
    )
    response = client.post(
        "/api/simulation/interview/all",
        json={"simulation_id": VALID_SIM_ID, "prompt": "Wie geht's?"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "error" not in payload
    assert "code" not in payload
    assert payload["data"] == fake_result
