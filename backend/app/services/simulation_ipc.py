"""Simulation inter-process communication module (Flask ↔ OASIS subprocess).

Issue #9 Phase A: The public API stays the same (module-level helpers
and the ``SimulationIPCClient`` / ``SimulationIPCServer`` classes), but
the Flask-side implementations now go through :class:`SimulationEventBus`.
The underlying transport is still the filesystem in Phase A
(:class:`FilePollingEventBus`); Phase B swaps it for Redis without
touching the callers.

The OASIS subprocess scripts (``run_reddit_simulation.py``,
``run_twitter_simulation.py``) still keep their own lightweight
``IPCHandler`` and read ``control_state.json`` directly. They'll switch
to the bus in Phase B together with the Redis adapter.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from .artifact_store import resolve_default_store
from .event_bus import (
    CHANNEL_CONTROL,
    CHANNEL_RPC_COMMAND,
    SimulationEvent,
    SimulationEventBus,
    resolve_default_event_bus,
    rpc_response_channel,
)

logger = get_logger("agora.simulation_ipc")


def _coerce_simulation_id(simulation_id_or_dir: str) -> str:
    """Accept a simulation_id or a legacy filesystem path and return the id."""
    if not simulation_id_or_dir:
        raise ValueError("simulation_id is required")
    if os.sep in simulation_id_or_dir or "/" in simulation_id_or_dir:
        return os.path.basename(simulation_id_or_dir.rstrip(os.sep).rstrip("/"))
    return simulation_id_or_dir


# ---------------------------------------------------------------------------
# Control state (pause/resume between rounds)
# ---------------------------------------------------------------------------


def read_control_state(simulation_id: str) -> Dict[str, Any]:
    """Return current control state for a simulation.

    Reads the persisted snapshot directly from the artifact store because
    the OASIS subprocess (which has no Flask context) still calls this
    helper synchronously between rounds.
    """
    sim_id = _coerce_simulation_id(simulation_id)
    store = resolve_default_store()
    data = store.read_json(sim_id, "control_state", default=None)
    if not data:
        return {"paused": False, "stop_requested": False, "updated_at": None}
    data.setdefault("paused", False)
    data.setdefault("stop_requested", False)
    return data


def write_control_state(
    simulation_id: str,
    *,
    bus: Optional[SimulationEventBus] = None,
    **changes: Any,
) -> Dict[str, Any]:
    """Publish a control update to the bus and return the merged state."""
    sim_id = _coerce_simulation_id(simulation_id)
    bus = bus or resolve_default_event_bus()
    ts = datetime.now().isoformat()
    event = SimulationEvent(
        type="control.update",
        simulation_id=sim_id,
        payload=dict(changes),
        ts=ts,
    )
    bus.publish(CHANNEL_CONTROL, event)
    return read_control_state(sim_id)


def set_pause_state(simulation_id: str, paused: bool) -> Dict[str, Any]:
    """Convenience wrapper used by the API to flip the pause flag."""
    return write_control_state(simulation_id, paused=bool(paused))


def is_paused(simulation_id: str) -> bool:
    """True if the simulation has a pending pause flag."""
    return bool(read_control_state(simulation_id).get("paused"))


def wait_while_paused(simulation_id: str, poll_interval: float = 1.0) -> None:
    """Block until ``paused`` flips back to False. Subprocess-side helper."""
    while is_paused(simulation_id):
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# IPC command / response envelopes
# ---------------------------------------------------------------------------


class CommandType(str, Enum):
    """Command type"""

    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"


class CommandStatus(str, Enum):
    """Command status"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """IPC command (legacy shape, kept for backward compatibility)."""

    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IPCCommand":
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class IPCResponse:
    """IPC response (legacy shape, kept for backward compatibility)."""

    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IPCResponse":
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


def _event_to_response(event: SimulationEvent, correlation_id: str) -> IPCResponse:
    """Translate a bus response event into the legacy :class:`IPCResponse`."""
    payload = event.payload or {}
    status_raw = payload.get("status") or event.type.split(".")[-1]
    try:
        status = CommandStatus(status_raw)
    except ValueError:
        status = CommandStatus.FAILED if payload.get("error") else CommandStatus.COMPLETED
    return IPCResponse(
        command_id=correlation_id,
        status=status,
        result=payload.get("result"),
        error=payload.get("error"),
        timestamp=event.ts,
    )


# ---------------------------------------------------------------------------
# IPC client (Flask side)
# ---------------------------------------------------------------------------


class SimulationIPCClient:
    """Flask-side IPC client. Publishes commands on the bus and awaits responses."""

    def __init__(
        self,
        simulation_id: str,
        *,
        bus: Optional[SimulationEventBus] = None,
    ) -> None:
        self.simulation_id = _coerce_simulation_id(simulation_id)
        self._bus: SimulationEventBus = bus or resolve_default_event_bus()
        # Store is only used for non-event reads (env_status). Everything
        # command-shaped flows through the bus.
        self._store = resolve_default_store()

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> IPCResponse:
        """Publish a command on the bus and block until the response arrives."""
        correlation_id = str(uuid.uuid4())
        # Build the command event directly so we control the correlation id.
        command_event = SimulationEvent(
            type=command_type.value,
            simulation_id=self.simulation_id,
            payload=dict(args),
            correlation_id=correlation_id,
        )
        self._bus.publish(CHANNEL_RPC_COMMAND, command_event)
        logger.info(
            "Send IPC command: %s, correlation_id=%s", command_type.value, correlation_id
        )

        response_channel = rpc_response_channel(correlation_id)
        for event in self._bus.subscribe(
            self.simulation_id,
            response_channel,
            timeout=timeout,
            poll_interval=poll_interval,
        ):
            response = _event_to_response(event, correlation_id)
            logger.info(
                "Received IPC response: correlation_id=%s, status=%s",
                correlation_id,
                response.status.value,
            )
            return response

        logger.error("Timeout waiting for IPC response: correlation_id=%s", correlation_id)
        raise TimeoutError(f"Timeout waiting for command response ({timeout} seconds)")

    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: Optional[str] = None,
        timeout: float = 60.0,
    ) -> IPCResponse:
        args: Dict[str, Any] = {"agent_id": agent_id, "prompt": prompt}
        if platform:
            args["platform"] = platform
        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout,
        )

    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: Optional[str] = None,
        timeout: float = 120.0,
    ) -> IPCResponse:
        args: Dict[str, Any] = {"interviews": interviews}
        if platform:
            args["platform"] = platform
        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout,
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout,
        )

    def check_env_alive(self) -> bool:
        """True if the simulation environment reports ``status == "alive"``."""
        status = self._store.read_json(self.simulation_id, "env_status", default=None)
        if not status:
            return False
        return status.get("status") == "alive"


# ---------------------------------------------------------------------------
# IPC server (subprocess side — unchanged file semantics in Phase A)
# ---------------------------------------------------------------------------


class SimulationIPCServer:
    """Subprocess-side IPC server.

    Phase A keeps this store-backed because OASIS subprocess scripts have
    their own lightweight ``IPCHandler`` and do not import the bus. The
    server exists as a public surface for any caller that still wants a
    Python-level API; Phase B will rewrite it on top of Redis pub/sub
    subscriptions.
    """

    def __init__(self, simulation_id: str) -> None:
        self.simulation_id = _coerce_simulation_id(simulation_id)
        self._store = resolve_default_store()
        self.simulation_dir = os.path.join(
            ArtifactLocator.simulations_dir(), self.simulation_id
        )
        os.makedirs(self.simulation_dir, exist_ok=True)
        self._running = False

    def start(self) -> None:
        self._running = True
        self._update_env_status("alive")

    def stop(self) -> None:
        self._running = False
        self._update_env_status("stopped")

    def _update_env_status(self, status: str) -> None:
        self._store.write_json(
            self.simulation_id,
            "env_status",
            {"status": status, "timestamp": datetime.now().isoformat()},
        )

    def poll_commands(self) -> Optional[IPCCommand]:
        """Poll command directory, return first pending command."""
        names = self._store.list_artifacts(self.simulation_id, prefix="ipc_command/")
        if not names:
            return None

        commands_dir = os.path.join(self.simulation_dir, "ipc_commands")
        if os.path.isdir(commands_dir):
            def mtime_for(name: str) -> float:
                cmd_id = name.split("/", 1)[1]
                path = os.path.join(commands_dir, f"{cmd_id}.json")
                try:
                    return os.path.getmtime(path)
                except OSError:
                    return 0.0
            names = sorted(names, key=mtime_for)
        else:
            names = sorted(names)

        for artifact_name in names:
            data = self._store.read_json(self.simulation_id, artifact_name, default=None)
            if data is None:
                logger.warning("Failed to read command artifact: %s", artifact_name)
                continue
            try:
                # Bus-era event shape has {type, correlation_id, payload, ...};
                # translate to legacy IPCCommand.
                if "type" in data and "correlation_id" in data:
                    return IPCCommand(
                        command_id=data.get("correlation_id")
                        or data.get("command_id", ""),
                        command_type=CommandType(data["type"]),
                        args=data.get("payload", {}) or {},
                        timestamp=data.get("ts", datetime.now().isoformat()),
                    )
                return IPCCommand.from_dict(data)
            except (KeyError, ValueError) as e:
                logger.warning("Failed to parse command artifact %s: %s", artifact_name, e)
                continue
        return None

    def send_response(self, response: IPCResponse) -> None:
        """Persist a response and clean up the matching command artifact."""
        self._store.write_json(
            self.simulation_id,
            f"ipc_response/{response.command_id}",
            response.to_dict(),
        )
        self._store.delete(self.simulation_id, f"ipc_command/{response.command_id}")

    def send_success(self, command_id: str, result: Dict[str, Any]) -> None:
        self.send_response(
            IPCResponse(
                command_id=command_id,
                status=CommandStatus.COMPLETED,
                result=result,
            )
        )

    def send_error(self, command_id: str, error: str) -> None:
        self.send_response(
            IPCResponse(
                command_id=command_id,
                status=CommandStatus.FAILED,
                error=error,
            )
        )
