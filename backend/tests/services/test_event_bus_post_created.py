"""Tests für emit_post_created auf InMemoryEventBus.

Layer 1 — event_bus-Erweiterung. Verifiziert:
1. emit_post_created publishes auf den korrekten Channel.
2. Der Channel-Name enthält die simulation_id.
3. Die empfangene SimulationEvent-Payload enthält event_type='post_created'.
4. Unbekanntes platform-Feld wird von PostCreatedEvent rejected (Pydantic-Guard).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.post_event_contract import (
    Platform,
    PostCreatedEvent,
    VoiceRegister,
)
from app.services.event_bus import (
    CHANNEL_POST_CREATED,
    InMemoryEventBus,
    SimulationEvent,
)


def _make_event(simulation_id: str = "sim-test") -> PostCreatedEvent:
    return PostCreatedEvent(
        simulation_id=simulation_id,
        post_id="post-001",
        parent_post_id=None,
        platform=Platform.REDDIT,
        persona_id="persona-42",
        persona_name="Mara Lindner",
        voice_register=VoiceRegister.NEUTRAL_DE,
        is_simulated=True,
        body="Hallo Welt.",
        timestamp=datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
    )


class TestInMemoryEventBusEmitPostCreated:
    def test_emit_publishes_to_post_created_channel(self) -> None:
        bus = InMemoryEventBus()
        sim_id = "sim-xyz"
        event = _make_event(sim_id)

        # Arm subscriber before publish
        received: list[SimulationEvent] = []
        import threading
        def drain():
            for ev in bus.subscribe(sim_id, CHANNEL_POST_CREATED, timeout=2.0):
                received.append(ev)

        t = threading.Thread(target=drain, daemon=True)
        t.start()

        import time
        time.sleep(0.05)  # brief pause so subscriber registers cursor

        bus.emit_post_created(event)
        t.join(timeout=3.0)

        assert len(received) == 1
        assert received[0].type == "post_created"
        assert received[0].simulation_id == sim_id

    def test_channel_name_is_post_created(self) -> None:
        assert CHANNEL_POST_CREATED == "post_created"

    def test_payload_contains_post_id(self) -> None:
        bus = InMemoryEventBus()
        sim_id = "sim-abc"
        event = _make_event(sim_id)

        received: list[SimulationEvent] = []
        import threading
        def drain():
            for ev in bus.subscribe(sim_id, CHANNEL_POST_CREATED, timeout=2.0):
                received.append(ev)

        t = threading.Thread(target=drain, daemon=True)
        t.start()

        import time
        time.sleep(0.05)

        bus.emit_post_created(event)
        t.join(timeout=3.0)

        assert received[0].payload["post_id"] == "post-001"
        assert received[0].payload["platform"] == "reddit"
        assert received[0].payload["persona_id"] == "persona-42"

    def test_invalid_post_event_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            PostCreatedEvent(
                simulation_id="sim-x",
                post_id="p1",
                platform="mastodon",  # type: ignore[arg-type]
                persona_id="pid",
                persona_name="Test Persona",
                voice_register="neutral-de",  # type: ignore[arg-type]
                body="x",
                timestamp=datetime.now(tz=timezone.utc),
            )
