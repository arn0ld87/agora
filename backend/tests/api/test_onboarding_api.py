"""API-Tests für /api/onboarding (Onboarding Slice 2).

Blueprint-/Client-Konventionen gespiegelt von
``tests/api/test_api_keys_api.py``. ``get_settings`` wird gezielt gepatcht,
um die Requirements (chat_model_configured/embedding_configured) hermetisch
und unabhängig von ADR-0003-Pflichtfeldern (SECRET_KEY etc.) zu steuern.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from app.api import onboarding_bp
from app.contracts.user_profile_contract import (
    ONBOARDING_STEP_ORDER,
    UserProfileUpdateRequest,
)
from app.services.onboarding_state_store import reset_onboarding_state_store_for_tests
from app.services.user_profile_store import (
    get_user_profile_store,
    reset_user_profile_store_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    reset_user_profile_store_for_tests()
    reset_onboarding_state_store_for_tests()
    yield
    reset_user_profile_store_for_tests()
    reset_onboarding_state_store_for_tests()


@pytest.fixture(autouse=True)
def _configured_settings(monkeypatch):
    """Chat-Modell + Embeddings gelten standardmäßig als konfiguriert.

    Tests, die die Requirements gezielt scheitern lassen wollen, patchen
    das Fixture-Ergebnis erneut.
    """
    monkeypatch.setattr(
        "app.services.onboarding_state_store.get_settings",
        lambda: SimpleNamespace(
            llm_model_name="test-chat-model",
            embedding_model="test-embed-model",
            vector_dim=768,
        ),
    )


@pytest.fixture
def app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.register_blueprint(onboarding_bp, url_prefix="/api/onboarding")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


def _create_profile() -> None:
    get_user_profile_store().update(
        UserProfileUpdateRequest(display_name="Alex Schneider")
    )


class TestGetOnboarding:
    def test_not_started_by_default(self, client) -> None:
        resp = client.get("/api/onboarding")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert data["state"]["status"] == "not_started"
        assert data["requirements"]["chat_model_configured"] is True
        assert data["requirements"]["embedding_configured"] is True
        assert data["requirements"]["profile_valid"] is False
        assert data["onboarding_required"] is True

    def test_onboarding_required_true_while_in_progress(self, client) -> None:
        client.put("/api/onboarding/step", json={"step": "welcome"})
        resp = client.get("/api/onboarding")
        data = resp.get_json()["data"]
        assert data["state"]["status"] == "in_progress"
        assert data["onboarding_required"] is True


class TestPutStep:
    def test_completing_step_advances_current_step(self, client) -> None:
        resp = client.put("/api/onboarding/step", json={"step": "welcome"})
        assert resp.status_code == 200
        state = resp.get_json()["data"]["state"]
        assert "welcome" in state["completed_steps"]
        assert state["current_step"] == ONBOARDING_STEP_ORDER[1]

    def test_repeating_step_is_idempotent(self, client) -> None:
        client.put("/api/onboarding/step", json={"step": "welcome"})
        resp = client.put("/api/onboarding/step", json={"step": "welcome"})
        assert resp.status_code == 200
        state = resp.get_json()["data"]["state"]
        assert state["completed_steps"].count("welcome") == 1


class TestCompleteOnboarding:
    def test_incomplete_returns_409_with_missing_list(self, client) -> None:
        resp = client.post("/api/onboarding/complete")
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["success"] is False
        assert body["code"] == "onboarding_incomplete"
        assert "profile_valid" in body["missing"]

    def test_happy_path_returns_200_completed(self, client) -> None:
        _create_profile()
        for step in ("profile", "chat_model", "embeddings"):
            client.put("/api/onboarding/step", json={"step": step})

        resp = client.post("/api/onboarding/complete")
        assert resp.status_code == 200
        state = resp.get_json()["data"]["state"]
        assert state["status"] == "completed"


class TestDismissOnboarding:
    def test_dismiss_sets_status_and_clears_onboarding_required(self, client) -> None:
        resp = client.post("/api/onboarding/dismiss")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["state"]["status"] == "dismissed"

        follow_up = client.get("/api/onboarding")
        assert follow_up.get_json()["data"]["onboarding_required"] is False


class TestReopenOnboarding:
    def test_reopen_resumes_with_completed_steps_intact(self, client) -> None:
        client.put("/api/onboarding/step", json={"step": "welcome"})
        client.post("/api/onboarding/dismiss")

        resp = client.post("/api/onboarding/reopen")
        assert resp.status_code == 200
        state = resp.get_json()["data"]["state"]
        assert state["status"] == "in_progress"
        assert "welcome" in state["completed_steps"]
