"""Tests: SSE-Endpoints senden 'retry:'-Frame als ersten Frame (Sub-Slice J.5, #223).

Beide SSE-Endpoints müssen dem Browser mitteilen, mit welchem Intervall er
bei einem Verbindungsabbruch wieder verbinden soll — ansonsten nutzt der
Browser seinen internen Default (~3 s, unsteuerbar vom Backend).

Getestet wird:
  1. simulation_stream: _stream() als Generator (kein HTTP, unit-level)
  2. logs/stream: stream_logs() via Flask-Test-Client (Integration)
"""

from __future__ import annotations

import pytest
from flask import Blueprint, Flask

from app.api import simulation_bp
from app.api.logs import stream_logs, get_logs
from app.services.event_bus import InMemoryEventBus
from app.utils.auth import install_blueprint_guard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_simulation_app() -> Flask:
    app = Flask(__name__)
    app.extensions = {}
    app.extensions["event_bus"] = InMemoryEventBus()
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app


@pytest.fixture(scope="module")
def logs_app():
    app = Flask(__name__)
    bp = Blueprint("logs_retry_test", __name__)
    bp.add_url_rule("", view_func=get_logs, methods=["GET"])
    bp.add_url_rule("/", view_func=get_logs, methods=["GET"])
    bp.add_url_rule("/stream", view_func=stream_logs, methods=["GET"])
    install_blueprint_guard(bp)
    app.register_blueprint(bp, url_prefix="/api/logs")
    return app


@pytest.fixture
def logs_client(logs_app, tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.logs.LOG_DIR", str(tmp_path))
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    return logs_app.test_client()


# ---------------------------------------------------------------------------
# simulation_stream — unit-level Generator-Test
# ---------------------------------------------------------------------------


def test_simulation_stream_sets_retry_field():
    """_stream() muss 'retry: 5000' als allererstes Frame emittieren.

    Wir rufen den Generator direkt auf (kein HTTP), um Deadlock-Risiken durch
    endlose while-True-Schleifen zu umgehen. next() liefert das erste Frame.
    """
    app = _build_simulation_app()
    sim_id = "sim_abcdef012345"

    with app.app_context():
        from app.api.simulation_stream import _stream

        gen = _stream(sim_id)
        first_frame = next(gen)

    assert "retry:" in first_frame, (
        f"Erstes Frame enthält kein 'retry:'-Feld: {first_frame!r}"
    )
    assert "retry: 5000" in first_frame, (
        f"retry-Wert ist nicht 5000 ms: {first_frame!r}"
    )


def test_simulation_stream_retry_before_hello():
    """retry-Frame muss VOR dem hello-Frame kommen."""
    app = _build_simulation_app()
    sim_id = "sim_abcdef012345"

    with app.app_context():
        from app.api.simulation_stream import _stream

        gen = _stream(sim_id)
        first_frame = next(gen)
        second_frame = next(gen)

    assert "retry:" in first_frame, (
        f"Erstes Frame ist nicht das retry-Frame: {first_frame!r}"
    )
    assert "event: hello" in second_frame, (
        f"Zweites Frame ist nicht das hello-Frame: {second_frame!r}"
    )


# ---------------------------------------------------------------------------
# logs/stream — Integration-Test (HTTP + iter_encoded)
# ---------------------------------------------------------------------------


def test_logs_stream_sets_retry_field(logs_client, tmp_path, monkeypatch):
    """GET /api/logs/stream: erstes Generator-Frame muss 'retry: 5000' sein.

    Der Flask-Response-Iterator liefert Frames 1:1 aus dem Generator — das
    erste Item muss exakt das retry-Frame sein, bevor irgendwelche data- oder
    heartbeat-Frames kommen.
    """
    # Kein Auth-Token gesetzt → Guard ist No-Op.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)

    response = logs_client.get("/api/logs/stream", buffered=False)
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"

    # Erstes Item aus dem Response-Iterator holen; danach schließen.
    first_item: str | None = None
    for raw in response.response:
        first_item = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        break
    response.close()

    assert first_item is not None, "Stream lieferte kein einziges Frame"
    assert "retry:" in first_item, (
        f"Erstes Frame enthält kein 'retry:'-Feld: {first_item!r}"
    )
    assert "retry: 5000" in first_item, (
        f"retry-Wert ist nicht 5000 ms im ersten Frame: {first_item!r}"
    )
    # Sicherstellen, dass das retry-Frame kein data:-Frame ist (Reihenfolge).
    assert "data:" not in first_item, (
        f"Erstes Frame ist kein reines retry-Frame (enthält data:): {first_item!r}"
    )
