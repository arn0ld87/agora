"""Slice-Welle-Hotfix 2026-05-16: RedisEventBus.subscribe für CHANNEL_POST_CREATED.

User-Bericht nach Container-Smoke: Stream-Drainer crashed mit
``ValueError: Unknown channel for RedisEventBus: 'post_created'`` weil
die Channel-Allowlist nur CONTROL/STATE enthielt. OASIS-Subprozess
publisht aber direkt nach ``agora:sim:{id}:post_created`` via Redis
(scripts/run_parallel_simulation.py::_emit_post_created_to_redis).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.event_bus import CHANNEL_POST_CREATED
from app.services.event_bus_redis import RedisEventBus


@pytest.fixture()
def bus():
    with patch("redis.from_url") as mock_from_url:
        client = MagicMock()
        client.ping.return_value = True
        mock_from_url.return_value = client
        b = RedisEventBus("redis://test:6379/0", ping_on_init=False)
    return b


def test_subscribe_accepts_post_created_channel(bus):
    """post_created darf KEIN ValueError mehr werfen (Hotfix)."""
    # Mock pubsub so subscribe() läuft an, gibt aber sofort timeout zurück
    pubsub = MagicMock()
    pubsub.get_message.return_value = None
    bus._redis.pubsub.return_value = pubsub

    # Snapshot-Read muss übersprungen werden für post_created — sonst würde
    # _store.read_json gegen 'run_state' fallen und ein falscher Update-Event
    # an den Drainer durchgereicht werden.
    bus._store = MagicMock()
    bus._store.read_json.return_value = None

    gen = bus.subscribe("sim_test", CHANNEL_POST_CREATED, timeout=0.01, poll_interval=0.005)
    events = list(gen)

    # Kein Event (kein Snapshot, keine Live-Messages) — aber wichtig: KEIN Raise.
    assert events == []
    # Verify: subscribe hat den richtigen Redis-Channel-Key abonniert
    pubsub.subscribe.assert_called_once_with("agora:sim:sim_test:post_created")


def test_subscribe_skips_snapshot_read_for_post_created(bus):
    """_subscribe_live darf für post_created nicht run_state als Snapshot rausreichen."""
    pubsub = MagicMock()
    pubsub.get_message.return_value = None
    bus._redis.pubsub.return_value = pubsub

    bus._store = MagicMock()
    # Würde der Snapshot-Pfad NICHT überspringen, würde read_json hier
    # mit 'run_state' aufgerufen und ein Dummy-Event durchsickern.
    bus._store.read_json.return_value = {"updated_at": "x", "foo": "bar"}

    gen = bus.subscribe("sim_test", CHANNEL_POST_CREATED, timeout=0.01, poll_interval=0.005)
    events = list(gen)

    assert events == []
    # Snapshot-Read wurde übersprungen — read_json darf gar nicht aufgerufen
    # worden sein (Pfad ist guarded by ``if channel != CHANNEL_POST_CREATED``).
    bus._store.read_json.assert_not_called()


def test_subscribe_still_rejects_truly_unknown_channels(bus):
    """Allowlist ist erweitert, nicht entfernt — Garbage-Channels bleiben hart abgelehnt."""
    with pytest.raises(ValueError, match="Unknown channel"):
        list(bus.subscribe("sim_test", "totally_made_up_channel", timeout=0.01))


def test_subscribe_parses_oasis_wire_format_for_post_created(bus):
    """Wire-Format-Brücke (Gemini-Finding #1, HIGH).

    OASIS-Subprozess (run_parallel_simulation.py::_emit_post_created_to_redis)
    publisht ein FLACHES Payload mit ``event_type`` statt eines
    SimulationEvent-Envelopes (``type``/``payload``). Ohne Brücke fliegt
    jedes post_created als KeyError im ``except KeyError`` → Event wird
    gedroppt → Frontend bleibt leer. Test asseritert dass die Brücke greift.
    """
    import json as _json

    oasis_payload = {
        "event_type": "post_created",
        "simulation_id": "sim_88b6a65f7bb0",
        "post_id": "post-42",
        "parent_post_id": None,
        "platform": "twitter",
        "persona_id": "agent-5",
        "voice_register": "casual",
        "is_simulated": True,
        "body": "Hallo Welt",
        "timestamp": "2026-05-16T17:25:28+00:00",
        "sentiment": None,
        "score": 0,
    }

    pubsub = MagicMock()
    # Erstes get_message gibt ein echtes message-Frame zurück, danach
    # endlos None — verhindert StopIteration im Generator, Timeout kappt
    # die Loop nach 50 ms ab.
    _messages = iter([{"type": "message", "data": _json.dumps(oasis_payload)}])

    def _get_message(*_args, **_kwargs):
        return next(_messages, None)

    pubsub.get_message.side_effect = _get_message
    bus._redis.pubsub.return_value = pubsub
    bus._store = MagicMock()
    bus._store.read_json.return_value = None  # kein snapshot

    gen = bus.subscribe("sim_88b6a65f7bb0", CHANNEL_POST_CREATED, timeout=0.05, poll_interval=0.005)
    events = list(gen)

    assert len(events) == 1, f"erwarte genau 1 Event, bekam {len(events)}"
    evt = events[0]
    assert evt.type == "post_created"
    assert evt.simulation_id == "sim_88b6a65f7bb0"
    assert evt.payload["post_id"] == "post-42"
    assert evt.payload["body"] == "Hallo Welt"
