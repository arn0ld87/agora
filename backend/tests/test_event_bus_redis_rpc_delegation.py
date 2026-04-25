"""Phase-B contract: RPC must keep going through the file bus, not Redis.

Issue #17 (full migration) will flip this — and these tests should flip
red precisely when that work lands so we notice. They run without a real
Redis: we mock the redis client and watch which underlying bus the
RedisEventBus delegates to.

See ``docu/issue-17-rpc-redis-plan.md`` for the migration plan that
will replace these tests with end-to-end Redis round-trip coverage.
"""

from __future__ import annotations

from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("redis")

from app.services.event_bus import (
    CHANNEL_RPC_COMMAND,
    SimulationEvent,
    rpc_response_channel,
)
from app.services.event_bus_redis import RedisEventBus


SIM_ID = "sim_rpc_delegation"


def _mock_redis_client() -> MagicMock:
    client = MagicMock()
    client.ping.return_value = True
    pubsub = MagicMock()
    pubsub.get_message.return_value = None
    client.pubsub.return_value = pubsub
    return client


@pytest.fixture
def bus(tmp_path) -> RedisEventBus:
    """Build a RedisEventBus whose Redis client is fully mocked."""
    fake_client = _mock_redis_client()
    with patch("redis.from_url", return_value=fake_client):
        from app.services.artifact_store import LocalFilesystemArtifactStore

        store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
        bus = RedisEventBus("redis://mocked:6379/0", artifact_store=store)
    return bus


def test_rpc_publish_does_not_hit_redis(bus):
    """Publishing on rpc.command must delegate to the file bus, not Redis."""
    bus._file_bus.publish = MagicMock()  # type: ignore[method-assign]
    redis_publish = bus._redis.publish

    event = SimulationEvent(
        type="interview",
        simulation_id=SIM_ID,
        payload={"agent_id": 1, "prompt": "ping"},
        correlation_id="cid-123",
    )
    bus.publish(CHANNEL_RPC_COMMAND, event)

    bus._file_bus.publish.assert_called_once_with(CHANNEL_RPC_COMMAND, event)
    redis_publish.assert_not_called()


def test_rpc_response_subscribe_does_not_hit_redis(bus):
    """Subscribing to rpc.response.<cid> must use the file bus iterator."""

    def _file_iter(_sim, _channel, **_kwargs) -> Iterator[SimulationEvent]:
        yield SimulationEvent(
            type="interview.response",
            simulation_id=SIM_ID,
            payload={"answer": "pong"},
            correlation_id="cid-123",
        )

    bus._file_bus.subscribe = MagicMock(side_effect=_file_iter)  # type: ignore[method-assign]

    received = list(
        bus.subscribe(SIM_ID, rpc_response_channel("cid-123"), timeout=0.1)
    )
    assert len(received) == 1
    assert received[0].type == "interview.response"
    bus._file_bus.subscribe.assert_called_once()
    bus._redis.pubsub.assert_not_called()


def test_request_response_drives_the_file_bus_round_trip(bus):
    """End-to-end shape: request_response uses the file bus on both legs."""

    captured = {}

    def _fake_publish(channel, event):
        captured["publish_channel"] = channel
        captured["publish_event"] = event

    def _fake_subscribe(_sim, channel, **_kwargs) -> Iterator[SimulationEvent]:
        captured["subscribe_channel"] = channel
        yield SimulationEvent(
            type="interview.response",
            simulation_id=SIM_ID,
            payload={"answer": "ok"},
            correlation_id=captured["publish_event"].correlation_id,
        )

    bus._file_bus.publish = MagicMock(side_effect=_fake_publish)  # type: ignore[method-assign]
    bus._file_bus.subscribe = MagicMock(side_effect=_fake_subscribe)  # type: ignore[method-assign]

    response = bus.request_response(
        SIM_ID,
        command_type="interview",
        args={"agent_id": 7, "prompt": "test"},
        timeout=0.5,
    )
    assert response.payload == {"answer": "ok"}
    assert captured["publish_channel"] == CHANNEL_RPC_COMMAND
    assert captured["subscribe_channel"].startswith("rpc.response.")
    bus._redis.publish.assert_not_called()
