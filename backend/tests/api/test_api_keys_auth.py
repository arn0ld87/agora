import pytest
from unittest.mock import patch
from flask import Flask
from app.utils.auth import token_required
from app.services.api_keys_store import get_api_keys_store
from app.utils.api_responses import install_api_error_handlers

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    install_api_error_handlers(app)

    @app.route("/test")
    @token_required
    def test_view():
        return {"success": True}

    return app

@pytest.fixture
def store():
    s = get_api_keys_store()
    s.reset_for_tests()
    return s

def test_auth_with_api_key(app, store):
    resp = store.create("Key", ["read"])
    token = resp.token

    with app.test_client() as client:
        # 1. No token -> 401 if AGORA_AUTH_TOKEN is set
        with patch("app.utils.auth._expected_token", return_value="master"):
            assert client.get("/test").status_code == 401

            # 2. Master token -> 200
            assert client.get("/test", headers={"X-Agora-Token": "master"}).status_code == 200

            # 3. API Key token -> 200
            assert client.get("/test", headers={"X-Agora-Token": token}).status_code == 200
            assert client.get("/test", headers={"Authorization": f"Bearer {token}"}).status_code == 200

            # 4. Revoked API Key -> 401
            store.revoke(resp.key.id)
            assert client.get("/test", headers={"X-Agora-Token": token}).status_code == 401

def test_auth_open_mode(app):
    with app.test_client() as client:
        # No AGORA_AUTH_TOKEN -> 200
        with patch("app.utils.auth._expected_token", return_value=""):
            assert client.get("/test").status_code == 200
