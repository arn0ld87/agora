"""Tests for token auth response contracts."""

from flask import Blueprint, Flask

from app.utils.api_responses import json_success
from app.utils.auth import install_blueprint_guard, token_required


def _build_guarded_app():
    app = Flask(__name__)
    bp = Blueprint("guarded", __name__)

    @bp.route("/ping")
    def ping():
        return json_success({"ok": True})

    install_blueprint_guard(bp)
    app.register_blueprint(bp, url_prefix="/api/guarded")
    return app


def test_token_required_open_mode_allows_request(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)

    @token_required
    def view():
        return json_success({"ok": True})

    with app.test_request_context("/api/example"):
        response, status = view()

    assert status == 200
    assert response.get_json() == {"success": True, "data": {"ok": True}}


def test_token_required_returns_standard_error_envelope(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret-token")
    app = Flask(__name__)

    @token_required
    def view():
        return json_success({"ok": True})

    with app.test_request_context("/api/example"):
        response, status = view()

    assert status == 401
    assert response.get_json() == {
        "success": False,
        "error": "unauthorized",
        "code": "auth_required",
    }


def test_blueprint_guard_returns_standard_error_envelope(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret-token")
    client = _build_guarded_app().test_client()

    response = client.get("/api/guarded/ping")

    assert response.status_code == 401
    assert response.get_json() == {
        "success": False,
        "error": "unauthorized",
        "code": "auth_required",
    }


def test_blueprint_guard_accepts_x_agora_token(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret-token")
    client = _build_guarded_app().test_client()

    response = client.get("/api/guarded/ping", headers={"X-Agora-Token": "secret-token"})

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": {"ok": True}}


def test_blueprint_guard_accepts_bearer_token(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret-token")
    client = _build_guarded_app().test_client()

    response = client.get("/api/guarded/ping", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": {"ok": True}}


def test_blueprint_guard_accepts_query_token(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret-token")
    client = _build_guarded_app().test_client()

    response = client.get("/api/guarded/ping?token=secret-token")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": {"ok": True}}
