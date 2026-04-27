from flask import Flask

from app.api import simulation_bp


def _build_test_app():
    app = Flask(__name__)
    app.extensions = {}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app


def test_available_models_route_is_registered():
    app = _build_test_app()
    client = app.test_client()

    response = client.get("/api/simulation/available-models")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "current_default" in payload["data"]


def test_available_models_surfaces_startup_neo4j_error():
    app = _build_test_app()
    app.extensions["neo4j_storage_error"] = "AuthError: unauthorized"
    client = app.test_client()

    response = client.get("/api/simulation/available-models")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["neo4j_reachable"] is False
    assert payload["data"]["neo4j_error"] == "AuthError: unauthorized"


def test_entity_routes_keep_validation_guard():
    app = _build_test_app()
    client = app.test_client()

    response = client.get("/api/simulation/entities/not-a-graph-id")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid graph_id format"


def test_create_simulation_requires_project_id():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/create", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide project_id"


def test_prepare_simulation_requires_simulation_id():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/prepare", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide simulation_id"


def test_prepare_status_requires_identifier():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/prepare/status", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide task_id Or simulation_id"


def test_create_branch_requires_branch_name():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/sim_abcdef123456/branch", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "branch_name is required"


def test_config_route_keeps_validation_guard():
    app = _build_test_app()
    client = app.test_client()

    response = client.get("/api/simulation/not-a-sim-id/config")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid simulation_id format"


def test_start_simulation_requires_simulation_id():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/start", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide simulation_id"


def test_start_simulation_validates_simulation_days():
    app = _build_test_app()
    client = app.test_client()

    response = client.post(
        "/api/simulation/start",
        json={"simulation_id": "sim_abcdef123456", "simulation_days": 0},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "simulation_days Must be between 1 and 365"


def test_persona_library_round_trip(monkeypatch, tmp_path):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    app = _build_test_app()
    client = app.test_client()

    create_response = client.post(
        "/api/simulation/persona-library",
        json={
            "username": "debug_sre",
            "name": "Debug SRE",
            "bio": "SRE with a bias toward reproducible incidents.",
            "persona": "Pragmatic infrastructure operator.",
        },
    )

    assert create_response.status_code == 200
    created = create_response.get_json()
    assert created["success"] is True
    template_id = created["data"]["template"]["template_id"]

    list_response = client.get("/api/simulation/persona-library")
    listed = list_response.get_json()
    assert listed["success"] is True
    assert listed["data"]["count"] == 1
    assert listed["data"]["templates"][0]["username"] == "debug_sre"

    delete_response = client.delete(f"/api/simulation/persona-library/{template_id}")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["success"] is True


def test_pause_route_keeps_validation_guard():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/not-a-sim-id/pause")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid simulation_id format"


def test_env_status_requires_simulation_id():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/env-status", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide simulation_id"


def test_generate_profiles_requires_graph_id():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/generate-profiles", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide graph_id"


def test_interview_requires_prompt():
    app = _build_test_app()
    client = app.test_client()

    response = client.post(
        "/api/simulation/interview",
        json={"simulation_id": "sim_abcdef123456", "agent_id": 1},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide prompt（Interview question）"


def test_posts_route_keeps_validation_guard():
    app = _build_test_app()
    client = app.test_client()

    response = client.get("/api/simulation/not-a-sim-id/posts")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid simulation_id format"


def test_list_simulations_route_is_registered():
    app = _build_test_app()
    client = app.test_client()

    response = client.get("/api/simulation/list")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "data" in payload
    assert "count" in payload
