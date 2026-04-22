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


def test_list_simulations_route_is_registered():
    app = _build_test_app()
    client = app.test_client()

    response = client.get("/api/simulation/list")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "data" in payload
    assert "count" in payload
