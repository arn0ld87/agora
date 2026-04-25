"""Integration tests for RedisIPCBridge (Issue #17 Phase D).

These tests stand in for the OASIS subprocess: they instantiate the
Backend-side :class:`RedisEventBus` and the Subprocess-side
:class:`RedisIPCBridge` against a real Redis, then verify that an RPC
round-trip flows entirely over Redis Pub/Sub — same protocol the
deployed setup will use after the cutover.

Skip the module when Redis is not reachable (mirrors test_event_bus_redis).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from typing import Any, Dict, List

import pytest

pytest.importorskip("redis")
pytest.importorskip("redis.asyncio")
import redis  # noqa: E402

from app.services.artifact_store import LocalFilesystemArtifactStore  # noqa: E402
from app.services.event_bus import SimulationEvent  # noqa: E402
from app.services.event_bus_redis import (  # noqa: E402
    RedisEventBus,
    is_redis_reachable,
)


_SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scripts")
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from subprocess_redis_bridge import RedisIPCBridge, channel_key  # noqa: E402


TEST_URL = (
    os.environ.get("TEST_REDIS_URL")
    or os.environ.get("REDIS_URL")
    or "redis://localhost:6379/15"
)

if not is_redis_reachable(TEST_URL, timeout=0.5):
    pytest.skip(
        f"Redis not reachable at {TEST_URL}; "
        f"set TEST_REDIS_URL to enable bridge integration tests.",
        allow_module_level=True,
    )


SIM_ID = "sim_bridge_integration"


@pytest.fixture
def redis_client():
    client = redis.from_url(TEST_URL, decode_responses=True)
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


@pytest.mark.asyncio
async def test_bridge_receives_redis_command_and_answers_via_redis(
    bus, redis_client
):
    """End-to-end hybrid round-trip with no OASIS process involved.

    Backend.request_response → publishes on Redis (and File). Bridge
    listener receives the command, the on_command callback answers via
    publish_response on Redis. Backend's hybrid waiter consumes the
    Redis response, never touching the file artifact.
    """
    received: List[Dict[str, Any]] = []

    async def on_command(event: Dict[str, Any]) -> None:
        received.append(event)
        await bridge.publish_response(
            event["correlation_id"],
            {
                "type": "rpc.response.completed",
                "simulation_id": SIM_ID,
                "payload": {
                    "status": "completed",
                    "result": {"answer": "via-bridge"},
                },
                "correlation_id": event["correlation_id"],
            },
        )

    bridge = RedisIPCBridge(
        simulation_id=SIM_ID,
        redis_url=TEST_URL,
        on_command=on_command,
    )
    started = await bridge.start()
    assert started, "Bridge failed to attach to Redis"

    try:
        loop = asyncio.get_running_loop()

        # Backend.request_response is synchronous and blocks. Run it in a
        # worker thread so the bridge listener can fire on this loop.
        def _call_request_response() -> SimulationEvent:
            return bus.request_response(
                SIM_ID,
                command_type="interview",
                args={"agent_id": 42, "prompt": "ping"},
                timeout=3.0,
                poll_interval=0.05,
            )

        response = await loop.run_in_executor(None, _call_request_response)
    finally:
        await bridge.stop()

    assert response.payload["status"] == "completed"
    assert response.payload["result"]["answer"] == "via-bridge"
    assert len(received) == 1
    assert received[0]["correlation_id"] == response.correlation_id


@pytest.mark.asyncio
async def test_bridge_disabled_without_redis_url():
    """Bridge stays inactive when REDIS_URL is unset — no exception, no work."""

    async def on_command(_event: Dict[str, Any]) -> None:
        raise AssertionError("on_command must not fire when bridge is disabled")

    bridge = RedisIPCBridge(
        simulation_id=SIM_ID,
        redis_url=None,
        on_command=on_command,
    )
    started = await bridge.start()
    assert started is False
    assert bridge.active is False
    # publish_response is a no-op when inactive
    ok = await bridge.publish_response("ignored", {"foo": "bar"})
    assert ok is False
    await bridge.stop()  # must not raise


@pytest.mark.asyncio
async def test_bridge_publish_response_reaches_raw_subscriber(redis_client):
    """publish_response writes to agora:sim:<id>:rpc.response.<cid> on Redis."""
    bridge = RedisIPCBridge(
        simulation_id=SIM_ID,
        redis_url=TEST_URL,
        on_command=lambda _e: asyncio.sleep(0),
    )
    started = await bridge.start()
    assert started

    received: List[Dict[str, Any]] = []
    ready = threading.Event()

    def consume() -> None:
        client = redis.from_url(TEST_URL, decode_responses=True)
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        key = channel_key(SIM_ID, "rpc.response.cid-publish-test")
        pubsub.subscribe(key)
        ready.set()
        for _ in range(40):
            msg = pubsub.get_message(timeout=0.1)
            if msg and msg.get("type") == "message":
                received.append(json.loads(msg["data"]))
                break
        pubsub.unsubscribe(key)
        pubsub.close()
        client.close()

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    ready.wait()
    await asyncio.sleep(0.1)

    try:
        ok = await bridge.publish_response(
            "cid-publish-test",
            {"status": "completed", "result": {"ok": True}},
        )
        assert ok is True
        # Give the consumer thread a moment to read the message.
        await asyncio.sleep(0.2)
    finally:
        await bridge.stop()

    t.join(timeout=2.0)
    assert received, "raw Redis subscriber did not see publish_response"
    assert received[0]["result"]["ok"] is True
