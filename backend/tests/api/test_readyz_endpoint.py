"""Tests für /readyz Readiness-Endpoint (PR 1, Finding 1.8).

Vertrag:
  A. /health bleibt unverändert: liefert 200 + {"status": "ok"} ohne
     Abhängigkeitsprüfungen (Liveness).
  B. /readyz prüft Neo4j-Connection, Redis-Ping, Upload-Verzeichnis
     schreibbar, Embedding-Konfig kohärent (EMBEDDING_MODEL ↔ VECTOR_DIM).
     Alle ok → 200; eine kaputt → 503.
     C. Antwort-Body enthält pro Check {"ok": bool, "detail": str}. Details
      nennen den kaputten Check, leaken aber keine Exception-/URI-Interna.
  D. Redis-Check wird übersprungen, wenn der konfigurierte Event-Bus auf
     File-Backend steht — sonst kann ein bewusster `EVENT_BUS_BACKEND=file`
     das ganze /readyz rot machen.
"""

from __future__ import annotations

import os

import pytest
from flask import Flask

from app.readiness import register_readiness_routes


# ---------------------------------------------------------------------------
# Test-Doubles
# ---------------------------------------------------------------------------


class _FakeNeo4jStorageOk:
    def verify_connectivity(self) -> None:
        return None


class _FakeNeo4jStorageBroken:
    def verify_connectivity(self) -> None:
        raise RuntimeError("bolt://neo4j:7687 unreachable: Connection refused")


class _FakeRedisEventBus:
    """Event-Bus mit explizitem ``verify_connectivity``-Probe-Vertrag.

    Spiegelt das Interface, das ``RedisEventBus`` in Production exposiert
    (siehe ``backend/app/services/event_bus_redis.py``).
    """

    def __init__(self, ok: bool = True, error: str = "") -> None:
        self._ok = ok
        self._error = error or "redis://redis:6379/0 unreachable: ECONNREFUSED"

    def verify_connectivity(self) -> None:
        if not self._ok:
            raise RuntimeError(self._error)


class _FakeFileEventBus:
    """File-Backend: exposiert keinen ``verify_connectivity``-Hook → Probe wird
    übersprungen. Spiegelt die ``FilePollingEventBus``-Realität."""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path):
    """Frische Flask-App mit readiness-Routen + Happy-Path-Konfig."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    application = Flask(__name__)
    application.config["UPLOAD_FOLDER"] = str(upload_dir)
    # qwen3-embedding:4b liefert 2560-dim Vektoren — kohärent.
    application.config["EMBEDDING_MODEL"] = "qwen3-embedding:4b"
    application.config["VECTOR_DIM"] = 2560

    application.extensions["neo4j_storage"] = _FakeNeo4jStorageOk()
    application.extensions["neo4j_storage_error"] = None
    application.extensions["event_bus"] = _FakeRedisEventBus(ok=True)
    register_readiness_routes(application)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------


def test_health_liveness_stays_simple(client):
    """/health ist NICHT abhängigkeitsabhängig — Trennung zu /readyz."""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert "checks" not in payload


# ---------------------------------------------------------------------------
# Readiness — Happy Path
# ---------------------------------------------------------------------------


def test_readyz_returns_ready_when_all_checks_pass(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    checks = payload["checks"]
    assert checks["neo4j"]["ok"] is True
    assert checks["redis"]["ok"] is True
    assert checks["upload_dir"]["ok"] is True
    assert checks["embedding_config"]["ok"] is True


# ---------------------------------------------------------------------------
# Readiness — Fehlerfälle
# ---------------------------------------------------------------------------


def test_readyz_returns_503_when_neo4j_unreachable(app, client):
    app.extensions["neo4j_storage"] = _FakeNeo4jStorageBroken()

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["neo4j"]["ok"] is False
    assert payload["checks"]["neo4j"]["detail"] == "neo4j connectivity probe failed"
    assert "bolt://" not in payload["checks"]["neo4j"]["detail"]
    # Andere Checks bleiben grün.
    assert payload["checks"]["upload_dir"]["ok"] is True


def test_readyz_returns_503_when_neo4j_storage_missing(app, client):
    """Neo4j konnte beim Boot gar nicht initialisiert werden (None in
    app.extensions). Review §1.8 nennt das als zentralen Fall."""
    app.extensions["neo4j_storage"] = None
    app.extensions["neo4j_storage_error"] = "init failed: auth"

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["checks"]["neo4j"]["ok"] is False
    assert "init failed: auth" in payload["checks"]["neo4j"]["detail"]


def test_readyz_returns_503_when_redis_unreachable(app, client):
    app.extensions["event_bus"] = _FakeRedisEventBus(ok=False)

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["checks"]["redis"]["ok"] is False
    assert payload["checks"]["redis"]["detail"] == "redis connectivity probe failed"
    assert "redis://" not in payload["checks"]["redis"]["detail"]


def test_readyz_skips_redis_check_for_file_backend(app, client):
    """File-Event-Bus → Redis-Ping nicht ausführen, sonst legt ein
    bewusster EVENT_BUS_BACKEND=file das ganze /readyz rot."""
    app.extensions["event_bus"] = _FakeFileEventBus()

    response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["checks"]["redis"]["ok"] is True
    assert "skipped" in payload["checks"]["redis"]["detail"].lower()


def test_readyz_returns_503_when_upload_dir_missing(app, client, tmp_path):
    """Stateless-Probe: ein fehlendes Upload-Verzeichnis ist ein Setup-
    Fehler, den /readyz meldet — nicht heimlich anlegt."""
    missing = tmp_path / "not-there"
    app.config["UPLOAD_FOLDER"] = str(missing)

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["checks"]["upload_dir"]["ok"] is False
    assert "not exist" in payload["checks"]["upload_dir"]["detail"].lower()
    # Probe darf das Verzeichnis NICHT erstellen.
    assert not missing.exists()


def test_readyz_returns_503_when_upload_dir_unwritable(app, client, tmp_path):
    unwritable = tmp_path / "no-write"
    unwritable.mkdir()
    os.chmod(unwritable, 0o500)  # r-x
    app.config["UPLOAD_FOLDER"] = str(unwritable)

    try:
        response = client.get("/readyz")
        assert response.status_code == 503
        payload = response.get_json()
        assert payload["checks"]["upload_dir"]["ok"] is False
        assert "not writable" in payload["checks"]["upload_dir"]["detail"].lower()
    finally:
        os.chmod(unwritable, 0o700)


def test_readyz_returns_503_on_embedding_config_mismatch(app, client):
    """qwen3-embedding:4b liefert 2560-dim Vektoren — VECTOR_DIM=768 ist
    eine garantierte Inkonsistenz, die Neo4j-Index-Inserts zerlegt."""
    app.config["EMBEDDING_MODEL"] = "qwen3-embedding:4b"
    app.config["VECTOR_DIM"] = 768

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["checks"]["embedding_config"]["ok"] is False
    detail = payload["checks"]["embedding_config"]["detail"]
    assert "vector_dim" in detail.lower()
    assert "768" in detail
    assert "2560" in detail
