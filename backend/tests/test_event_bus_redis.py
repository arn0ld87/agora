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


# ---------------------------------------------------------------------------
# Issue #17 — RPC migration spec (xfail until Phase 3 lands)
#
# These tests describe the post-migration behaviour: backend publishes RPC
# commands on Redis Pub/Sub, subscribes to RPC responses on Redis Pub/Sub,
# and falls back to the legacy file IPC layer only when Redis stays silent.
#
# All four are marked ``xfail(strict=True)`` so the suite stays green while
# Phase 1 only ships the spec. Phase 3 flips the implementation; the
# strict-xfail then turns those tests into XPASS-failures, which is the
# signal to remove the marker.
# ---------------------------------------------------------------------------


def _redis_subscribe_blocking(redis_url: str, key: str, timeout: float = 2.0):
    """Open a fresh raw-Redis pubsub, subscribe to ``key``, wait for one message."""
    client = redis.from_url(redis_url, decode_responses=True)
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(key)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            msg = pubsub.get_message(timeout=0.1)
            if msg and msg.get("type") == "message":
                return json.loads(msg["data"])
        return None
    finally:
        try:
            pubsub.unsubscribe(key)
            pubsub.close()
        except Exception:
            pass
        client.close()


@pytest.mark.xfail(
    strict=True,
    reason="Issue #17 Phase 3: backend publishes rpc.command via Redis Pub/Sub",
)
def test_rpc_command_publish_reaches_redis_subscriber(bus, redis_client):
    """Backend.publish(CHANNEL_RPC_COMMAND) must reach a raw-Redis subscriber.

    Phase B delegates to the file bus, so a Redis subscriber sees nothing.
    Phase 3 mirrors the publish to ``agora:sim:<id>:rpc.command`` so the
    OASIS subprocess listener can consume it without touching disk.
    """
    from app.services.event_bus import CHANNEL_RPC_COMMAND

    received: List[dict] = []
    ready = threading.Event()

    def consume() -> None:
        ready.set()
        msg = _redis_subscribe_blocking(
            TEST_URL, _channel_key(SIM_ID, CHANNEL_RPC_COMMAND), timeout=2.0
        )
        if msg is not None:
            received.append(msg)

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    ready.wait()
    time.sleep(0.15)  # let SUBSCRIBE settle on the consumer connection

    bus.publish(
        CHANNEL_RPC_COMMAND,
        SimulationEvent(
            type="interview",
            simulation_id=SIM_ID,
            payload={"agent_id": 1, "prompt": "ping"},
            correlation_id="cid-redis-cmd",
        ),
    )
    t.join(timeout=2.5)

    assert received, "Redis subscriber did not receive the rpc.command event"
    assert received[0]["correlation_id"] == "cid-redis-cmd"
    assert received[0]["payload"]["agent_id"] == 1


@pytest.mark.xfail(
    strict=True,
    reason="Issue #17 Phase 3: backend subscribes rpc.response.<cid> via Redis Pub/Sub",
)
def test_rpc_response_subscribe_consumes_redis_publish(bus, redis_client):
    """Backend.subscribe(rpc.response.<cid>) must yield events published on Redis."""
    from app.services.event_bus import rpc_response_channel

    correlation_id = "cid-redis-resp"
    response_channel = rpc_response_channel(correlation_id)
    response_key = _channel_key(SIM_ID, response_channel)

    received: List[SimulationEvent] = []
    ready = threading.Event()

    def consume() -> None:
        ready.set()
        for event in bus.subscribe(
            SIM_ID, response_channel, timeout=2.0, poll_interval=0.05
        ):
            received.append(event)
            return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    ready.wait()
    time.sleep(0.15)

    response_event = SimulationEvent(
        type="rpc.response.completed",
        simulation_id=SIM_ID,
        payload={"status": "completed", "result": {"ok": True}},
        correlation_id=correlation_id,
    )
    redis_client.publish(response_key, json.dumps(response_event.to_dict()))
    t.join(timeout=2.5)

    assert received, "Backend never received the response published on Redis"
    assert received[0].correlation_id == correlation_id
    assert received[0].payload["status"] == "completed"


@pytest.mark.xfail(
    strict=True,
    reason="Issue #17 Phase 3: request_response round-trips fully over Redis",
)
def test_request_response_redis_round_trip(bus, redis_client):
    """End-to-end: publish via Redis, mock subprocess answers via Redis, no file I/O."""
    from app.services.event_bus import CHANNEL_RPC_COMMAND

    cmd_key = _channel_key(SIM_ID, CHANNEL_RPC_COMMAND)
    responder_ready = threading.Event()

    def responder() -> None:
        client = redis.from_url(TEST_URL, decode_responses=True)
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(cmd_key)
        responder_ready.set()
        deadline = time.monotonic() + 3.0
        try:
            while time.monotonic() < deadline:
                msg = pubsub.get_message(timeout=0.1)
                if not msg or msg.get("type") != "message":
                    continue
                cmd = json.loads(msg["data"])
                cid = cmd["correlation_id"]
                resp = SimulationEvent(
                    type="rpc.response.completed",
                    simulation_id=SIM_ID,
                    payload={"status": "completed", "result": {"answer": "pong"}},
                    correlation_id=cid,
                )
                resp_key = _channel_key(SIM_ID, f"rpc.response.{cid}")
                # tiny delay so the backend is already subscribed
                time.sleep(0.1)
                client.publish(resp_key, json.dumps(resp.to_dict()))
                return
        finally:
            try:
                pubsub.unsubscribe(cmd_key)
                pubsub.close()
            except Exception:
                pass
            client.close()

    t = threading.Thread(target=responder, daemon=True)
    t.start()
    responder_ready.wait()
    time.sleep(0.15)

    response = bus.request_response(
        SIM_ID,
        command_type="interview",
        args={"agent_id": 7, "prompt": "ping"},
        timeout=3.0,
        poll_interval=0.05,
    )
    t.join(timeout=3.5)

    assert response.payload["status"] == "completed"
    assert response.payload["result"]["answer"] == "pong"


def test_request_response_falls_back_to_file_response(bus):
    """Legacy subprocess that only writes a file response must still work.

    During the rolling upgrade, an old subprocess version may answer only
    via the file IPC layer. This is the regression guard for Phase 3: when
    the new backend gains a Redis-first path, it MUST still pick up the
    file response if Redis stays silent. Today this works because the
    backend itself goes through the file bus; Phase 3 keeps it green.
    """
    from app.services.event_bus import CHANNEL_RPC_COMMAND, rpc_response_channel

    def file_only_responder() -> None:
        # Watch for the command on the file bus (mirrored by the new backend
        # publish) and answer only via files — no Redis publish at all.
        for cmd in bus._file_bus.subscribe(  # noqa: SLF001
            SIM_ID, CHANNEL_RPC_COMMAND, timeout=3.0, poll_interval=0.05
        ):
            bus._file_bus.publish(  # noqa: SLF001
                rpc_response_channel(cmd.correlation_id),
                SimulationEvent(
                    type="rpc.response.completed",
                    simulation_id=SIM_ID,
                    payload={"status": "completed", "result": {"via": "file"}},
                    correlation_id=cmd.correlation_id,
                ),
            )
            return

    t = threading.Thread(target=file_only_responder, daemon=True)
    t.start()

    response = bus.request_response(
        SIM_ID,
        command_type="interview",
        args={"agent_id": 2, "prompt": "legacy"},
        timeout=3.0,
        poll_interval=0.05,
    )
    t.join(timeout=3.5)

    assert response.payload["status"] == "completed"
    assert response.payload["result"]["via"] == "file"
