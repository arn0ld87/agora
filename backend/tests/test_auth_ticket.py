"""Integration tests for ?ticket= auth and POST /api/auth/ticket (P0.2b)."""

from __future__ import annotations

import pytest
from flask import Blueprint, Flask

from app.api.auth import auth_bp
from app.utils import signed_ticket
from app.utils.api_responses import (
    install_api_error_handlers,
    json_success,
)
from app.utils.auth import allow_ticket_auth, install_blueprint_guard
from app.utils.rate_limit import ticket_rate_limiter


SECRET = "test-secret-do-not-use"
TOKEN = "deploy-token"


@pytest.fixture(autouse=True)
def _reset_consumed_set():
    signed_ticket._reset_seen_for_tests()
    ticket_rate_limiter.reset_for_tests()
    yield
    signed_ticket._reset_seen_for_tests()
    ticket_rate_limiter.reset_for_tests()


@pytest.fixture(scope="module")
def app():
    """Build the Flask app once per module — Blueprint guards can only be
    installed before the first registration, so we keep app + guard setup
    out of per-test fixtures."""
    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = SECRET
    flask_app.config["AGORA_TICKET_RATE_LIMIT_MAX"] = 2
    flask_app.config["AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS"] = 60
    install_api_error_handlers(flask_app)

    bp = Blueprint("guarded", __name__)

    @bp.route("/sse/<sim_id>")
    @allow_ticket_auth(lambda sim_id: f"sse:{sim_id}", single_use=False)
    def sse(sim_id):
        return json_success({"sim": sim_id})

    @bp.route("/dl/<rid>")
    @allow_ticket_auth(lambda rid: f"download:report:{rid}")
    def dl(rid):
        return json_success({"rid": rid})

    @bp.route("/no-ticket")
    def no_ticket():
        return json_success({"ok": True})

    install_blueprint_guard(bp)
    install_blueprint_guard(auth_bp)
    flask_app.register_blueprint(bp, url_prefix="/api/guarded")
    flask_app.register_blueprint(auth_bp, url_prefix="/api/auth")
    return flask_app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", TOKEN)
    return app.test_client()


def test_ticket_endpoint_requires_token(client):
    response = client.post("/api/auth/ticket", json={"scope": "sse:sim_abc"})

    assert response.status_code == 401


def test_ticket_endpoint_rate_limits_before_auth_guard(client):
    for _ in range(2):
        response = client.post("/api/auth/ticket", json={"scope": "sse:sim_abc"})
        assert response.status_code == 401

    response = client.post("/api/auth/ticket", json={"scope": "sse:sim_abc"})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    body = response.get_json()
    assert body["code"] == "rate_limited"
    assert body["retry_after_seconds"] == 60


def test_ticket_endpoint_returns_ticket_for_valid_scope(client):
    response = client.post(
        "/api/auth/ticket",
        json={"scope": "sse:sim_abc"},
        headers={"X-Agora-Token": TOKEN},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["scope"] == "sse:sim_abc"
    assert data["ticket"].startswith("v1.")
    assert isinstance(data["exp"], int)


def test_ticket_endpoint_rejects_invalid_scope(client):
    response = client.post(
        "/api/auth/ticket",
        json={"scope": "admin:everything"},
        headers={"X-Agora-Token": TOKEN},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_scope"


def test_ticket_endpoint_rejects_excessive_ttl(client):
    response = client.post(
        "/api/auth/ticket",
        json={"scope": "sse:sim_abc", "ttl_seconds": 99999},
        headers={"X-Agora-Token": TOKEN},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_ttl"


def test_guarded_endpoint_accepts_valid_ticket(client):
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60)

    response = client.get(f"/api/guarded/sse/sim_abc?ticket={ticket}")

    assert response.status_code == 200
    assert response.get_json()["data"]["sim"] == "sim_abc"


def test_guarded_endpoint_rejects_ticket_for_other_simulation(client):
    ticket = signed_ticket.issue(SECRET, "sse:sim_other", ttl_seconds=60)

    response = client.get(f"/api/guarded/sse/sim_abc?ticket={ticket}")

    assert response.status_code == 401


def test_guarded_sse_endpoint_allows_ticket_reuse(client):
    """SSE views are reusable so EventSource reconnects within TTL still work."""
    ticket = signed_ticket.issue(SECRET, "sse:sim_abc", ttl_seconds=60)

    first = client.get(f"/api/guarded/sse/sim_abc?ticket={ticket}")
    second = client.get(f"/api/guarded/sse/sim_abc?ticket={ticket}")

    assert first.status_code == 200
    assert second.status_code == 200


def test_guarded_download_endpoint_rejects_ticket_replay(client):
    ticket = signed_ticket.issue(SECRET, "download:report:r1", ttl_seconds=60)

    first = client.get(f"/api/guarded/dl/r1?ticket={ticket}")
    second = client.get(f"/api/guarded/dl/r1?ticket={ticket}")

    assert first.status_code == 200
    assert second.status_code == 401


def test_guarded_endpoint_without_ticket_marker_ignores_ticket(client):
    """A view without @allow_ticket_auth must not be reachable via ?ticket=."""
    ticket = signed_ticket.issue(SECRET, "sse:any", ttl_seconds=60)

    response = client.get(f"/api/guarded/no-ticket?ticket={ticket}")

    assert response.status_code == 401
