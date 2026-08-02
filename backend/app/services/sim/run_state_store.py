"""
Run-state data structures and pure I/O helpers for OASIS simulation runs.

Extracted from ``simulation_runner.py`` as part of M11 Phase 5 PR 1.
``simulation_runner.py`` re-exports all public symbols for backward-compat.

Design constraints
------------------
* No direct imports of ``event_bus`` or ``RunRegistry`` — callers pass those
  as optional ``Callable`` parameters so this module stays side-effect-free
  with respect to the bus and registry.
* ``resolve_default_store`` is imported lazily (same pattern as ``_store()``
  in ``simulation_runner.py``) so this module works inside and outside of a
  Flask application context.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ...utils.logger import get_logger
from ...utils.path_safety import safe_join_within_root, validate_path_id

logger = get_logger("agora.run_state_store")


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class RunnerStatus(str, Enum):
    """Runner status"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    READY = "ready"  # legacy alias for idle


@dataclass
class AgentAction:
    """Agent action record"""
    round_num: int
    timestamp: str
    platform: str  # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str  # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class RoundSummary:
    """Round summary"""
    round_num: int
    start_time: str
    end_time: Optional[str] = None
    simulated_hour: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    active_agents: List[int] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "simulated_hour": self.simulated_hour,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "active_agents": self.active_agents,
            "actions_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class SimulationRunState:
    """Simulation run state (real-time)"""
    simulation_id: str
    runner_status: RunnerStatus = RunnerStatus.IDLE

    # Progress information
    current_round: int = 0
    total_rounds: int = 0
    # float: bei minutes_per_round=30 ist eine Runde 0.5 h — mit int wäre die
    # Folge 0, 1, 1, 2 und der Fortschritt nicht mehr streng monoton (B-28).
    simulated_hours: float = 0.0
    total_simulation_hours: int = 0

    # Per-platform independent rounds and simulated time (for dual-platform parallel display)
    twitter_current_round: int = 0
    reddit_current_round: int = 0
    twitter_simulated_hours: float = 0.0
    reddit_simulated_hours: float = 0.0

    # Platform status
    twitter_running: bool = False
    reddit_running: bool = False
    twitter_actions_count: int = 0
    reddit_actions_count: int = 0

    # Platform completion status (detected via simulation_end events in actions.jsonl)
    twitter_completed: bool = False
    reddit_completed: bool = False

    # Round summary
    rounds: List[RoundSummary] = field(default_factory=list)

    # Recent actions (for frontend real-time display)
    recent_actions: List[AgentAction] = field(default_factory=list)
    max_recent_actions: int = 50

    # Timestamps
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    # Error message
    error: Optional[str] = None

    # Process ID (for stopping)
    process_pid: Optional[int] = None

    def add_action(self, action: AgentAction) -> None:
        """Add action to recent actions list"""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[:self.max_recent_actions]

        if action.platform == "twitter":
            self.twitter_actions_count += 1
        else:
            self.reddit_actions_count += 1

        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "runner_status": self.runner_status.value,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "simulated_hours": self.simulated_hours,
            "total_simulation_hours": self.total_simulation_hours,
            "progress_percent": round(self.current_round / max(self.total_rounds, 1) * 100, 1),
            # Per-platform independent rounds and time
            "twitter_current_round": self.twitter_current_round,
            "reddit_current_round": self.reddit_current_round,
            "twitter_simulated_hours": self.twitter_simulated_hours,
            "reddit_simulated_hours": self.reddit_simulated_hours,
            "twitter_running": self.twitter_running,
            "reddit_running": self.reddit_running,
            "twitter_completed": self.twitter_completed,
            "reddit_completed": self.reddit_completed,
            "twitter_actions_count": self.twitter_actions_count,
            "reddit_actions_count": self.reddit_actions_count,
            "total_actions_count": self.twitter_actions_count + self.reddit_actions_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "process_pid": self.process_pid,
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        """Details with recent actions"""
        result = self.to_dict()
        result["recent_actions"] = [a.to_dict() for a in self.recent_actions]
        result["rounds_count"] = len(self.rounds)
        return result


# ---------------------------------------------------------------------------
# Module-level I/O functions
# ---------------------------------------------------------------------------


def load_run_state(
    run_id: str,
    base_dir: str | Path,
) -> Optional[SimulationRunState]:
    """Deserialise ``run_state.json`` from the artifact store into a
    :class:`SimulationRunState`.

    Returns ``None`` when the artifact does not exist or is unreadable.
    ``base_dir`` is unused by this function (the artifact store resolves paths
    internally); it is accepted for API symmetry with :func:`save_run_state`
    and the other helpers.
    """
    from ...services.artifact_store import resolve_default_store

    store = resolve_default_store()
    if not store.exists(run_id, "run_state"):
        return None

    try:
        data = store.read_json(run_id, "run_state", default=None)
        if not data:
            return None

        state = SimulationRunState(
            simulation_id=run_id,
            runner_status=RunnerStatus(data.get("runner_status", "idle")),
            current_round=data.get("current_round", 0),
            total_rounds=data.get("total_rounds", 0),
            simulated_hours=data.get("simulated_hours", 0),
            total_simulation_hours=data.get("total_simulation_hours", 0),
            # Per-platform independent rounds and time
            twitter_current_round=data.get("twitter_current_round", 0),
            reddit_current_round=data.get("reddit_current_round", 0),
            twitter_simulated_hours=data.get("twitter_simulated_hours", 0),
            reddit_simulated_hours=data.get("reddit_simulated_hours", 0),
            twitter_running=data.get("twitter_running", False),
            reddit_running=data.get("reddit_running", False),
            twitter_completed=data.get("twitter_completed", False),
            reddit_completed=data.get("reddit_completed", False),
            twitter_actions_count=data.get("twitter_actions_count", 0),
            reddit_actions_count=data.get("reddit_actions_count", 0),
            started_at=data.get("started_at"),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            process_pid=data.get("process_pid"),
        )

        # Load recent actions
        for a in data.get("recent_actions", []):
            state.recent_actions.append(
                AgentAction(
                    round_num=a.get("round_num", 0),
                    timestamp=a.get("timestamp", ""),
                    platform=a.get("platform", ""),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a.get("action_type", ""),
                    action_args=a.get("action_args", {}),
                    result=a.get("result"),
                    success=a.get("success", True),
                )
            )

        return state
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error("Failed to load run state: %s", exc)
        return None


