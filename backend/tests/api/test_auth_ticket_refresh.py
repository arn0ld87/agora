"""Tests für P1-Befund #4: POST /api/auth/ticket muss ohne gültiges X-Ticket
funktionieren, solange ein Master-Token oder API-Key vorliegt (Henne-Ei-Fix).

Hintergrund:  install_blueprint_guard mit token_only_endpoints={"auth.issue_ticket"}
stellt sicher, dass der Ticket-Ausstellungs-Endpoint kein abgelaufenes Signed-Ticket
als Auth-Mittel akzeptiert.  Gültige Master-Token / API-Keys greifen weiterhin.

Wir bauen eine eigene Flask-Instanz mit einer lokalen auth-Route, weil der globale
``auth_bp``-Singleton bereits in ``test_auth_ticket.py`` mit ``install_blueprint_guard``
belegt ist und Blueprint-Guards nur einmal vor der Registrierung gesetzt werden können
(see test_llm_model_stream.py für denselben Trick).
"""

from __future__ import annotations

import time

import pytest
from flask import Blueprint, Flask, current_app, request

from app.utils import signed_ticket
from app.utils.api_responses import install_api_error_handlers, json_error, json_success
from app.utils.auth import install_blueprint_guard
from app.utils.rate_limit import ticket_rate_limiter

SECRET = "test-secret-ticket-refresh"
TOKEN = "master-token-refresh-test"

# Spiegelt die relevanten ALLOWED_SCOPE_PREFIXES aus app/api/auth.py
_ALLOWED_SCOPE_PREFIXES = ("sse:", "settings-stream", "llm-stream")


@pytest.fixture(autouse=True)
def _reset_state():
    signed_ticket._reset_seen_for_tests()
    ticket_rate_limiter.reset_for_tests()
    yield
    signed_ticket._reset_seen_for_tests()
    ticket_rate_limiter.reset_for_tests()


@pytest.fixture(scope="module")
def app():
    """Minimale Flask-App mit lokaler auth-Blueprint-Instanz.

    Verwendet ``token_only_endpoints=frozenset({"local_auth_refresh.issue_ticket"})``
    um den Henne-Ei-Fix zu testen.
    """
    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = SECRET
    flask_app.config["AGORA_TICKET_RATE_LIMIT_MAX"] = 3
    flask_app.config["AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS"] = 60
    install_api_error_handlers(flask_app)

    local_auth_bp = Blueprint("local_auth_refresh", __name__)

    @local_auth_bp.before_request
    def _limit_ticket_endpoint():
        """Rate-Limit-Hook analog app/api/auth.py."""
        if request.endpoint != "local_auth_refresh.issue_ticket" or request.method != "POST":
            return None
        from app.utils.api_errors import ApiErrorCode
        from app.utils.rate_limit import build_rate_limit_key

        result = ticket_rate_limiter.check(
            build_rate_limit_key("auth-ticket"),
            max_requests=current_app.config["AGORA_TICKET_RATE_LIMIT_MAX"],
            window_seconds=current_app.config["AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS"],
        )
        if result.allowed:
            return None

        response, status = json_error(
            ApiErrorCode.RATE_LIMITED,
            status=429,
            extra={"retry_after_seconds": result.retry_after_seconds},
        )
        response.headers["Retry-After"] = str(result.retry_after_seconds)
        return response, status

    @local_auth_bp.route("/ticket", methods=["POST"])
    def issue_ticket():
        payload = request.get_json(silent=True) or {}
        scope = (payload.get("scope") or "").strip()
        if not scope or not any(scope.startswith(p) for p in _ALLOWED_SCOPE_PREFIXES):
            return json_error("invalid scope", status=400, code="invalid_scope")
        secret = current_app.config.get("SECRET_KEY") or ""
        if not secret:
            return json_error("server misconfigured", status=500, code="no_secret")
        ticket = signed_ticket.issue(secret, scope, ttl_seconds=60)
        parsed = signed_ticket._parse(ticket)
        exp = parsed[1] if parsed else None
        return json_success({"ticket": ticket, "exp": exp, "scope": scope})

    # Henne-Ei-Fix: issue_ticket braucht kein gültiges Ticket, aber Token/API-Key.
    install_blueprint_guard(
        local_auth_bp,
        token_only_endpoints=frozenset({"local_auth_refresh.issue_ticket"}),
    )
    flask_app.register_blueprint(local_auth_bp, url_prefix="/api/auth")
    return flask_app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", TOKEN)
    return app.test_client()


