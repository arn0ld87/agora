"""
Simulation inter-process communication module for Flask and simulation script communication.

Communication uses a simple filesystem-based command/response model:
1. Flask writes commands to the commands/ directory.
2. The simulation script polls the commands directory, executes the command, and writes the response to the responses/ directory.
3. Flask polls the responses directory and retrieves the result.

In addition to request/response commands, a single ``control_state.json`` file is used
for fire-and-forget control flags such as pause/resume. The OASIS subprocess polls this
file between rounds; Flask writes it directly via :func:`set_pause_state`.

Issue #13: All JSON I/O on simulation artifacts now goes through
:class:`SimulationArtifactStore`. Helpers accept ``simulation_id`` (not raw
paths) so the store can resolve the artifact location uniformly.
"""

import os
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from .artifact_store import resolve_default_store

logger = get_logger('agora.simulation_ipc')


def _coerce_simulation_id(simulation_id_or_dir: str) -> str:
    """Accept a simulation_id or a legacy filesystem path and return the id.

    Subprocess scripts and older callers still pass a directory path; we
    derive the simulation_id from the basename so they keep working without
    forcing a coordinated change in the OASIS subprocess scripts.
    """
    if not simulation_id_or_dir:
        raise ValueError("simulation_id is required")
    if os.sep in simulation_id_or_dir or "/" in simulation_id_or_dir:
        return os.path.basename(simulation_id_or_dir.rstrip(os.sep).rstrip("/"))
    return simulation_id_or_dir


# ----- Control state (pause/resume between rounds) -----


def read_control_state(simulation_id: str) -> Dict[str, Any]:
    """Return current control state for a simulation.

    Defaults: ``{"paused": False, "stop_requested": False, "updated_at": None}``.
    """
    sim_id = _coerce_simulation_id(simulation_id)
    store = resolve_default_store()
    data = store.read_json(sim_id, "control_state", default=None)
    if not data:
        return {"paused": False, "stop_requested": False, "updated_at": None}
    data.setdefault("paused", False)
    data.setdefault("stop_requested", False)
    return data


def write_control_state(simulation_id: str, **changes) -> Dict[str, Any]:
    """Merge ``changes`` into the existing control state and persist atomically."""
    sim_id = _coerce_simulation_id(simulation_id)
    state = read_control_state(sim_id)
    state.update(changes)
    state["updated_at"] = datetime.now().isoformat()
    resolve_default_store().write_json(sim_id, "control_state", state)
    return state


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


class CommandType(str, Enum):
    """Command type"""
    INTERVIEW = "interview"           # Single Agent interview
    BATCH_INTERVIEW = "batch_interview"  # Batch interview
    CLOSE_ENV = "close_env"           # Close environment


class CommandStatus(str, Enum):
    """Command status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """IPC command"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """IPC response"""
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
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    Simulation IPC client for Flask side.

    Used to send commands to the simulation process and wait for responses.
    """

    def __init__(self, simulation_id: str):
        """Initialize IPC client.

        ``simulation_id`` may also be a legacy directory path; the basename is
        used in that case to keep older call sites compatible.
        """
        self.simulation_id = _coerce_simulation_id(simulation_id)
        self._store = resolve_default_store()

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """Send command and wait for response."""
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )

        cmd_artifact = f"ipc_command/{command_id}"
        resp_artifact = f"ipc_response/{command_id}"

        # Write command file (atomic via store).
        self._store.write_json(self.simulation_id, cmd_artifact, command.to_dict())
        logger.info(f"Send IPC command: {command_type.value}, command_id={command_id}")

        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._store.exists(self.simulation_id, resp_artifact):
                response_data = self._store.read_json(
                    self.simulation_id, resp_artifact, default=None
                )
                if response_data:
                    response = IPCResponse.from_dict(response_data)
                    # Clean up command and response artifacts.
                    self._store.delete(self.simulation_id, cmd_artifact)
                    self._store.delete(self.simulation_id, resp_artifact)
                    logger.info(
                        f"Received IPC response: command_id={command_id}, "
                        f"status={response.status.value}"
                    )
                    return response
            time.sleep(poll_interval)

        # Timeout
        logger.error(f"Timeout waiting for IPC response: command_id={command_id}")
        self._store.delete(self.simulation_id, cmd_artifact)
        raise TimeoutError(f"Timeout waiting for command response ({timeout} seconds)")

    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """Send single Agent interview command."""
        args = {"agent_id": agent_id, "prompt": prompt}
        if platform:
            args["platform"] = platform
        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """Send batch interview command."""
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform
        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """Send close environment command."""
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )

    def check_env_alive(self) -> bool:
        """True if the simulation environment reports ``status == "alive"``."""
        status = self._store.read_json(self.simulation_id, "env_status", default=None)
        if not status:
            return False
        return status.get("status") == "alive"


class SimulationIPCServer:
    """
    Simulation IPC server for the simulation script side.

    Polls the command directory, executes commands, and returns responses.
    Runs inside the OASIS subprocess (no Flask app context).
    """

    def __init__(self, simulation_id: str):
        """Initialize IPC server. ``simulation_id`` may be a legacy directory path."""
        self.simulation_id = _coerce_simulation_id(simulation_id)
        self._store = resolve_default_store()

        # Keep a real on-disk path around for callers that still expect one
        # (e.g. log files written next to the IPC artifacts in subprocess scripts).
        self.simulation_dir = os.path.join(
            ArtifactLocator.simulations_dir(), self.simulation_id
        )
        os.makedirs(self.simulation_dir, exist_ok=True)

        # Environment status
        self._running = False

    def start(self):
        """Mark server as running"""
        self._running = True
        self._update_env_status("alive")

    def stop(self):
        """Mark server as stopped"""
        self._running = False
        self._update_env_status("stopped")

    def _update_env_status(self, status: str):
        """Update environment status file (atomic via store)."""
        self._store.write_json(self.simulation_id, "env_status", {
            "status": status,
            "timestamp": datetime.now().isoformat()
        })

    def poll_commands(self) -> Optional[IPCCommand]:
        """Poll command directory, return first pending command."""
        names = self._store.list_artifacts(self.simulation_id, prefix="ipc_command/")
        if not names:
            return None

        # Sort by mtime if the local adapter is in play, else lexicographic
        # (good enough for in-memory tests where uuid order is stable).
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
                logger.warning(f"Failed to read command artifact: {artifact_name}")
                continue
            try:
                return IPCCommand.from_dict(data)
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse command artifact {artifact_name}: {e}")
                continue
        return None

    def send_response(self, response: IPCResponse):
        """Persist a response and clean up the matching command artifact."""
        self._store.write_json(
            self.simulation_id,
            f"ipc_response/{response.command_id}",
            response.to_dict(),
        )
        self._store.delete(self.simulation_id, f"ipc_command/{response.command_id}")

    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Send success response"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))

    def send_error(self, command_id: str, error: str):
        """Send error response"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
