"""Integrationstest: `/readyz` meldet `postgres: ok` gegen echtes PostgreSQL (#1581).

Die Unit-Tests (``backend/tests/test_readiness_postgres.py``) decken alle drei
Zustände gegen Fakes ab. Dieser Test ist der Beweis, dass der ``ok``-Zweig
tatsächlich gegen eine laufende PostgreSQL-Instanz funktioniert — mit der
echten `SELECT 1`-Probe über den zentralen ``Database``-Adapter, nicht gegen
ein Double.
"""

from __future__ import annotations

import pytest
from flask import Flask

from app.config import Config
from app.readiness import register_readiness_routes

pytestmark = pytest.mark.integration


@pytest.fixture
def app() -> Flask:
    application = Flask(__name__)
    register_readiness_routes(application)
    return application


def test_readyz_reports_postgres_ok_against_a_real_database(
    app, monkeypatch, postgres_database_url
):
    monkeypatch.setattr(Config, "PROJECT_BACKEND", "postgres")
    monkeypatch.setattr(Config, "DATABASE_URL", postgres_database_url)

    client = app.test_client()

    response = client.get("/readyz")

    payload = response.get_json()
    assert payload["checks"]["postgres"] == {
        "ok": True,
        "detail": "ok",
        "state": "ok",
    }
