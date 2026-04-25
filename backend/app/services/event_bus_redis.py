"""Redis-backed SimulationEventBus (Issue #9 Phase B + Issue #17 Phase D).

Scope:

* ``CHANNEL_CONTROL`` / ``CHANNEL_STATE`` ride Redis Pub/Sub for live
  delivery and mirror to the artifact store as retained snapshots
  (Issue #9 Phase B).
* ``CHANNEL_RPC_COMMAND`` and ``rpc.response.*`` go **hybrid**: every
  publish hits both Redis and the file IPC layer, and every response
  read races a Redis Pub/Sub subscription against a file-artifact
  poller. Whichever arrives first wins; the loser is cleaned up so it
  cannot trigger a duplicate later (Issue #17 Phase D).

The hybrid path keeps rolling upgrades safe: a subprocess that already
runs the new ``RedisIPCBridge`` answers via Pub/Sub (low latency); a
legacy subprocess that only writes the response file is still picked
up by the file poller; backward compat with no dependence on which
side ships first.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
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
            # Phase D hybrid: publish on Redis Pub/Sub for the live
            # subprocess listener AND through the file bus so legacy
            # subprocesses keep working and the file poller in
            # _await_response can fall back if Redis stays silent.
            try:
                self._publish_redis(channel, event)
            except Exception:
                logger.exception(
                    "Redis publish failed for RPC channel=%s — file path remains",
                    channel,
                )
            try:
                self._file_bus.publish(channel, event)
            except Exception:
                logger.exception(
                    "File publish failed for RPC channel=%s — Redis path remains",
                    channel,
                )
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
        if channel == CHANNEL_RPC_COMMAND:
            # Subprocess-side concern only; Backend never subscribes to
            # rpc.command. Keep file-bus delegation for defensive use.
            yield from self._file_bus.subscribe(
                simulation_id, channel, timeout=timeout, poll_interval=poll_interval
            )
            return
        if channel.startswith("rpc.response."):
            cid = channel.removeprefix("rpc.response.")
            yield from self._subscribe_rpc_response_hybrid(
                simulation_id, cid, timeout=timeout, poll_interval=poll_interval
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

    # ----- hybrid RPC response wait (Issue #17 Phase D) -----------------

    def _cleanup_rpc_artifacts(
        self, simulation_id: str, correlation_id: str
    ) -> None:
        """Best-effort delete of file artifacts after a response is consumed."""
        for artifact in (
            f"ipc_response/{correlation_id}",
            f"ipc_command/{correlation_id}",
        ):
            try:
                self._store.delete(simulation_id, artifact)
            except Exception:  # noqa: BLE001 — cleanup must never raise
                pass

    def _decode_file_response(
        self,
        data: Dict[str, Any],
        simulation_id: str,
        correlation_id: str,
    ) -> SimulationEvent:
        """Translate either Bus-event or legacy IPCResponse shapes."""
        if "type" in data and "simulation_id" in data:
            return SimulationEvent.from_dict(data)
        return SimulationEvent(
            type=f"rpc.response.{data.get('status', 'unknown')}",
            simulation_id=simulation_id,
            payload={
                "status": data.get("status"),
                "result": data.get("result"),
                "error": data.get("error"),
            },
            ts=data.get("timestamp", datetime.now().isoformat()),
            correlation_id=correlation_id,
        )

    def _await_response(
        self,
        simulation_id: str,
        correlation_id: str,
        *,
        deadline: Optional[float],
        poll_interval: float,
        pubsub: Any,
    ) -> Optional[SimulationEvent]:
        """Race a Redis Pub/Sub subscription against the file artifact poller.

        Returns the first response observed on either path, or None if
        ``deadline`` elapses. Cleans up file leftovers on success so a
        late-arriving second copy cannot trigger a duplicate dispatch.
        """
        artifact = f"ipc_response/{correlation_id}"
        while True:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                wait = min(remaining, poll_interval)
            else:
                wait = poll_interval

            msg = pubsub.get_message(timeout=wait)
            if msg and msg.get("type") == "message":
                try:
                    data = json.loads(msg["data"])
                    self._cleanup_rpc_artifacts(simulation_id, correlation_id)
                    return SimulationEvent.from_dict(data)
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning(
                        "Dropped malformed RPC response on rpc.response.%s: %s",
                        correlation_id,
                        exc,
                    )

            if self._store.exists(simulation_id, artifact):
                data = self._store.read_json(simulation_id, artifact, default=None)
                if data is not None:
                    self._cleanup_rpc_artifacts(simulation_id, correlation_id)
                    return self._decode_file_response(
                        data, simulation_id, correlation_id
                    )

    def _subscribe_rpc_response_hybrid(
        self,
        simulation_id: str,
        correlation_id: str,
        *,
        timeout: Optional[float],
        poll_interval: float,
    ) -> Iterator[SimulationEvent]:
        response_key = _channel_key(
            simulation_id, rpc_response_channel(correlation_id)
        )
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(response_key)
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            event = self._await_response(
                simulation_id,
                correlation_id,
                deadline=deadline,
                poll_interval=poll_interval,
                pubsub=pubsub,
            )
            if event is not None:
                yield event
        finally:
            try:
                pubsub.unsubscribe(response_key)
                pubsub.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Pubsub cleanup error on %s: %s", response_key, exc
                )

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
        correlation_id = str(uuid.uuid4())
        response_key = _channel_key(
            simulation_id, rpc_response_channel(correlation_id)
        )

        # Pre-arm the Redis subscription BEFORE publishing — the
        # subprocess might answer before this method gets back the
        # control flow otherwise.
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(response_key)
        try:
            command = SimulationEvent(
                type=command_type,
                simulation_id=simulation_id,
                payload=dict(args),
                correlation_id=correlation_id,
            )
            # publish() handles the Redis+File hybrid for RPC channels.
            self.publish(CHANNEL_RPC_COMMAND, command)

            deadline = time.monotonic() + timeout
            event = self._await_response(
                simulation_id,
                correlation_id,
                deadline=deadline,
                poll_interval=poll_interval,
                pubsub=pubsub,
            )
            if event is not None:
                return event

            # Timeout: drop a stale command artifact so the subprocess
            # cannot pick it up after the caller gave up.
            try:
                self._store.delete(simulation_id, f"ipc_command/{correlation_id}")
            except Exception:  # noqa: BLE001
                pass
            raise TimeoutError(
                f"Timeout waiting for IPC response "
                f"(command_type={command_type}, correlation_id={correlation_id}, "
                f"timeout={timeout}s)"
            )
        finally:
            try:
                pubsub.unsubscribe(response_key)
                pubsub.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Pubsub cleanup error on %s: %s", response_key, exc
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
