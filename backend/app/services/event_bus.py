"""SimulationEventBus – Port + adapters for simulation IPC events (Issue #9 Phase A).

The Flask↔OASIS subprocess pipeline has historically communicated via
filesystem polling — commands in ``ipc_commands/``, responses in
``ipc_responses/``, pause flags in ``control_state.json``, run state in
``run_state.json``. Phase A introduces a bus abstraction so Phase B can
swap the transport to Redis Pub/Sub without touching the callers.

Two adapters ship today:

* :class:`InMemoryEventBus` – threadsafe dict-of-channels, used by tests
  and future in-process callers.
* :class:`FilePollingEventBus` – wraps :class:`SimulationArtifactStore` and
  reproduces the **exact** semantics of the pre-#9 code (polling reads,
  atomic writes, cleanup on request/response).

Redis lands in Phase B as ``event_bus_redis.py`` behind the same port.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Protocol, runtime_checkable

from ..utils.logger import get_logger
from .artifact_store import SimulationArtifactStore, resolve_default_store

logger = get_logger("agora.event_bus")


# ---------------------------------------------------------------------------
# Channel naming conventions (shared across all adapters)
# ---------------------------------------------------------------------------

CHANNEL_CONTROL = "control"          # pause / stop / resume flags
CHANNEL_STATE = "state"              # run_state.json updates
CHANNEL_RPC_COMMAND = "rpc.command"  # Flask → subprocess commands (fan-in)
CHANNEL_ACTION = "action"            # reserved for Phase B (live action events)


def rpc_response_channel(correlation_id: str) -> str:
    """Return the per-command response channel (one client subscriber)."""
    return f"rpc.response.{correlation_id}"


# ---------------------------------------------------------------------------
# Event record
# ---------------------------------------------------------------------------


@dataclass
class SimulationEvent:
    """Envelope for everything crossing the Flask↔subprocess boundary."""

    type: str
    simulation_id: str
    payload: Dict[str, Any]
    ts: str = field(default_factory=lambda: datetime.now().isoformat())
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "simulation_id": self.simulation_id,
            "payload": self.payload,
            "ts": self.ts,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimulationEvent":
        return cls(
            type=data["type"],
            simulation_id=data["simulation_id"],
            payload=data.get("payload", {}) or {},
            ts=data.get("ts", datetime.now().isoformat()),
            correlation_id=data.get("correlation_id"),
        )


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


@runtime_checkable
class SimulationEventBus(Protocol):
    """Pub/Sub port with request/response correlation.

    Channels are scoped per ``simulation_id`` — subscribing to ``control``
    on sim A must not deliver events published on sim B.
    """

    def publish(self, channel: str, event: SimulationEvent) -> None:
        """Publish ``event`` to ``channel`` (scoped to ``event.simulation_id``)."""
        ...

    def subscribe(
        self,
        simulation_id: str,
        channel: str,
        *,
        timeout: Optional[float] = None,
        poll_interval: float = 0.5,
    ) -> Iterator[SimulationEvent]:
        """Yield events published on ``channel`` for ``simulation_id``.

        The iterator blocks between events. If ``timeout`` is given, it
        stops yielding after ``timeout`` seconds of idleness.
        """
        ...

    def request_response(
        self,
        simulation_id: str,
        command_type: str,
        args: Dict[str, Any],
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> SimulationEvent:
        """Publish an RPC command and block until the matching response arrives.

        Raises :class:`TimeoutError` if no response is seen within ``timeout``.
        """
        ...


# ---------------------------------------------------------------------------
# In-memory adapter
# ---------------------------------------------------------------------------


class InMemoryEventBus:
    """Threadsafe in-process bus. Backed by a dict of queues + a condition variable."""

    def __init__(self) -> None:
        self._lock = threading.Condition()
        self._queues: Dict[tuple[str, str], List[SimulationEvent]] = {}

    # -- internal ---------------------------------------------------------

    def _queue_for(self, simulation_id: str, channel: str) -> List[SimulationEvent]:
        key = (simulation_id, channel)
        q = self._queues.get(key)
        if q is None:
            q = []
            self._queues[key] = q
        return q

    # -- port -------------------------------------------------------------

    def publish(self, channel: str, event: SimulationEvent) -> None:
        with self._lock:
            self._queue_for(event.simulation_id, channel).append(event)
            self._lock.notify_all()

    def subscribe(
        self,
        simulation_id: str,
        channel: str,
        *,
        timeout: Optional[float] = None,
        poll_interval: float = 0.5,  # unused for in-memory (signal-based)
    ) -> Iterator[SimulationEvent]:
        cursor = 0
        with self._lock:
            # Start after any events already in the queue — new subscribers
            # get only events published from now on.
            cursor = len(self._queue_for(simulation_id, channel))
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                q = self._queue_for(simulation_id, channel)
                if cursor < len(q):
                    event = q[cursor]
                    cursor += 1
                    # Yield outside the lock to avoid deadlocks in consumers
                    # that call publish() during iteration.
                    pass
                else:
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            return
                        self._lock.wait(timeout=remaining)
                    else:
                        self._lock.wait()
                    continue
            yield event

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
        response_channel = rpc_response_channel(correlation_id)
        # Arm the response queue *before* publishing so fast responders can
        # never deliver into a missing channel.
        with self._lock:
            self._queue_for(simulation_id, response_channel)

        command = SimulationEvent(
            type=command_type,
            simulation_id=simulation_id,
            payload=args,
            correlation_id=correlation_id,
        )
        self.publish(CHANNEL_RPC_COMMAND, command)
        for event in self.subscribe(
            simulation_id, response_channel, timeout=timeout, poll_interval=poll_interval
        ):
            return event
        raise TimeoutError(
            f"Timeout waiting for RPC response "
            f"(command_type={command_type}, correlation_id={correlation_id}, timeout={timeout}s)"
        )


# ---------------------------------------------------------------------------
# File-polling adapter (reproduces pre-#9 behaviour on top of the artifact store)
# ---------------------------------------------------------------------------


class FilePollingEventBus:
    """Wraps :class:`SimulationArtifactStore` and emulates pub/sub via polling.

    This exists to keep Phase A a pure refactor: the code paths that used
    to call ``store.write_json(sim, 'control_state', ...)`` now go through
    the bus, but the *persisted* semantics are unchanged.
    """

    def __init__(self, store: Optional[SimulationArtifactStore] = None) -> None:
        self._store: SimulationArtifactStore = store or resolve_default_store()

    # -- internal helpers --------------------------------------------------

    def _write_control(self, event: SimulationEvent) -> None:
        """Merge ``event.payload`` into ``control_state.json`` (same as write_control_state)."""
        existing = self._store.read_json(event.simulation_id, "control_state", default=None) or {}
        existing.setdefault("paused", False)
        existing.setdefault("stop_requested", False)
        existing.update(event.payload or {})
        existing["updated_at"] = event.ts
        self._store.write_json(event.simulation_id, "control_state", existing)

    def _write_state(self, event: SimulationEvent) -> None:
        """Persist a full run_state snapshot."""
        self._store.write_json(event.simulation_id, "run_state", event.payload)

    def _write_rpc_command(self, event: SimulationEvent) -> None:
        if not event.correlation_id:
            raise ValueError("RPC command events must carry a correlation_id")
        payload = {
            **event.to_dict(),
            "command_id": event.correlation_id,  # legacy field for IPC consumers
        }
        self._store.write_json(
            event.simulation_id,
            f"ipc_command/{event.correlation_id}",
            payload,
        )

    def _write_rpc_response(self, channel: str, event: SimulationEvent) -> None:
        # Channel form: "rpc.response.<correlation_id>"
        cid = channel.removeprefix("rpc.response.")
        if not cid:
            raise ValueError("rpc.response channel requires a correlation id suffix")
        payload = {
            **event.to_dict(),
            "command_id": cid,
        }
        self._store.write_json(event.simulation_id, f"ipc_response/{cid}", payload)
        # Matching command artifact is cleaned up by the responder's consumer
        # (mirrors today's behaviour in SimulationIPCServer.send_response).
        self._store.delete(event.simulation_id, f"ipc_command/{cid}")

    # -- port: publish -----------------------------------------------------

    def publish(self, channel: str, event: SimulationEvent) -> None:
        if channel == CHANNEL_CONTROL:
            self._write_control(event)
        elif channel == CHANNEL_STATE:
            self._write_state(event)
        elif channel == CHANNEL_RPC_COMMAND:
            self._write_rpc_command(event)
        elif channel.startswith("rpc.response."):
            self._write_rpc_response(channel, event)
        elif channel == CHANNEL_ACTION:
            # No file-backed semantics today — actions are already written to
            # actions.jsonl by OASIS. Phase B will mirror them to the bus.
            logger.debug(
                "Action event dropped by FilePollingEventBus (no file-backed semantics): %s",
                event.type,
            )
        else:
            raise ValueError(f"Unknown channel for FilePollingEventBus: {channel!r}")

    # -- port: subscribe ---------------------------------------------------

    def subscribe(
        self,
        simulation_id: str,
        channel: str,
        *,
        timeout: Optional[float] = None,
        poll_interval: float = 0.5,
    ) -> Iterator[SimulationEvent]:
        deadline = None if timeout is None else time.monotonic() + timeout

        if channel == CHANNEL_CONTROL:
            yield from self._subscribe_control(
                simulation_id, deadline=deadline, poll_interval=poll_interval
            )
        elif channel == CHANNEL_STATE:
            yield from self._subscribe_state(
                simulation_id, deadline=deadline, poll_interval=poll_interval
            )
        elif channel == CHANNEL_RPC_COMMAND:
            yield from self._subscribe_rpc_commands(
                simulation_id, deadline=deadline, poll_interval=poll_interval
            )
        elif channel.startswith("rpc.response."):
            cid = channel.removeprefix("rpc.response.")
            yield from self._subscribe_rpc_response(
                simulation_id, cid, deadline=deadline, poll_interval=poll_interval
            )
        else:
            raise ValueError(f"Unknown channel for FilePollingEventBus: {channel!r}")

    def _sleep_until_deadline(self, deadline: Optional[float], poll_interval: float) -> bool:
        """Sleep ``poll_interval`` s; return True if deadline reached afterwards."""
        time.sleep(poll_interval)
        return deadline is not None and time.monotonic() >= deadline

    def _subscribe_control(
        self, simulation_id: str, *, deadline: Optional[float], poll_interval: float
    ) -> Iterator[SimulationEvent]:
        last_stamp: Optional[str] = None
        while True:
            data = self._store.read_json(simulation_id, "control_state", default=None)
            if data:
                stamp = data.get("updated_at")
                if stamp != last_stamp:
                    last_stamp = stamp
                    yield SimulationEvent(
                        type="control.update",
                        simulation_id=simulation_id,
                        payload=data,
                        ts=stamp or datetime.now().isoformat(),
                    )
            if deadline is not None and time.monotonic() >= deadline:
                return
            if self._sleep_until_deadline(deadline, poll_interval):
                return

    def _subscribe_state(
        self, simulation_id: str, *, deadline: Optional[float], poll_interval: float
    ) -> Iterator[SimulationEvent]:
        last_stamp: Optional[str] = None
        while True:
            data = self._store.read_json(simulation_id, "run_state", default=None)
            if data:
                stamp = data.get("updated_at")
                if stamp != last_stamp:
                    last_stamp = stamp
                    yield SimulationEvent(
                        type="state.update",
                        simulation_id=simulation_id,
                        payload=data,
                        ts=stamp or datetime.now().isoformat(),
                    )
            if deadline is not None and time.monotonic() >= deadline:
                return
            if self._sleep_until_deadline(deadline, poll_interval):
                return

    def _subscribe_rpc_commands(
        self, simulation_id: str, *, deadline: Optional[float], poll_interval: float
    ) -> Iterator[SimulationEvent]:
        seen: set[str] = set()
        while True:
            names = self._store.list_artifacts(simulation_id, prefix="ipc_command/")
            # Deterministic dispatch order (matches SimulationIPCServer.poll_commands).
            sim_dir = _simulation_abs_dir(simulation_id)
            if sim_dir and os.path.isdir(os.path.join(sim_dir, "ipc_commands")):
                def _mtime(name: str) -> float:
                    cid = name.split("/", 1)[1]
                    path = os.path.join(sim_dir, "ipc_commands", f"{cid}.json")
                    try:
                        return os.path.getmtime(path)
                    except OSError:
                        return 0.0
                names = sorted(names, key=_mtime)
            else:
                names = sorted(names)

            for name in names:
                cid = name.split("/", 1)[1]
                if cid in seen:
                    continue
                data = self._store.read_json(simulation_id, name, default=None)
                if data is None:
                    continue
                seen.add(cid)
                if "type" in data and "simulation_id" in data:
                    yield SimulationEvent.from_dict(data)
                else:
                    # Legacy IPCCommand shape — translate.
                    yield SimulationEvent(
                        type=data.get("command_type", "rpc.command"),
                        simulation_id=simulation_id,
                        payload=data.get("args", {}) or {},
                        ts=data.get("timestamp", datetime.now().isoformat()),
                        correlation_id=data.get("command_id", cid),
                    )
            if deadline is not None and time.monotonic() >= deadline:
                return
            if self._sleep_until_deadline(deadline, poll_interval):
                return

    def _subscribe_rpc_response(
        self,
        simulation_id: str,
        correlation_id: str,
        *,
        deadline: Optional[float],
        poll_interval: float,
    ) -> Iterator[SimulationEvent]:
        artifact = f"ipc_response/{correlation_id}"
        while True:
            if self._store.exists(simulation_id, artifact):
                data = self._store.read_json(simulation_id, artifact, default=None)
                if data is not None:
                    self._store.delete(simulation_id, artifact)
                    self._store.delete(simulation_id, f"ipc_command/{correlation_id}")
                    if "type" in data and "simulation_id" in data:
                        yield SimulationEvent.from_dict(data)
                    else:
                        # Legacy IPCResponse shape.
                        yield SimulationEvent(
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
                    return
            if deadline is not None and time.monotonic() >= deadline:
                return
            if self._sleep_until_deadline(deadline, poll_interval):
                return

    # -- port: request_response -------------------------------------------

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
        command = SimulationEvent(
            type=command_type,
            simulation_id=simulation_id,
            payload=args,
            correlation_id=correlation_id,
        )
        self.publish(CHANNEL_RPC_COMMAND, command)
        logger.info(
            "Published IPC command: type=%s correlation_id=%s", command_type, correlation_id
        )
        for event in self.subscribe(
            simulation_id,
            rpc_response_channel(correlation_id),
            timeout=timeout,
            poll_interval=poll_interval,
        ):
            return event
        # Cleanup the command artifact so the subprocess does not pick up a
        # stale command after the caller gave up.
        self._store.delete(simulation_id, f"ipc_command/{correlation_id}")
        raise TimeoutError(
            f"Timeout waiting for IPC response "
            f"(command_type={command_type}, correlation_id={correlation_id}, timeout={timeout}s)"
        )


def _simulation_abs_dir(simulation_id: str) -> Optional[str]:
    """Return the on-disk simulation directory if the local adapter is active."""
    from ..utils.artifact_locator import ArtifactLocator

    path = os.path.join(ArtifactLocator.simulations_dir(), simulation_id)
    return path if os.path.isdir(path) else None


# ---------------------------------------------------------------------------
# Default resolver (mirrors artifact_store.resolve_default_store)
# ---------------------------------------------------------------------------


def resolve_default_event_bus() -> SimulationEventBus:
    """Return the app-wide bus, falling back to a file-polling one outside Flask.

    The subprocess scripts (no Flask context) get a fresh ``FilePollingEventBus``
    backed by the default artifact store. Once Phase B lands, they'll construct
    a ``RedisEventBus`` directly when ``REDIS_URL`` is available.
    """
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            container = current_app.extensions.get("container")
            if container is not None:
                return container.event_bus
            bus = current_app.extensions.get("event_bus")
            if bus is not None:
                return bus
    except Exception:  # noqa: BLE001 — Flask optional at import time
        pass
    return FilePollingEventBus()


__all__ = [
    "SimulationEvent",
    "SimulationEventBus",
    "InMemoryEventBus",
    "FilePollingEventBus",
    "resolve_default_event_bus",
    "rpc_response_channel",
    "CHANNEL_CONTROL",
    "CHANNEL_STATE",
    "CHANNEL_RPC_COMMAND",
    "CHANNEL_ACTION",
]