def save_run_state(
    state: SimulationRunState,
    base_dir: str | Path,
    *,
    event_bus_publish: Optional[Callable[[Dict[str, Any]], None]] = None,
    run_registry_sync: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> None:
    """Serialise *state* and persist it via the artifact store.

    Side-effects (event-bus publish, run-registry sync) are injected as
    optional callables so this module does not import ``event_bus`` or
    ``RunRegistry`` directly.

    Parameters
    ----------
    state:
        The :class:`SimulationRunState` to persist.
    base_dir:
        Simulation root directory (used only to ensure the ``<sim_id>/``
        sub-directory exists before the artifact store writes).
    event_bus_publish:
        If provided, called with the serialised *data* dict after writing.
        Must be best-effort (exceptions are caught and logged at DEBUG).
    run_registry_sync:
        If provided, called with ``(simulation_id, data)`` after writing.
        Must be best-effort (exceptions are caught and logged at DEBUG).
    """
    from ...services.artifact_store import resolve_default_store

    sim_dir = safe_join_within_root(str(base_dir), validate_path_id(state.simulation_id, field_name="simulation_id"))
    os.makedirs(sim_dir, exist_ok=True)  # keep dir for log-pipe / shutil consumers

    data = state.to_detail_dict()
    resolve_default_store().write_json(state.simulation_id, "run_state", data)

    if event_bus_publish is not None:
        try:
            event_bus_publish(data)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Event bus state publish skipped: %s", exc)

    if run_registry_sync is not None:
        try:
            run_registry_sync(state.simulation_id, data)
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.debug("Run registry sync skipped for %s: %s", state.simulation_id, exc)


def read_console_log(
    run_id: str,
    base_dir: str | Path,
    *,
    max_lines: Optional[int] = None,
) -> List[str]:
    """Return lines from ``<base_dir>/<run_id>/simulation.log``.

    Parameters
    ----------
    run_id:
        Simulation ID.
    base_dir:
        Parent directory that contains per-simulation sub-directories.
    max_lines:
        When set, return only the *last* ``max_lines`` lines.  ``None``
        returns all lines.

    Returns
    -------
    list[str]
        Lines with trailing newlines stripped.  Empty list on missing file or
        read error.
    """
    log_path = safe_join_within_root(str(base_dir), validate_path_id(run_id, field_name="run_id"), "simulation.log")

    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n\r") for line in fh]
        if max_lines is not None:
            lines = lines[-max_lines:]
        return lines
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning("Failed to read simulation.log for %s: %s", run_id, exc)
        return []


def cleanup_run_logs(
    run_id: str,
    base_dir: str | Path,
) -> Dict[str, Any]:
    """Delete run-time log and state files for *run_id*.

    Removes the following files (config files are intentionally kept):

    * ``run_state.json``
    * ``simulation.log``
    * ``stdout.log`` / ``stderr.log``
    * ``twitter_simulation.db``
    * ``reddit_simulation.db``
    * ``env_status.json``
    * ``twitter/actions.jsonl``
    * ``reddit/actions.jsonl``

    Parameters
    ----------
    run_id:
        Simulation ID.
    base_dir:
        Parent directory that contains per-simulation sub-directories.

    Returns
    -------
    dict
        ``{"success": bool, "cleaned_files": list[str], "errors": list[str] | None}``
    """
    sim_dir = safe_join_within_root(str(base_dir), validate_path_id(run_id, field_name="run_id"))

    if not os.path.exists(sim_dir):
        return {"success": True, "message": "Simulation directory does not exist, no cleanup needed"}

    cleaned_files: List[str] = []
    errors: List[str] = []

    files_to_delete = [
        "run_state.json",
        "simulation.log",
        "stdout.log",
        "stderr.log",
        "twitter_simulation.db",
        "reddit_simulation.db",
        "env_status.json",
    ]

    dirs_to_clean = ["twitter", "reddit"]

    for filename in files_to_delete:
        file_path = os.path.join(sim_dir, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                cleaned_files.append(filename)
            except Exception as exc:  # noqa: BLE001 — state already saved; exc logged or discarded
                errors.append(f"Failed to delete {filename}: {exc}")

    for dir_name in dirs_to_clean:
        actions_file = os.path.join(sim_dir, dir_name, "actions.jsonl")
        if os.path.exists(actions_file):
            try:
                os.remove(actions_file)
                cleaned_files.append(f"{dir_name}/actions.jsonl")
            except Exception as exc:  # noqa: BLE001 — state already saved; exc logged or discarded
                errors.append(f"Failed to delete {dir_name}/actions.jsonl: {exc}")

    logger.info(
        "Cleanup run logs completed: %s, deleted files: %s",
        run_id,
        cleaned_files,
    )

    return {
        "success": len(errors) == 0,
        "cleaned_files": cleaned_files,
        "errors": errors if errors else None,
    }
