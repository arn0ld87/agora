"""Integration tests for :class:`RedisEventBus` (Issue #9 Phase B).

Requires a reachable Redis server. Tests are skipped automatically when
``REDIS_URL`` is unset or the server does not respond to PING within
half a second, so the suite stays green in CI without Redis.

Set ``TEST_REDIS_URL`` (or ``REDIS_URL``) to enable locally, e.g.::

    TEST_REDIS_URL=redis://localhost:6379/15 uv run pytest tests/test_event_bus_redis.py
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import List

import pytest

pytest.importorskip("redis")  # noqa: E402
import redis  # noqa: E402

from app.services.artifact_store import LocalFilesystemArtifactStore  # noqa: E402
from app.services.event_bus import (  # noqa: E402
    CHANNEL_CONTROL,
    CHANNEL_STATE,
    SimulationEvent,
)
from app.services.event_bus_redis import (  # noqa: E402
    RedisEventBus,
    _channel_key,
    is_redis_reachable,
)


TEST_URL = (
    os.environ.get("TEST_REDIS_URL")
    or os.environ.get("REDIS_URL")
    or "redis://localhost:6379/15"
)

if not is_redis_reachable(TEST_URL, timeout=0.5):
    pytest.skip(
        f"Redis not reachable at {TEST_URL}; set TEST_REDIS_URL to enable Phase B integration tests.",
        allow_module_level=True,
    )


SIM_ID = "sim_redis_bus_test"


@pytest.fixture
def redis_client():
    client = redis.from_url(TEST_URL, decode_responses=True)
    # Scope cleanup to our test namespace — never touch the caller's data.
    for key in client.scan_iter(f"agora:sim:{SIM_ID}:*"):
        client.delete(key)
    yield client
    for key in client.scan_iter(f"agora:sim:{SIM_ID}:*"):
        client.delete(key)
    client.close()


@pytest.fixture
def bus(tmp_path, redis_client):
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    bus = RedisEventBus(TEST_URL, artifact_store=store)
    yield bus
    bus.close()


# ---------------------------------------------------------------------------
# Pub/Sub: control channel round-trip
# ---------------------------------------------------------------------------


def test_control_publish_reaches_live_subscriber(bus):
    received: List[SimulationEvent] = []
    ready = threading.Event()

    def consume() -> None:
        ready.set()
        for event in bus.subscribe(
            SIM_ID, CHANNEL_CONTROL, timeout=2.0, poll_interval=0.05
        ):
            received.append(event)
            if event.payload.get("paused") is True:
                return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    ready.wait()
    # Give the subscriber time to issue SUBSCRIBE on the Redis connection.
    time.sleep(0.15)

    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"paused": True},
        ),
    )
    t.join(timeout=2.5)

    assert any(e.payload.get("paused") is True for e in received), (
        f"Subscriber did not receive pause event (saw: {[e.payload for e in received]})"
    )


def test_control_publish_mirrors_to_artifact_store(bus, tmp_path):
    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"stop_requested": True},
        ),
    )
    snapshot_path = tmp_path / SIM_ID / "control_state.json"
    # Give the mirror write a moment in case of async I/O under load.
    for _ in range(10):
        if snapshot_path.exists():
            break
        time.sleep(0.05)
    assert snapshot_path.exists(), "control_state.json was not mirrored"
    data = json.loads(snapshot_path.read_text())
    assert data["stop_requested"] is True


# ---------------------------------------------------------------------------
# State channel: live subscriber sees updates
# ---------------------------------------------------------------------------


def test_state_publish_reaches_live_subscriber(bus):
    received: List[SimulationEvent] = []
    ready = threading.Event()

    def consume() -> None:
        ready.set()
        for event in bus.subscribe(
            SIM_ID, CHANNEL_STATE, timeout=2.0, poll_interval=0.05
        ):
            received.append(event)
            if event.payload.get("current_round") == 7:
                return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    ready.wait()
    time.sleep(0.15)

    bus.publish(
        CHANNEL_STATE,
        SimulationEvent(
            type="state.update",
            simulation_id=SIM_ID,
            payload={"current_round": 7, "updated_at": "2026-04-23T12:00:00"},
        ),
    )
    t.join(timeout=2.5)

    assert any(e.payload.get("current_round") == 7 for e in received)


# ---------------------------------------------------------------------------
# Retained snapshot yielded to late subscribers
# ---------------------------------------------------------------------------


def test_late_subscriber_sees_retained_control(bus):
    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"paused": True},
        ),
    )
    # Subscribe *after* the publish — pub/sub alone would drop the event,
    # but the adapter yields the retained snapshot from the store first.
    received: List[SimulationEvent] = []
    for event in bus.subscribe(SIM_ID, CHANNEL_CONTROL, timeout=0.3, poll_interval=0.05):
        received.append(event)
        if event.payload.get("paused") is True:
            break

    assert received and received[0].payload.get("paused") is True


# ---------------------------------------------------------------------------
# Isolation: channels are namespaced per simulation
# ---------------------------------------------------------------------------


def test_redis_channel_key_is_per_simulation():
    assert _channel_key("sim_a", "control") == "agora:sim:sim_a:control"
    assert _channel_key("sim_b", "control") == "agora:sim:sim_b:control"


# ---------------------------------------------------------------------------
# RPC channel delegates to the file bus
# ---------------------------------------------------------------------------


def test_rpc_request_response_goes_through_file_bus(bus):
    from app.services.event_bus import CHANNEL_RPC_COMMAND, rpc_response_channel

    # A responder thread consumes the command via the file adapter inside
    # the Redis bus (Phase B keeps RPC on files until subprocess migrates).
    def responder() -> None:
        for cmd in bus._file_bus.subscribe(  # noqa: SLF001
            SIM_ID, CHANNEL_RPC_COMMAND, timeout=2.0, poll_interval=0.05
        ):
            bus._file_bus.publish(  # noqa: SLF001
                rpc_response_channel(cmd.correlation_id),
                SimulationEvent(
                    type="rpc.response.completed",
                    simulation_id=SIM_ID,
                    payload={"status": "completed", "result": {"ok": True}},
                    correlation_id=cmd.correlation_id,
                ),
            )
            return

    t = threading.Thread(target=responder, daemon=True)
    t.start()

    response = bus.request_response(
        SIM_ID,
        command_type="interview",
        args={"agent_id": 1, "prompt": "ping"},
        timeout=2.0,
        poll_interval=0.05,
    )
    t.join(timeout=3.0)

    assert response.payload["status"] == "completed"
