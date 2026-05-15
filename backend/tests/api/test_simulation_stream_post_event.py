"""SSE-Smoke: PostCreatedEvent geht via InMemoryEventBus als SSE-Frame durch.

Testet:
1. _stream() emittiert einen ``event: post_created``-Frame wenn ein
   PostCreatedEvent über den Bus gepublisht wird.
2. Der Frame enthält post_id, platform, persona_id.
3. Bestehende state/control-Events werden nicht gebrochen (Regressions-Smoke).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from flask import Flask

from app.api import simulation_bp
from app.contracts.post_event_contract import (
    Platform,
    PostCreatedEvent,
    VoiceRegister,
)
from app.services.event_bus import InMemoryEventBus


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _build_app(bus: InMemoryEventBus) -> Flask:
    app = Flask(__name__)
    app.extensions = {}
    app.extensions["event_bus"] = bus
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse_frames(raw: bytes) -> list[dict]:
    """Parse raw SSE bytes into list of {event, data} dicts."""
    frames = []
    current: dict = {}
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:"):].strip()
        elif line == "" and current:
            frames.append(current)
            current = {}
    if current:
        frames.append(current)
    return frames


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSimulationStreamPostCreated:
    def test_post_created_frame_emitted(self) -> None:
        """SSE stream emits an ``event: post_created`` frame for PostCreatedEvent."""
        bus = InMemoryEventBus()
        app = _build_app(bus)
        sim_id = "sim-stream-001"

        event = PostCreatedEvent(
            simulation_id=sim_id,
            post_id="post-sse-1",
            parent_post_id=None,
            platform=Platform.REDDIT,
            persona_id="persona-99",
            voice_register=VoiceRegister.CASUAL,
            is_simulated=True,
            body="SSE-Testpost.",
            timestamp=datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc),
        )

        frames: list[str] = []

        def collect():
            with app.app_context():
                from app.api.simulation_stream import _stream

                gen = _stream(sim_id)
                # skip retry + hello frames
                next(gen)  # retry:
                next(gen)  # hello
                # publish post event, then collect next frame
                bus.emit_post_created(event)
                try:
                    frame = next(gen)
                    frames.append(frame)
                except StopIteration:
                    pass

        t = threading.Thread(target=collect, daemon=True)
        t.start()
        t.join(timeout=5.0)

        assert frames, "No frame received from _stream() after emit_post_created"
        frame = frames[0]
        assert "event: post_created" in frame, f"Expected 'event: post_created' in frame: {frame!r}"

        # Extract JSON data from frame
        data_line = next(
            (ln for ln in frame.splitlines() if ln.startswith("data:")), None
        )
        assert data_line is not None, f"No data: line in frame: {frame!r}"
        data = json.loads(data_line[len("data:"):].strip())
        assert data["payload"]["post_id"] == "post-sse-1"
        assert data["payload"]["platform"] == "reddit"
        assert data["payload"]["persona_id"] == "persona-99"

    def test_existing_channels_not_broken(self) -> None:
        """Subscribing to state/control still works after post_created channel added."""
        bus = InMemoryEventBus()
        app = _build_app(bus)
        sim_id = "sim-stream-002"

        with app.app_context():
            from app.api.simulation_stream import _stream

            gen = _stream(sim_id)
            retry_frame = next(gen)
            hello_frame = next(gen)

        assert "retry:" in retry_frame
        assert "event: hello" in hello_frame
