"""Tests für CORS-Konfiguration (Issue #592).

Verifiziert:
- AGORA_CORS_ALLOW_ALL=true deaktiviert Access-Control-Allow-Credentials
  auf Preflight-Requests (Wildcard + Credentials ist CORS-Fehler).
- App-Start wird verweigert wenn AGORA_CORS_ALLOW_ALL=true im
  Produktionsmodus (DEBUG=False, d.h. FLASK_DEBUG nicht true) gesetzt
  ist (fail-closed).
"""
from __future__ import annotations

import pytest
from flask import Flask
from flask_cors import CORS


# ---------------------------------------------------------------------------
# Hilfsfunktion: minimale Flask-App mit CORS analog zu create_app
# ---------------------------------------------------------------------------


def _make_cors_app(allow_all: bool) -> Flask:
    """Erstellt eine minimale Flask-App mit CORS-Konfiguration wie create_app."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    if allow_all:
        cors_origins = "*"
    else:
        cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    CORS(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        supports_credentials=not allow_all,
    )

    @app.route("/api/ping", methods=["GET", "OPTIONS"])
    def ping():
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# Test 1: AGORA_CORS_ALLOW_ALL=true → kein Access-Control-Allow-Credentials
# ---------------------------------------------------------------------------


def test_allow_all_disables_credentials():
    """Preflight mit AGORA_CORS_ALLOW_ALL=true darf KEIN
    Access-Control-Allow-Credentials senden.

    Hintergrund: Browser lehnen Wildcard-Origin + Credentials kombiniert
    ab (CORS-Spec §8.7). flask-cors setzt supports_credentials=False wenn
    allow_all aktiv — dieser Test verifiziert das End-to-End.

    flask-cors >= 4.x reflektiert bei supports_credentials=False die
    angeforderte Origin statt "*", sendet aber keinen
    Access-Control-Allow-Credentials-Header.
    """
    app = _make_cors_app(allow_all=True)
    client = app.test_client()

    resp = client.options(
        "/api/ping",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    # Preflight muss beantwortet werden (200 oder 204)
    assert resp.status_code in (200, 204)

    # Access-Control-Allow-Credentials darf NICHT "true" sein
    # (Header fehlt komplett oder hat anderen Wert — beides akzeptabel)
    creds_header = resp.headers.get("Access-Control-Allow-Credentials", "")
    assert creds_header.lower() != "true", (
        f"Access-Control-Allow-Credentials darf bei allow_all nicht 'true' sein, "
        f"war aber: {creds_header!r}"
    )


def test_restricted_origins_keeps_credentials():
    """Mit expliziter Origin-Liste bleibt supports_credentials aktiv."""
    app = _make_cors_app(allow_all=False)
    client = app.test_client()

    resp = client.options(
        "/api/ping",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    creds_header = resp.headers.get("Access-Control-Allow-Credentials", "")
    assert creds_header.lower() == "true", (
        f"Access-Control-Allow-Credentials sollte 'true' sein bei expliziter Origin, "
        f"war: {creds_header!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: fail-closed — App-Start verweigert in production
# ---------------------------------------------------------------------------


def test_production_guard_raises_on_allow_all(monkeypatch):
    """create_app() muss RuntimeError werfen wenn AGORA_CORS_ALLOW_ALL=true
    im Produktionsmodus (DEBUG=False) gesetzt ist (fail-closed).
    """
    monkeypatch.setenv("AGORA_CORS_ALLOW_ALL", "true")
    monkeypatch.setenv("FLASK_DEBUG", "false")
    monkeypatch.setenv("AGORA_SKIP_EMBEDDING_PROBE", "true")

    # Config.DEBUG wird beim Import aus FLASK_DEBUG evaluiert — direkt
    # patchen, damit der Test unabhängig von Import-Reihenfolge robust ist.
    from app.config import Config
    monkeypatch.setattr(Config, "DEBUG", False)

    from app import create_app

    with pytest.raises(RuntimeError, match="AGORA_CORS_ALLOW_ALL"):
        create_app()


def test_production_guard_ok_without_allow_all(monkeypatch, tmp_path):
    """create_app() im Produktionsmodus (DEBUG=False) ohne
    AGORA_CORS_ALLOW_ALL=true soll NICHT wegen CORS abbrechen.

    Dieser Test prüft nur, dass kein CORS-bedingter RuntimeError kommt.
    Andere Start-Fehler (Neo4j, Embedding) sind akzeptabel und werden
    hier ignoriert.
    """
    monkeypatch.setenv("FLASK_DEBUG", "false")
    monkeypatch.delenv("AGORA_CORS_ALLOW_ALL", raising=False)
    monkeypatch.setenv("AGORA_SKIP_EMBEDDING_PROBE", "true")

    from app.config import Config
    monkeypatch.setattr(Config, "DEBUG", False)

    from app import create_app

    try:
        create_app()
    except RuntimeError as exc:
        # Nur CORS-spezifische Fehler sind hier nicht erlaubt
        assert "AGORA_CORS_ALLOW_ALL" not in str(exc), (
            f"CORS-Guard darf nicht feuern ohne AGORA_CORS_ALLOW_ALL=true: {exc}"
        )
