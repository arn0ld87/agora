import os

import pytest
from flask import Flask

from app.api import simulation_bp
from app.api.simulation_lifecycle import _detect_default_provider
from app.services.artifact_store import InMemoryArtifactStore
from app.utils.rate_limit import llm_trigger_rate_limiter


@pytest.fixture(autouse=True)
def _clear_auth_token():
    # @require_scope greift sobald AGORA_AUTH_TOKEN gesetzt ist. Tests in
    # dieser Datei prüfen Validierungs-/Routing-Logik, nicht Auth — Open-Mode.
    prev = os.environ.pop("AGORA_AUTH_TOKEN", None)
    try:
        yield
    finally:
        if prev is not None:
            os.environ["AGORA_AUTH_TOKEN"] = prev


def _reset_llm_trigger_limiter():
    llm_trigger_rate_limiter.reset_for_tests()


def _build_test_app(*, artifact_store=None):
    _reset_llm_trigger_limiter()
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 20
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.extensions = {}
    if artifact_store is not None:
        app.extensions["artifact_store"] = artifact_store
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
    assert "default_provider" in payload["data"]


def test_detect_default_provider_openai(monkeypatch):
    monkeypatch.setattr('app.api.simulation_lifecycle.Config.LLM_BASE_URL', 'https://api.openai.com/v1')
    monkeypatch.setattr('app.api.simulation_lifecycle.Config.LLM_MODEL_NAME', 'gpt-5.4-mini')

    assert _detect_default_provider() == 'openai'



def test_detect_default_provider_ollama_cloud(monkeypatch):
    monkeypatch.setattr('app.api.simulation_lifecycle.Config.LLM_BASE_URL', 'https://example.test/v1')
    monkeypatch.setattr('app.api.simulation_lifecycle.Config.LLM_MODEL_NAME', 'qwen3-coder-next:cloud')

    assert _detect_default_provider() == 'cloud'



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


def test_prepare_simulation_rate_limits_llm_trigger():
    app = _build_test_app()
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 2
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    client = app.test_client()

    for _ in range(2):
        response = client.post("/api/simulation/prepare", json={})
        assert response.status_code == 400

    response = client.post("/api/simulation/prepare", json={})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    payload = response.get_json()
    assert payload["code"] == "rate_limited"
    assert payload["retry_after_seconds"] == 60


