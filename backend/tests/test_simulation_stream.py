"""SSE simulation stream route tests (Issue #9 Phase C).

The route streams events coming off the :class:`SimulationEventBus`. Tests
inject an :class:`InMemoryEventBus`, publish control/state events from a
background thread, and assert that the stream emits matching SSE frames.
"""

from __future__ import annotations

import json
import re
import threading
import time

from flask import Flask

from app.api import simulation_bp
from app.services.event_bus import (
    CHANNEL_CONTROL,
    CHANNEL_STATE,
    InMemoryEventBus,
    SimulationEvent,
)


def _build_test_app() -> Flask:
    app = Flask(__name__)
    app.extensions = {}
    app.extensions["event_bus"] = InMemoryEventBus()
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app


def test_stream_rejects_invalid_simulation_id():
    app = _build_test_app()
    client = app.test_client()

    response = client.get("/api/simulation/not a sim/stream")

    assert response.status_code in (200, 400)
    # Route returns a JSON error envelope for bad IDs.
    if response.status_code == 200:
        body = response.get_json()
        assert body["success"] is False


def test_stream_emits_hello_and_control_events():
    app = _build_test_app()
    bus: InMemoryEventBus = app.extensions["event_bus"]
    sim_id = "sim_abcdef012345"

    # Publish a control event shortly after the client connects so the
    # generator observes it and emits an SSE frame.
    def publish_after_connect() -> None:
        time.sleep(0.3)
        bus.publish(
            CHANNEL_CONTROL,
            SimulationEvent(
                type="control.update",
                simulation_id=sim_id,
                payload={"paused": True},
            ),
        )
        bus.publish(
            CHANNEL_STATE,
            SimulationEvent(
                type="state.update",
                simulation_id=sim_id,
                payload={"runner_status": "running", "current_round": 3},
            ),
        )

    t = threading.Thread(target=publish_after_connect, daemon=True)
    t.start()

    client = app.test_client()
    # buffered=False + iter_encoded lets us consume streaming output.
    response = client.get(f"/api/simulation/{sim_id}/stream", buffered=False)
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"

    chunks: list[str] = []
    deadline = time.monotonic() + 3.0
    seen_control = False
    seen_state = False
    for raw in response.response:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        chunks.append(raw)
        if "event: control" in raw:
            seen_control = True
        if "event: state" in raw:
            seen_state = True
        if seen_control and seen_state:
            break
        if time.monotonic() >= deadline:
            break
    response.close()
    t.join(timeout=1.0)

    blob = "".join(chunks)
    # First frame is always the `hello` message.
    assert "event: hello" in blob, f"No hello frame (got: {blob[:400]!r})"
    assert seen_control, f"No control frame observed (got: {blob[:800]!r})"
    assert seen_state, f"No state frame observed (got: {blob[:800]!r})"

    # Decode the data payload of the control frame and sanity-check shape.
    match = re.search(r"event: control\nid: .*?\ndata: (\{.*?\})\n", blob)
    assert match, "Could not parse control data line"
    data = json.loads(match.group(1))
    assert data["simulation_id"] == sim_id
    assert data["payload"]["paused"] is True
