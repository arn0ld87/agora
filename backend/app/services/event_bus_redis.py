"""Redis-backed SimulationEventBus (Issue #9 Phase B).

Scope: Redis Pub/Sub carries the **live** channels — ``CHANNEL_CONTROL``
and ``CHANNEL_STATE``. These are the low-latency, one-writer/many-reader
channels that Phase C's frontend SSE bridge will consume.

RPC channels (``CHANNEL_RPC_COMMAND`` and ``rpc.response.*``) keep the
filesystem semantics from Phase A in this release: the OASIS subprocess
ships its own lightweight file-based ``IPCHandler`` (see
``backend/scripts/run_{reddit,twitter}_simulation.py``) and migrating
*both sides* to Redis is a dedicated follow-up. Until then, this adapter
delegates RPC publish/subscribe to an internal
:class:`FilePollingEventBus`, keeping IPC latency on par with Phase A
without requiring subprocess changes.

``CHANNEL_CONTROL`` and ``CHANNEL_STATE`` writes go to both Redis
(pub/sub for live subscribers) and the artifact store (retained snapshot
for ``read_control_state`` / UI polling).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Iterator, Optional

from ..utils.logger import get_logger
from .artifact_store import SimulationArtifactStore, resolve_default_store
from .event_bus import (
    CHANNEL_ACTION,
    CHANNEL_CONTROL,
    CHANNEL_RPC_COMMAND,
    CHANNEL_STATE,
    FilePollingEventBus,
    SimulationEvent,
    rpc_response_channel,
)

logger = get_logger("agora.event_bus_redis")

_CHANNEL_PREFIX = "agora:sim"


def _channel_key(simulation_id: str, channel: str) -> str:
    return f"{_CHANNEL_PREFIX}:{simulation_id}:{channel}"


def _is_rpc_channel(channel: str) -> bool:
    return channel == CHANNEL_RPC_COMMAND or channel.startswith("rpc.response.")


class RedisEventBus:
    """Redis pub/sub bus for live channels; files for RPC (Phase B scope).

    One long-lived client per bus instance. Live-channel subscribers get
    a fresh :class:`PubSub` handle per :meth:`subscribe` call — each
    iterator owns its subscription lifecycle including cleanup on
    generator close.
    """

    def __init__(
        self,
        url: str,
        *,
        artifact_store: Optional[SimulationArtifactStore] = None,
        ping_on_init: bool = True,
    ) -> None:
        import redis  # local import: keep module import cheap if Redis unused

        self._redis = redis.from_url(
            url,
            decode_responses=True,
            socket_keepalive=True,
            health_check_interval=30,
        )
        if ping_on_init:
            self._redis.ping()
        self._store: SimulationArtifactStore = artifact_store or resolve_default_store()
        self._file_bus = FilePollingEventBus(store=self._store)
        self._url = url

    # ----- internal ------------------------------------------------------

    def _write_retained(self, channel: str, event: SimulationEvent) -> None:
        if channel == CHANNEL_CONTROL:
            existing = (
                self._store.read_json(event.simulation_id, "control_state", default=None) or {}
            )
            existing.setdefault("paused", False)
            existing.setdefault("stop_requested", False)
            existing.update(event.payload or {})
            existing["updated_at"] = event.ts
            self._store.write_json(event.simulation_id, "control_state", existing)
        elif channel == CHANNEL_STATE:
            self._store.write_json(event.simulation_id, "run_state", event.payload)

    def _publish_redis(self, channel: str, event: SimulationEvent) -> None:
        key = _channel_key(event.simulation_id, channel)
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        self._redis.publish(key, payload)

    # ----- port: publish -------------------------------------------------

    def publish(self, channel: str, event: SimulationEvent) -> None:
        if _is_rpc_channel(channel):
            # RPC stays file-backed in Phase B (subprocess keeps its
            # legacy file IPC handler). Phase D migrates both sides.
            self._file_bus.publish(channel, event)
            return
        if channel == CHANNEL_ACTION:
            # No transport for action events in Phase B — the action log
            # files in `uploads/simulations/<id>/{twitter,reddit}/actions.jsonl`
            # remain the source of truth until Phase C wires SSE mirroring.
            return
        if channel not in (CHANNEL_CONTROL, CHANNEL_STATE):
            raise ValueError(f"Unknown channel for RedisEventBus: {channel!r}")

        try:
            self._publish_redis(channel, event)
        except Exception:
            logger.exception("Redis publish failed for channel=%s", channel)
            raise
        try:
            self._write_retained(channel, event)
        except Exception as exc:  # noqa: BLE001 — mirror is best-effort
            logger.warning(
                "Failed to mirror %s event to artifact store: %s", channel, exc
            )

    # ----- port: subscribe ----------------------------------------------

    def subscribe(
        self,
        simulation_id: str,
        channel: str,
        *,
        timeout: Optional[float] = None,
        poll_interval: float = 0.5,
    ) -> Iterator[SimulationEvent]:
        if _is_rpc_channel(channel):
            yield from self._file_bus.subscribe(
                simulation_id, channel, timeout=timeout, poll_interval=poll_interval
            )
            return
        if channel == CHANNEL_ACTION:
            # No-op iterator — Phase B does not ship action events.
            return
        if channel not in (CHANNEL_CONTROL, CHANNEL_STATE):
            raise ValueError(f"Unknown channel for RedisEventBus: {channel!r}")

        yield from self._subscribe_live(
            simulation_id, channel, timeout=timeout, poll_interval=poll_interval
        )

    def _subscribe_live(
        self,
        simulation_id: str,
        channel: str,
        *,
        timeout: Optional[float],
        poll_interval: float,
    ) -> Iterator[SimulationEvent]:
        key = _channel_key(simulation_id, channel)
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(key)
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            # Yield the retained snapshot first so late subscribers see
            # the current value (matches FilePollingEventBus semantics).
            artifact_name = "control_state" if channel == CHANNEL_CONTROL else "run_state"
            snapshot = self._store.read_json(simulation_id, artifact_name, default=None)
            if snapshot:
                yield SimulationEvent(
                    type=f"{channel}.update",
                    simulation_id=simulation_id,
                    payload=snapshot,
                    ts=snapshot.get("updated_at") or "",
                )
            while True:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return
                    wait = min(remaining, poll_interval)
                else:
                    wait = poll_interval
                msg = pubsub.get_message(timeout=wait)
                if msg and msg.get("type") == "message":
                    try:
                        data = json.loads(msg["data"])
                        yield SimulationEvent.from_dict(data)
                    except (json.JSONDecodeError, KeyError) as exc:
                        logger.warning(
                            "Dropped malformed bus event on %s: %s", key, exc
                        )
        finally:
            try:
                pubsub.unsubscribe(key)
                pubsub.close()
            except Exception as exc:  # noqa: BLE001 — cleanup must never raise
                logger.debug("Pubsub cleanup error on %s: %s", key, exc)

    # ----- port: request_response ---------------------------------------

    def request_response(
        self,
        simulation_id: str,
        command_type: str,
        args: Dict[str, Any],
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> SimulationEvent:
        # RPC round-trip continues over the file bus in Phase B so the
        # unchanged OASIS subprocess can respond.
        correlation_id = str(uuid.uuid4())
        command = SimulationEvent(
            type=command_type,
            simulation_id=simulation_id,
            payload=dict(args),
            correlation_id=correlation_id,
        )
        self._file_bus.publish(CHANNEL_RPC_COMMAND, command)
        for event in self._file_bus.subscribe(
            simulation_id,
            rpc_response_channel(correlation_id),
            timeout=timeout,
            poll_interval=poll_interval,
        ):
            return event
        raise TimeoutError(
            f"Timeout waiting for IPC response "
            f"(command_type={command_type}, correlation_id={correlation_id}, "
            f"timeout={timeout}s)"
        )

    # ----- lifecycle -----------------------------------------------------

    def close(self) -> None:
        try:
            self._redis.close()
        except Exception:  # noqa: BLE001
            pass


def is_redis_reachable(url: str, timeout: float = 0.5) -> bool:
    """Cheap connectivity probe used to auto-pick the backend."""
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)
        client.ping()
        client.close()
        return True
    except Exception:  # noqa: BLE001
        return False


__all__ = ["RedisEventBus", "is_redis_reachable"]