def test_prepare_status_requires_identifier():
    app = _build_test_app()
    client = app.test_client()

    response = client.post("/api/simulation/prepare/status", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Please provide task_id or simulation_id"
    assert payload["code"] == "validation_failed"


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
    assert payload["error"] == "simulation_days must be between 1 and 365"
    assert payload["code"] == "validation_failed"


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


def _seed_ready_simulation(store, sim_id, profiles):
    store.write_json(sim_id, "state", {
        "project_id": "proj_abcdef012345",
        "graph_id": "deadbeefdeadbeefdeadbeefdeadbeef",
        "status": "ready",
    })
    store.write_json(sim_id, "reddit_profiles", profiles)


def test_start_route_blocks_when_personas_pending(monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "PERSONA_REVIEW_ENABLED", True)
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    _seed_ready_simulation(store, sim_id, [
        {"username": "alice", "review_status": "approved"},
        {"username": "bob"},  # default pending
    ])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    response = client.post(
        "/api/simulation/start",
        json={"simulation_id": sim_id},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "persona_review_required"
    assert payload["review"]["pending"] == ["bob"]


def test_start_route_skips_gate_when_flag_disabled(monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "PERSONA_REVIEW_ENABLED", False)
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    _seed_ready_simulation(store, sim_id, [{"username": "bob"}])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    response = client.post(
        "/api/simulation/start",
        json={"simulation_id": sim_id},
    )

    # The gate is silent; later validation/runtime layers may still fail in
    # this test harness, but the request must not be rejected with a
    # persona-review 409.
    assert response.status_code != 409
    if response.is_json:
        payload = response.get_json()
        assert payload.get("code") != "persona_review_required"


def test_persona_quality_route_returns_summary_and_issues():
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    store.write_json(sim_id, "reddit_profiles", [
        {"username": "alice", "bio": "x", "persona": "y", "profession": "ops",
         "mbti": "INTJ", "source_entity_uuid": "u-1"},
        {"username": "alice", "bio": "x", "persona": "y", "profession": "ops",
         "mbti": "INTJ", "source_entity_uuid": "u-2"},
    ])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    response = client.get(f"/api/simulation/{sim_id}/profiles/quality")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["summary"]["total"] == 2
    codes = {issue["code"] for entry in payload["personas"] for issue in entry["issues"]}
    assert "duplicate_username" in codes
    assert payload["review_enabled"] is False


def test_persona_quality_route_validates_simulation_id():
    app = _build_test_app(artifact_store=InMemoryArtifactStore())
    client = app.test_client()

    response = client.get("/api/simulation/not-a-sim/profiles/quality")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid simulation_id format"


def test_persona_review_endpoints_round_trip():
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    store.write_json(sim_id, "reddit_profiles", [
        {"username": "alice", "is_manual": False},
        {"username": "bob", "is_manual": True},
    ])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    approve = client.post(f"/api/simulation/{sim_id}/profiles/alice/approve")
    assert approve.status_code == 200
    assert approve.get_json()["data"]["review_status"] == "approved"

    edit = client.patch(
        f"/api/simulation/{sim_id}/profiles/alice",
        json={"bio": "tightened"},
    )
    assert edit.status_code == 200
    payload = edit.get_json()["data"]
    assert payload["profile"]["bio"] == "tightened"
    assert payload["review_status"] == "pending"

    reject = client.post(
        f"/api/simulation/{sim_id}/profiles/alice/reject",
        json={"reason": "thin bio"},
    )
    assert reject.status_code == 200
    assert reject.get_json()["data"]["profile"]["review_notes"] == "thin bio"

    missing = client.post(f"/api/simulation/{sim_id}/profiles/ghost/approve")
    assert missing.status_code == 404


def test_persona_review_endpoint_validates_simulation_id():
    app = _build_test_app(artifact_store=InMemoryArtifactStore())
    client = app.test_client()

    response = client.post("/api/simulation/not-a-sim/profiles/alice/approve")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid simulation_id format"


def test_persona_edit_rejects_payload_with_no_editable_fields():
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    store.write_json(sim_id, "reddit_profiles", [{"username": "alice"}])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    response = client.patch(
        f"/api/simulation/{sim_id}/profiles/alice",
        json={"user_id": 7},
    )

    assert response.status_code == 400


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


def test_generate_profiles_rate_limits_llm_trigger():
    app = _build_test_app()
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 2
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    client = app.test_client()

    for _ in range(2):
        response = client.post("/api/simulation/generate-profiles", json={})
        assert response.status_code == 400

    response = client.post("/api/simulation/generate-profiles", json={})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    payload = response.get_json()
    assert payload["code"] == "rate_limited"
    assert payload["retry_after_seconds"] == 60


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
    assert payload["error"] == "Please provide prompt (interview question)"
    assert payload["code"] == "validation_failed"


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


# ---------------------------------------------------------------------------
# Sub-Slice 31: regenerate endpoint
# ---------------------------------------------------------------------------

def test_regenerate_returns_regenerating_status():
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    store.write_json(sim_id, "reddit_profiles", [{"username": "alice"}])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    response = client.post(f"/api/simulation/{sim_id}/profiles/alice/regenerate")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["review_status"] == "regenerating"
    assert payload["data"]["username"] == "alice"


def test_regenerate_with_notes_sets_review_notes():
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    store.write_json(sim_id, "reddit_profiles", [{"username": "alice"}])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    response = client.post(
        f"/api/simulation/{sim_id}/profiles/alice/regenerate",
        json={"notes": "profile too generic"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["profile"]["review_notes"] == "profile too generic"


def test_regenerate_unknown_username_returns_404():
    sim_id = "sim_abcdef012345"
    store = InMemoryArtifactStore()
    store.write_json(sim_id, "reddit_profiles", [{"username": "alice"}])
    app = _build_test_app(artifact_store=store)
    client = app.test_client()

    response = client.post(f"/api/simulation/{sim_id}/profiles/ghost/regenerate")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False


def test_regenerate_invalid_simulation_id_returns_400():
    app = _build_test_app(artifact_store=InMemoryArtifactStore())
    client = app.test_client()

    response = client.post("/api/simulation/not-a-sim/profiles/alice/regenerate")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid simulation_id format"
