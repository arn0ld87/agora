"""Tests für @require_scope-Decorator (PR 4 Hardening §3.3)."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from flask import Flask

from app.services.api_keys_store import ApiKeysStore
from app.utils.api_responses import install_api_error_handlers
from app.utils.scopes import require_scope


@pytest.fixture(autouse=True)
def _reset_store(monkeypatch, tmp_path):
    """Setzt Store-Singleton, Fernet-Cache und Auth-Env für jeden Test zurück."""
    fernet_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("AGORA_FERNET_KEY", fernet_key)
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    # AGORA_AUTH_TOKEN setzen damit require_scope aktiv ist (kein Open-Mode)
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "test-master-token-for-scope-tests")

    # Fernet-Cache invalidieren
    import app.services.api_keys_persistence as _pm
    _pm._fernet_instance = None
    _pm._fernet_key_raw = None

    from app.services import api_keys_store as _mod
    _mod._store_singleton = ApiKeysStore()
    yield
    _mod._store_singleton = ApiKeysStore()


@pytest.fixture
def app():
    """Flask-Test-App mit zwei Endpunkten: report:read und report:write."""
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    install_api_error_handlers(flask_app)

    @flask_app.route("/report/read")
    @require_scope("report:read")
    def read_report():
        return {"success": True, "action": "read"}

    @flask_app.route("/report/write", methods=["POST"])
    @require_scope("report:write")
    def write_report():
        return {"success": True, "action": "write"}

    @flask_app.route("/graph/write", methods=["POST"])
    @require_scope("graph:write")
    def write_graph():
        return {"success": True, "action": "graph_write"}

    @flask_app.route("/sim/control", methods=["POST"])
    @require_scope("simulation:control")
    def control_sim():
        return {"success": True, "action": "control"}

    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _make_key(scopes: list[str]) -> str:
    from app.services.api_keys_store import get_api_keys_store
    resp = get_api_keys_store().create("test-key", scopes)  # type: ignore[arg-type]
    return resp.token


class TestNoApiKey:
    def test_no_api_key_returns_401(self, client):
        resp = client.get("/report/read")
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"] == "unauthorized"
        assert body["code"] == "no_api_key"


class TestAdminScope:
    def test_key_with_admin_scope_passes(self, client):
        token = _make_key(["admin"])
        resp = client.get("/report/read", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_key_with_admin_scope_passes_write(self, client):
        token = _make_key(["admin"])
        resp = client.post("/report/write", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestFineGrainedScope:
    def test_key_with_matching_fine_grained_scope_passes(self, client):
        # Fine-grained Scopes im Key kommen im nächsten Slice (Literal-Erweiterung).
        # Bis dahin: coarse "read" Scope deckt "report:read" via Hierarchie.
        token = _make_key(["read"])
        resp = client.get("/report/read", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_key_with_read_scope_does_not_match_write(self, client):
        token = _make_key(["read"])
        resp = client.post("/report/write", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestWriteScopeHierarchy:
    def test_key_with_write_scope_covers_report_write(self, client):
        token = _make_key(["write"])
        resp = client.post("/report/write", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_key_with_write_scope_covers_control(self, client):
        token = _make_key(["write"])
        resp = client.post("/sim/control", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_key_with_write_scope_covers_read(self, client):
        token = _make_key(["write"])
        resp = client.get("/report/read", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestReadScopeBlocked:
    def test_key_with_read_scope_blocks_write_endpoint(self, client):
        token = _make_key(["read"])
        resp = client.post("/report/write", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_key_without_required_scope_returns_403_with_body(self, client):
        token = _make_key(["read"])
        resp = client.post("/graph/write", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["error"] == "forbidden"
        assert body["code"] == "scope_missing"
        assert body["required"] == "graph:write"
        assert "read" in body["have"]
