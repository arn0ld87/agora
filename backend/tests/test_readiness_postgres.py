"""Der ``postgres``-Check von `/readyz` in allen drei Zuständen (Issue #1581).

Siehe ``backend/tests/api/test_readyz_endpoint.py`` für die bestehenden
Readiness-Tests (Neo4j, Redis, Upload-Dir, Embedding) — die bleiben
unverändert. Dieser Modul deckt ausschließlich den neuen ``postgres``-Zweig
ab: ``disabled`` (Legacy-Default, keine Verbindung), ``ok`` (SELECT 1 gelingt)
und ``unavailable`` (SELECT 1 scheitert), sowie die Zusage, dass dabei nie
Host, User, Passwort, Port oder Datenbankname der `DATABASE_URL` im
Response-Body landen.
"""

from __future__ import annotations

import json

import pytest
from flask import Flask

import app.readiness as readiness_module
from app.config import Config
from app.infrastructure.postgres.session import Database
from app.readiness import register_readiness_routes

# Absichtlich "sensible" Bestandteile, die eine echte psycopg-Fehlermeldung
# typischerweise im Klartext trägt — keine echten Zugangsdaten.
_FAKE_HOST = "dbhost.internal.example"
_FAKE_PORT = "6543"
_FAKE_USER = "sehr-geheimer-user"
_FAKE_PASSWORD = "sehr-geheimes-passwort"
_FAKE_DBNAME = "agora_metadata_geheim"
_FAKE_DATABASE_URL = (
    f"postgresql+psycopg://{_FAKE_USER}:{_FAKE_PASSWORD}@{_FAKE_HOST}:{_FAKE_PORT}/{_FAKE_DBNAME}"
)
_FAKE_URL_PARTS = (_FAKE_HOST, _FAKE_PORT, _FAKE_USER, _FAKE_PASSWORD, _FAKE_DBNAME)


@pytest.fixture
def app(tmp_path) -> Flask:
    """Minimale Flask-App mit Readiness-Routen — andere Checks sind hier
    bewusst nicht auf 'ok' gestellt, die Tests fragen nur ``checks["postgres"]``
    ab."""
    application = Flask(__name__)
    application.config["UPLOAD_FOLDER"] = str(tmp_path)
    application.config["EMBEDDING_MODEL"] = "qwen3-embedding:4b"
    application.config["VECTOR_DIM"] = 2560
    register_readiness_routes(application)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_backend_switches(monkeypatch):
    """Alle ``*_BACKEND``-Schalter auf Legacy-Default — unabhängig davon, was
    die lokale Umgebung sonst gesetzt hat."""
    for name in dir(Config):
        if name.endswith("_BACKEND") and getattr(Config, name, None) == "postgres":
            monkeypatch.setattr(Config, name, "file")
    monkeypatch.setattr(Config, "METADATA_BACKEND", "legacy")
    monkeypatch.setattr(Config, "LLM_PROFILE_BACKEND", "sqlite")
    monkeypatch.setattr(Config, "PROJECT_BACKEND", "file")


# ---------------------------------------------------------------------------
# disabled — Legacy-Default, keine Verbindung
# ---------------------------------------------------------------------------


def test_postgres_check_is_disabled_when_no_backend_is_postgres(client):
    response = client.get("/readyz")

    payload = response.get_json()
    postgres_check = payload["checks"]["postgres"]
    assert postgres_check == {
        "ok": True,
        "detail": "no AGORA_*_BACKEND is set to postgres",
        "state": "disabled",
    }


def test_disabled_postgres_check_never_builds_a_database(client, monkeypatch):
    """Kein ``AGORA_*_BACKEND=postgres`` → keine Engine, nicht einmal eine
    ``Database``-Instanz. Spy statt echter Verbindung."""

    class _ExplodingDatabase:
        def __init__(self, *args, **kwargs):
            raise AssertionError(
                "Database darf nicht konstruiert werden, wenn kein "
                "AGORA_*_BACKEND auf postgres steht"
            )

    monkeypatch.setattr(readiness_module, "Database", _ExplodingDatabase)

    response = client.get("/readyz")

    assert response.get_json()["checks"]["postgres"]["state"] == "disabled"


def test_disabled_state_does_not_make_readyz_red(client):
    """``disabled`` ist ``ok=True`` — darf /readyz allein nicht auf 503 ziehen."""
    response = client.get("/readyz")

    payload = response.get_json()
    assert payload["checks"]["postgres"]["ok"] is True
    # Andere Checks sind in diesem Fixture nicht konfiguriert und liefern
    # daher ok=False — das beweist, dass ein rotes /readyz hier NICHT vom
    # Postgres-Check kommt.
    assert payload["checks"]["postgres"]["state"] == "disabled"


# ---------------------------------------------------------------------------
# ok — Backend aktiv, SELECT 1 gelingt
# ---------------------------------------------------------------------------


