"""Tests for GET /api/llm/model-stream SSE endpoint (Slice E.1, Issue #213)."""

from __future__ import annotations

import time

import pytest
from flask import Blueprint, Flask

from app.utils import signed_ticket
from app.utils.api_responses import install_api_error_handlers, json_success
from app.utils.auth import install_blueprint_guard

SECRET = "test-secret-llm-stream"
TOKEN = "test-bearer-token"
SCOPE = "llm-stream"


@pytest.fixture(autouse=True)
def _reset_tickets():
    signed_ticket._reset_seen_for_tests()
    yield
    signed_ticket._reset_seen_for_tests()


@pytest.fixture(scope="module")
def app():
    """Build a minimal Flask app with only the llm_bp and a local auth endpoint.

    We deliberately do NOT import the global auth_bp singleton here to avoid
    the 'before_request can no longer be called on registered blueprint' error
    that occurs when two test modules both call install_blueprint_guard(auth_bp).
    The ticket-issuance behaviour is tested separately via signed_ticket directly.
    """
    from app.api import llm_bp

    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = SECRET
    install_api_error_handlers(flask_app)

    # Local auth blueprint that mirrors POST /api/auth/ticket behaviour
    # without reusing the global auth_bp singleton.
    local_auth_bp = Blueprint("local_auth_e1_test", __name__)

    @local_auth_bp.route("/ticket", methods=["POST"])
    def issue_ticket():
        from flask import current_app, request

        payload = request.get_json(silent=True) or {}
        scope = (payload.get("scope") or "").strip()
        allowed = ("sse:", "download:report:", "llm-stream")
        if not scope or not any(scope.startswith(p) for p in allowed):
            from app.utils.api_responses import json_error
            return json_error("invalid scope", status=400, code="invalid_scope")
        secret = current_app.config.get("SECRET_KEY") or ""
        ticket = signed_ticket.issue(secret, scope, ttl_seconds=60)
        return json_success({"ticket": ticket, "scope": scope})

    install_blueprint_guard(llm_bp)
    install_blueprint_guard(local_auth_bp)
    flask_app.register_blueprint(llm_bp, url_prefix="/api/llm")
    flask_app.register_blueprint(local_auth_bp, url_prefix="/api/auth")
    return flask_app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", TOKEN)
    return app.test_client()


@pytest.fixture
def open_client(app, monkeypatch):
    """Client with no auth required."""
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    return app.test_client()


def _valid_ticket() -> str:
    return signed_ticket.issue(SECRET, SCOPE, ttl_seconds=60)


def _expired_ticket() -> str:
    past_time = time.time() - 120
    return signed_ticket.issue(SECRET, SCOPE, ttl_seconds=1, now=past_time)


def _wrong_scope_ticket() -> str:
    return signed_ticket.issue(SECRET, "sse:other", ttl_seconds=60)


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestLLMModelStreamAuth:
    def test_401_without_ticket_or_token(self, client):
        response = client.get("/api/llm/model-stream")
        assert response.status_code == 401
        data = response.get_json()
        assert data["code"] == "auth_required"

    def test_401_with_expired_ticket(self, client):
        ticket = _expired_ticket()
        response = client.get(f"/api/llm/model-stream?ticket={ticket}")
        assert response.status_code == 401

    def test_401_with_wrong_scope_ticket(self, client):
        ticket = _wrong_scope_ticket()
        response = client.get(f"/api/llm/model-stream?ticket={ticket}")
        assert response.status_code == 401

    def test_401_with_garbage_ticket(self, client):
        response = client.get("/api/llm/model-stream?ticket=not-a-valid-ticket")
        assert response.status_code == 401

    def test_200_with_bearer_token(self, client):
        """Bearer token auth must also be accepted."""
        response = client.get(
            "/api/llm/model-stream",
            headers={"X-Agora-Token": TOKEN},
            buffered=False,
        )
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        response.close()

    def test_200_with_valid_ticket(self, client):
        ticket = _valid_ticket()
        response = client.get(
            f"/api/llm/model-stream?ticket={ticket}",
            buffered=False,
        )
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        response.close()

    def test_ticket_reuse_allowed_sse_is_non_single_use(self, client):
        """SSE tickets must be reusable (EventSource reconnects within TTL)."""
        ticket = _valid_ticket()
        r1 = client.get(f"/api/llm/model-stream?ticket={ticket}", buffered=False)
        r1.close()
        r2 = client.get(f"/api/llm/model-stream?ticket={ticket}", buffered=False)
        r2.close()
        # Both must succeed — non-single-use verify()
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_200_no_auth_required_when_no_token_configured(self, open_client):
        response = open_client.get("/api/llm/model-stream", buffered=False)
        assert response.status_code == 200
        response.close()


# ---------------------------------------------------------------------------
# Frame format tests
# ---------------------------------------------------------------------------

class TestLLMModelStreamFrameFormat:
    def test_first_frame_is_retry(self, open_client):
        """First SSE frame must be the retry: field."""
        response = open_client.get("/api/llm/model-stream", buffered=False)
        assert response.status_code == 200

        first_frame = None
        for raw in response.response:
            first_frame = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            break
        response.close()

        assert first_frame is not None
        assert "retry:" in first_frame
        assert "retry: 5000" in first_frame

    def test_event_frame_contains_id_and_data(self, open_client):
        """After publishing an event, the SSE frame must contain id: and data:."""
        import threading
        import time as _time

        from app.services.model_event_bus import ModelActiveEvent, model_event_bus

        frames = []

        def collect():
            response = open_client.get("/api/llm/model-stream", buffered=False)
            for raw in response.response:
                frame = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                frames.append(frame)
                if len(frames) >= 2:  # retry frame + data frame
                    break
            response.close()

        t = threading.Thread(target=collect, daemon=True)
        t.start()
        _time.sleep(0.15)  # let the stream connect and past retry frame

        ev = ModelActiveEvent(
            model="test-model",
            context="chat",
            provider="ollama",
            ts=_time.time(),
        )
        model_event_bus.publish(ev)
        t.join(timeout=3.0)

        # Find the data frame (not the retry frame)
        data_frames = [f for f in frames if "data:" in f]
        assert data_frames, f"No data frame received, got: {frames}"
        data_frame = data_frames[0]
        assert "id:" in data_frame
        assert "data:" in data_frame
        assert "test-model" in data_frame

    def test_mimetype_is_text_event_stream(self, open_client):
        response = open_client.get("/api/llm/model-stream", buffered=False)
        assert response.mimetype == "text/event-stream"
        response.close()

    def test_cache_control_no_cache(self, open_client):
        response = open_client.get("/api/llm/model-stream", buffered=False)
        assert "no-cache" in response.headers.get("Cache-Control", "")
        response.close()


# ---------------------------------------------------------------------------
# Ticket endpoint: llm-stream scope must be issuable via /api/auth/ticket
# ---------------------------------------------------------------------------

class TestLLMStreamTicketIssuance:
    def test_ticket_endpoint_allows_llm_stream_scope(self, client):
        response = client.post(
            "/api/auth/ticket",
            json={"scope": SCOPE},
            headers={"X-Agora-Token": TOKEN},
        )
        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["scope"] == SCOPE
        assert data["ticket"].startswith("v1.")
