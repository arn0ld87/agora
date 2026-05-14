"""API-Tests für /api/api-keys (Slice G2)."""
from __future__ import annotations

import re

import pytest
from flask import Flask

from app.api import api_keys_bp
from app.services.api_keys_store import get_api_keys_store


@pytest.fixture(autouse=True)
def _reset_store():
    get_api_keys_store().reset_for_tests()
    yield
    get_api_keys_store().reset_for_tests()


@pytest.fixture
def app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.register_blueprint(api_keys_bp, url_prefix="/api/api-keys")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


class TestListApiKeys:
    def test_empty_list(self, client) -> None:
        resp = client.get("/api/api-keys")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["items"] == []
        assert body["data"]["total"] == 0

    def test_list_after_create(self, client) -> None:
        client.post(
            "/api/api-keys", json={"label": "CI", "scopes": ["read"]}
        )
        resp = client.get("/api/api-keys")
        assert resp.status_code == 200
        items = resp.get_json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["label"] == "CI"
        assert items[0]["status"] == "active"
        # Klartext-Token darf in der Liste nicht auftauchen
        assert "token" not in items[0]


class TestCreateApiKey:
    def test_happy_path_returns_201_and_one_time_token(self, client) -> None:
        resp = client.post(
            "/api/api-keys",
            json={"label": "Deploy bot", "scopes": ["read", "write"]},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        token = body["data"]["token"]
        assert re.fullmatch(r"ago_[0-9a-f]{48}", token)
        key = body["data"]["key"]
        assert key["label"] == "Deploy bot"
        assert key["scopes"] == ["read", "write"]
        assert key["status"] == "active"
        # Prefix sollte die ersten 8 Hex-Zeichen aus dem Klartext spiegeln
        assert token.startswith(key["prefix"])

    def test_create_with_invalid_scope_returns_400(self, client) -> None:
        resp = client.post(
            "/api/api-keys",
            json={"label": "X", "scopes": ["root"]},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert body["code"] == "invalid_request"

    def test_create_with_empty_label_returns_400(self, client) -> None:
        resp = client.post(
            "/api/api-keys",
            json={"label": "", "scopes": ["read"]},
        )
        assert resp.status_code == 400

    def test_create_with_empty_scopes_returns_400(self, client) -> None:
        resp = client.post(
            "/api/api-keys",
            json={"label": "X", "scopes": []},
        )
        assert resp.status_code == 400

    def test_create_with_extra_field_returns_400(self, client) -> None:
        resp = client.post(
            "/api/api-keys",
            json={"label": "X", "scopes": ["read"], "secret": "x"},
        )
        assert resp.status_code == 400

    def test_tokens_are_unique_across_creates(self, client) -> None:
        first = client.post(
            "/api/api-keys", json={"label": "a", "scopes": ["read"]}
        ).get_json()["data"]["token"]
        second = client.post(
            "/api/api-keys", json={"label": "b", "scopes": ["read"]}
        ).get_json()["data"]["token"]
        assert first != second


class TestRevokeApiKey:
    def test_revoke_existing_key_returns_revoked_state(self, client) -> None:
        created = client.post(
            "/api/api-keys", json={"label": "X", "scopes": ["read"]}
        ).get_json()["data"]["key"]
        key_id = created["id"]

        resp = client.delete(f"/api/api-keys/{key_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["status"] == "revoked"
        assert body["data"]["revoked_at"] is not None

    def test_revoke_returns_404_for_unknown_id(self, client) -> None:
        resp = client.delete("/api/api-keys/not-there")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["code"] == "not_found"

    def test_revoke_is_idempotent(self, client) -> None:
        created = client.post(
            "/api/api-keys", json={"label": "X", "scopes": ["read"]}
        ).get_json()["data"]["key"]
        key_id = created["id"]
        client.delete(f"/api/api-keys/{key_id}")
        resp = client.delete(f"/api/api-keys/{key_id}")
        # Zweiter Revoke gibt nach wie vor 200 + revoked-Status zurück
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "revoked"

    def test_revoked_key_still_listed(self, client) -> None:
        created = client.post(
            "/api/api-keys", json={"label": "X", "scopes": ["read"]}
        ).get_json()["data"]["key"]
        client.delete(f"/api/api-keys/{created['id']}")
        resp = client.get("/api/api-keys")
        items = resp.get_json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "revoked"
