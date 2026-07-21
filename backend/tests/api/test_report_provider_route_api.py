"""API-Contract: POST /api/report/generate akzeptiert eine explizite AiModelRef
und lehnt widersprüchliche explizite Eingaben ab (Issue #817).

Die Konflikt-Prüfungen greifen vor ``start_generation`` — daher ohne
Storage-/Routing-Stubs testbar. Der Forward-Test patcht ``start_generation``
und prüft nur, dass die AiModelRef unverändert durchgereicht wird.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import report_bp

VALID_SIM_ID = "sim_0123456789ab"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["TESTING"] = True
    app.config["AGORA_REPORT_RATE_LIMIT_MAX"] = 100
    app.config["AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.register_blueprint(report_bp, url_prefix="/api/report")
    with app.app_context():
        yield app.test_client()


def _ref_body(**extra):
    body = {
        "simulation_id": VALID_SIM_ID,
        "ai_model_ref": {
            "provider_connection_id": "conn-minimax",
            "model_id": "MiniMax-M3",
            "source": "explicit",
        },
    }
    body.update(extra)
    return body


def test_ai_model_ref_conflicts_with_llm_profile_id_returns_400(client):
    resp = client.post("/api/report/generate", json=_ref_body(llm_profile_id="prof-x"))
    assert resp.status_code == 400
    assert b"ai_model_ref" in resp.data


def test_ai_model_ref_conflicts_with_llm_model_returns_400(client):
    resp = client.post("/api/report/generate", json=_ref_body(llm_model="gemini-1.5-pro"))
    assert resp.status_code == 400


def test_invalid_ai_model_ref_returns_400(client):
    resp = client.post(
        "/api/report/generate",
        json={"simulation_id": VALID_SIM_ID, "ai_model_ref": {"model_id": "x"}},
    )
    assert resp.status_code == 400


def test_valid_ai_model_ref_is_forwarded_to_start_generation(client):
    fake = MagicMock(return_value={"status": "generating", "report_id": "report_x"})
    with patch("app.api.report.ReportGenerationService.start_generation", fake):
        resp = client.post("/api/report/generate", json=_ref_body())
    assert resp.status_code == 200
    forwarded = fake.call_args.kwargs["ai_model_ref"]
    assert forwarded is not None
    assert forwarded.provider_connection_id == "conn-minimax"
    assert forwarded.model_id == "MiniMax-M3"
    # Legacy-Felder werden bei expliziter AiModelRef nicht mitgeschickt.
    assert fake.call_args.kwargs["llm_profile_id"] is None
    assert fake.call_args.kwargs["llm_model_override"] is None


def test_connection_model_mismatch_returns_400(client):
    """Issue #819: das strikte Katalog-ValueError aus dem Service-Layer
    (Connection/Model-Mismatch) wird am Endpunkt zu HTTP 400 mit verständlicher
    Meldung — bestehendes ``except ValueError``-Handling in report.py, kein
    neuer Error-Pfad."""
    fake = MagicMock(
        side_effect=ValueError(
            "Modell 'MiniMax-M3' gehört nicht zur ProviderConnection 'conn-minimax'"
        )
    )
    with patch("app.api.report.ReportGenerationService.start_generation", fake):
        resp = client.post("/api/report/generate", json=_ref_body())
    assert resp.status_code == 400
    error_message = resp.get_json()["error"]
    assert "conn-minimax" in error_message
    assert "MiniMax-M3" in error_message
    assert "gehört nicht zur" in error_message


def test_connection_model_discovery_failure_returns_400_distinct_message(client):
    """Ein Discovery-Fehlschlag (Provider nicht erreichbar/ungültige
    Credentials) wird ebenfalls zu HTTP 400, aber mit einer von einem echten
    Model-Mismatch unterscheidbaren Meldung."""
    fake = MagicMock(
        side_effect=ValueError(
            "Modell-Katalog für ProviderConnection 'conn-minimax' derzeit "
            "nicht abrufbar (invalid_credentials): Anmeldung abgelehnt"
        )
    )
    with patch("app.api.report.ReportGenerationService.start_generation", fake):
        resp = client.post("/api/report/generate", json=_ref_body())
    assert resp.status_code == 400
    error_message = resp.get_json()["error"]
    assert "nicht abrufbar" in error_message
    assert "invalid_credentials" in error_message
    assert "gehört nicht zur" not in error_message
