"""Tests for token auth response contracts."""

import logging

from flask import Blueprint, Flask

from app.utils.api_responses import json_success
from app.utils.auth import install_blueprint_guard, log_auth_mode, token_required


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


def test_blueprint_guard_accepts_query_token_in_debug(monkeypatch):
    """?token= funktioniert nur im Debug-Modus (Dev)."""
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret-token")
    app = _build_guarded_app()
    app.config["DEBUG"] = True
    client = app.test_client()

    response = client.get("/api/guarded/ping?token=secret-token")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": {"ok": True}}


def test_blueprint_guard_rejects_query_token_in_prod(monkeypatch):
    """?token= ist in Prod (FLASK_DEBUG=false) deaktiviert (F2.2)."""
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret-token")
    app = _build_guarded_app()
    app.config["DEBUG"] = False
    client = app.test_client()

    response = client.get("/api/guarded/ping?token=secret-token")

    # In Prod wird ?token= ignoriert → normaler Auth-Fehler
    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"
    assert response.get_json()["code"] == "auth_required"


def _capture_logs(target_logger):
    handler = _ListHandler()
    target_logger.addHandler(handler)
    target_logger.setLevel(logging.DEBUG)
    return handler


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_log_auth_mode_token_set_emits_info(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "deploy-secret")
    monkeypatch.delenv("AGORA_ALLOW_ANONYMOUS", raising=False)
    app = Flask(__name__)
    app.config["DEBUG"] = False
    logger = logging.getLogger("test.auth.token")
    handler = _capture_logs(logger)

    log_auth_mode(app, logger)

    assert any(r.levelno == logging.INFO and "AGORA_AUTH_TOKEN aktiv" in r.message for r in handler.records)


def test_log_auth_mode_allow_anonymous_emits_warning(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
    app = Flask(__name__)
    app.config["DEBUG"] = False
    logger = logging.getLogger("test.auth.allow")
    handler = _capture_logs(logger)

    log_auth_mode(app, logger)

    assert any(
        r.levelno == logging.WARNING and "ALLOW_ANONYMOUS=true" in r.message
        for r in handler.records
    )


def test_log_auth_mode_debug_no_token_warns(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("AGORA_ALLOW_ANONYMOUS", raising=False)
    app = Flask(__name__)
    app.config["DEBUG"] = True
    logger = logging.getLogger("test.auth.debug")
    handler = _capture_logs(logger)

    log_auth_mode(app, logger)

    assert any(
        r.levelno == logging.WARNING and "FLASK_DEBUG aktiv" in r.message
        for r in handler.records
    )


def test_log_auth_mode_no_token_no_flag_no_debug_logs_error(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("AGORA_ALLOW_ANONYMOUS", raising=False)
    app = Flask(__name__)
    app.config["DEBUG"] = False
    logger = logging.getLogger("test.auth.bypass")
    handler = _capture_logs(logger)

    log_auth_mode(app, logger)

    assert any(
        r.levelno == logging.ERROR and "Config.validate()" in r.message
        for r in handler.records
    )
