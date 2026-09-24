"""HTTP-Tests fuer ``POST /api/simulation/prepare/status`` (#1174).

Deckt die drei Klartext-Kurzschluesse ab, die der Endpoint liefert, bevor er
auf einen ``Task`` zurueckgreift — jeder davon muss neben ``message`` jetzt
auch den stabilen i18n-Schluessel ``message_key`` tragen (Muster aus #1458).
Die HTTP-Ebene folgt bewusst dem Client-Fixture aus
``test_simulation_prepare_routing.py``.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp

VALID_SIM_ID = "sim_0123456789ab"
VALID_TASK_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


def test_status_already_prepared_via_simulation_id_carries_message_key(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.simulation_prepare._check_simulation_prepared",
        lambda _sid: (True, {"status": "ready"}),
    )

    response = client.post("/api/simulation/prepare/status", json={"simulation_id": VALID_SIM_ID})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "ready"
    assert data["message"] == "Preparation already completed"
    assert data["message_key"] == "prepare.already_completed"


def test_status_not_started_carries_message_key(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.simulation_prepare._check_simulation_prepared",
        lambda _sid: (False, {}),
    )

    response = client.post("/api/simulation/prepare/status", json={"simulation_id": VALID_SIM_ID})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "not_started"
    assert data["message"] == "Preparation not started yet, please call /api/simulation/prepare"
    assert data["message_key"] == "prepare.not_started"


def test_status_task_not_found_but_prepared_carries_message_key(client, monkeypatch):
    """Stale task_id (z. B. nach Serverneustart) — der Prepare-Zustand entscheidet."""
    calls = {"n": 0}

    def fake_check(_sid):
        # Erster Aufruf (vor dem Task-Lookup) liefert nicht vorbereitet, damit
        # der Endpoint bis zum Task-Zweig durchlaeuft; der zweite (nach dem
        # gescheiterten Task-Lookup) meldet den Kurzschluss dieses Tests.
        calls["n"] += 1
        return (calls["n"] > 1, {"status": "ready"})

    monkeypatch.setattr("app.api.simulation_prepare._check_simulation_prepared", fake_check)

    fake_task_manager = MagicMock()
    fake_task_manager.get_task.return_value = None
    monkeypatch.setattr(
        "app.models.task.TaskManager", lambda: fake_task_manager
    )

    response = client.post(
        "/api/simulation/prepare/status",
        json={"task_id": VALID_TASK_ID, "simulation_id": VALID_SIM_ID},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["task_id"] == VALID_TASK_ID
    assert data["message"] == "Task complete (PrepareWork already exists)"
    assert data["message_key"] == "prepare.already_completed"