def test_postgres_check_reports_ok_when_backend_active_and_probe_succeeds(
    client, monkeypatch
):
    monkeypatch.setattr(Config, "PROJECT_BACKEND", "postgres")
    monkeypatch.setattr(Config, "DATABASE_URL", _FAKE_DATABASE_URL)
    monkeypatch.setattr(Database, "check_connection", lambda self: True)

    response = client.get("/readyz")

    payload = response.get_json()
    assert payload["checks"]["postgres"] == {
        "ok": True,
        "detail": "ok",
        "state": "ok",
    }


# ---------------------------------------------------------------------------
# unavailable — Backend aktiv, SELECT 1 scheitert
# ---------------------------------------------------------------------------


def test_postgres_check_reports_unavailable_when_probe_fails(client, monkeypatch):
    monkeypatch.setattr(Config, "PROJECT_BACKEND", "postgres")
    monkeypatch.setattr(Config, "DATABASE_URL", _FAKE_DATABASE_URL)
    monkeypatch.setattr(Database, "check_connection", lambda self: False)

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["checks"]["postgres"] == {
        "ok": False,
        "detail": "postgres connectivity probe failed",
        "state": "unavailable",
    }


def test_unavailable_postgres_check_makes_readyz_red(client, monkeypatch):
    monkeypatch.setattr(Config, "PROJECT_BACKEND", "postgres")
    monkeypatch.setattr(Config, "DATABASE_URL", _FAKE_DATABASE_URL)
    monkeypatch.setattr(Database, "check_connection", lambda self: False)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["status"] == "not_ready"


def test_postgres_check_never_leaks_url_parts_when_the_driver_exception_contains_them(
    client, monkeypatch
):
    """Reale psycopg-Fehlermeldungen tragen Host/User/Passwort/Port/DB-Namen
    im Klartext. Selbst wenn ``check_connection`` intern nicht fängt und die
    Exception durchreicht, darf davon nichts im Response-Body landen."""
    monkeypatch.setattr(Config, "PROJECT_BACKEND", "postgres")
    monkeypatch.setattr(Config, "DATABASE_URL", _FAKE_DATABASE_URL)

    def _raise_leaky_error(self):
        raise RuntimeError(
            f'connection to server at "{_FAKE_HOST}", port {_FAKE_PORT} failed: '
            f'FATAL: password authentication failed for user "{_FAKE_USER}" '
            f'(password="{_FAKE_PASSWORD}", dbname="{_FAKE_DBNAME}")'
        )

    monkeypatch.setattr(Database, "check_connection", _raise_leaky_error)

    response = client.get("/readyz")

    assert response.status_code == 503
    body_text = json.dumps(response.get_json())
    for secret_part in _FAKE_URL_PARTS:
        assert secret_part not in body_text
    assert response.get_json()["checks"]["postgres"] == {
        "ok": False,
        "detail": "postgres connectivity probe failed",
        "state": "unavailable",
    }


def test_hanging_probe_is_cut_off_by_the_deadline(client, monkeypatch):
    """Codex-Review auf #1600: nimmt der Server die Verbindung an und
    antwortet nicht mehr, darf /readyz nicht unbegrenzt hängen."""
    import threading as _threading

    import app.readiness as readiness

    release = _threading.Event()
    monkeypatch.setattr(Config, "PROJECT_BACKEND", "postgres")
    monkeypatch.setattr(Config, "DATABASE_URL", _FAKE_DATABASE_URL)
    monkeypatch.setattr(readiness, "_POSTGRES_READINESS_DEADLINE", 0.2)
    monkeypatch.setattr(Database, "check_connection", lambda self: release.wait(5) or True)

    try:
        resp = client.get("/readyz")
    finally:
        release.set()

    assert resp.status_code == 503
    assert resp.get_json()["checks"]["postgres"]["state"] == "unavailable"


def test_probe_failure_is_logged_without_traceback(client, monkeypatch):
    """Codex-Review auf #1600: kein ``exc_info`` — der Traceback trüge die
    Exception-Message mit Zugangsdaten am Redaktionsfilter vorbei ins Log."""
    import logging

    import app.readiness as readiness

    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    def _raise(self):
        raise RuntimeError("postgresql://agora:geheim@db.intern:5432/agora")

    monkeypatch.setattr(Config, "PROJECT_BACKEND", "postgres")
    monkeypatch.setattr(Config, "DATABASE_URL", _FAKE_DATABASE_URL)
    monkeypatch.setattr(Database, "check_connection", _raise)
    handler = _Collect(level=logging.WARNING)
    readiness.logger.addHandler(handler)
    try:
        client.get("/readyz")
    finally:
        readiness.logger.removeHandler(handler)

    probe_records = [r for r in records if "readiness probe failed" in r.getMessage()]
    assert probe_records
    for record in probe_records:
        assert record.exc_info is None
        assert "geheim" not in record.getMessage()