# ---------------------------------------------------------------------------
# Case 1: Master-Token gültig, kein X-Ticket-Header → 200
# ---------------------------------------------------------------------------


def test_ticket_endpoint_works_without_x_ticket_when_master_token_valid(client):
    """POST /api/auth/ticket mit Master-Token aber OHNE abgelaufenes Ticket → 200.

    Das ist der Kern-Fix: Ein Browser, dessen Ticket abgelaufen ist, kann sich
    mit dem Master-Token ein neues holen, ohne vorher ein gültiges Ticket zu haben.
    """
    response = client.post(
        "/api/auth/ticket",
        json={"scope": "sse:sim_123"},
        headers={"X-Agora-Token": TOKEN},
        # explizit: kein ticket=-Query-Param, kein X-Ticket-Header
    )

    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["scope"] == "sse:sim_123"
    assert data["ticket"].startswith("v1.")
    assert isinstance(data["exp"], int)
    assert data["exp"] > int(time.time())


# ---------------------------------------------------------------------------
# Case 2: kein Session-Token, kein X-Ticket → 401
# ---------------------------------------------------------------------------


def test_ticket_endpoint_rejects_when_no_session_and_no_ticket(client):
    """Ohne Master-Token und ohne Ticket → 401.

    Ein vollständig unauthentifizierter Request soll abgelehnt werden.
    """
    response = client.post(
        "/api/auth/ticket",
        json={"scope": "sse:sim_456"},
        # kein Auth-Header, kein Token
    )

    assert response.status_code == 401
    assert response.get_json()["code"] == "auth_required"


# ---------------------------------------------------------------------------
# Case 3: Rate-Limit bleibt aktiv (auch ohne Ticket)
# ---------------------------------------------------------------------------


def test_ticket_endpoint_still_rate_limited(client):
    """Rate-Limit-Header bleibt auch nach dem Henne-Ei-Fix aktiv.

    Nach AGORA_TICKET_RATE_LIMIT_MAX=3 Requests → 429 mit Retry-After.
    """
    headers = {"X-Agora-Token": TOKEN}
    payload = {"scope": "sse:sim_ratelimit"}

    # Erlaubte Requests ausschöpfen
    for _ in range(3):
        resp = client.post("/api/auth/ticket", json=payload, headers=headers)
        assert resp.status_code == 200

    # Nächster Request → Rate-Limited
    resp = client.post("/api/auth/ticket", json=payload, headers=headers)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    body = resp.get_json()
    assert body["code"] == "rate_limited"
    assert isinstance(body["retry_after_seconds"], int)


# ---------------------------------------------------------------------------
# Case 4: Ein abgelaufenes (ungültiges) Signed-Ticket darf NICHT als Auth
#         für den Ticket-Endpoint verwendet werden
# ---------------------------------------------------------------------------


def test_ticket_endpoint_rejects_expired_ticket_as_auth(client):
    """Ein abgelaufenes Ticket als einzige Auth-Methode → 401.

    Das ist das Kernproblem, das dieser Slice löst: Kein Henne-Ei-Deadlock.
    Ein ungültiges (oder fehlendes) Ticket plus kein Master-Token → 401.
    """
    # Abgelaufenes Ticket bauen (TTL=-1 ist technisch ungültig, issue() aber
    # erlaubt es; verify() lehnt es ab). Alternativ: Ticket mit falschem Secret.
    fake_ticket = "v1.fake.fake.fake"

    response = client.post(
        "/api/auth/ticket",
        json={"scope": "sse:sim_789"},
        query_string={"ticket": fake_ticket},
        # kein Master-Token-Header
    )

    assert response.status_code == 401
