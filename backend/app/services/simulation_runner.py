"""
OASIS Simulation Runner
Run simulations in the background and record actions for each Agent, supporting real-time status monitoring
"""

from __future__ import annotations

import os
import threading
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime
from queue import Queue

from ..utils.logger import get_logger
from .artifact_store import resolve_default_store
from .event_bus import CHANNEL_STATE, SimulationEvent, resolve_default_event_bus
from .run_registry import RunRegistry
from .graph_memory_updater import GraphMemoryManager
# M11 Phase 5 PR 1 — re-export from extracted sub-module for backward-compat.
# All callers that import these symbols from simulation_runner continue to work.
# Aliased imports satisfy mypy's no-implicit-reexport check (PEP 484 §re-exports).
from .sim.run_state_store import AgentAction as AgentAction  # noqa: PLC0414
from .sim.run_state_store import RoundSummary as RoundSummary  # noqa: PLC0414
from .sim.run_state_store import RunnerStatus as RunnerStatus  # noqa: PLC0414
from .sim.run_state_store import SimulationRunState as SimulationRunState  # noqa: PLC0414
from .sim.run_state_store import load_run_state
from .sim.run_state_store import save_run_state as _save_run_state_fn
from .sim.run_state_store import read_console_log
from .sim.run_state_store import cleanup_run_logs

# M11 Phase 5 PR 2 — re-export action-log-reader module functions.
# The five class-method wrappers below delegate to these for backward-compat.
from .sim.action_log_reader import read_action_log_chunk as _read_action_log_chunk
from .sim.action_log_reader import check_all_platforms_completed as _check_all_platforms_completed_fn
from .sim.action_log_reader import read_actions_from_file as _read_actions_from_file_fn
from .sim.action_log_reader import get_all_actions as _get_all_actions_fn
from .sim.action_log_reader import get_actions as _get_actions_fn

# M11 Phase 5 PR 3 — re-export monitor module functions.
# The three class-method wrappers below delegate to these for backward-compat.
from .sim.monitor import monitor_simulation as _monitor_simulation_fn
from .sim.monitor import get_timeline as _get_timeline_fn
from .sim.monitor import get_agent_stats as _get_agent_stats_fn

# M11 Phase 5 PR 4 — re-export interview/IPC module functions.
# The eight class-method wrappers below delegate to these for backward-compat.
from .sim.interview_client import check_env_alive as _check_env_alive_fn
from .sim.interview_client import get_env_status_detail as _get_env_status_detail_fn
from .sim.interview_client import interview_agent as _interview_agent_fn
from .sim.interview_client import interview_agents_batch as _interview_agents_batch_fn
from .sim.interview_client import interview_all_agents as _interview_all_agents_fn
from .sim.interview_client import close_simulation_env as _close_simulation_env_fn
from .sim.interview_client import _get_interview_history_from_db as _get_hist_from_db_fn
from .sim.interview_client import get_interview_history as _get_interview_history_fn
from .sim.interview_direct import (
    direct_interviews_available as _direct_interviews_available_fn,
)

# M11 Phase 5 PR 5 — re-export process-manager module functions.
# The class-method wrappers below delegate to these for backward-compat.
from .sim.process_manager import _compute_oasis_db_path as _compute_oasis_db_path  # noqa: PLC0414
from .sim.process_manager import _inject_oasis_db_env as _inject_oasis_db_env  # noqa: PLC0414
from .sim.process_manager import terminate_process as _terminate_process_fn
from .sim.process_manager import start_simulation as _start_simulation_fn
from .sim.process_manager import stop_simulation as _stop_simulation_fn
from .sim.process_manager import cleanup_all_simulations as _cleanup_all_simulations_fn
from .sim.process_manager import register_cleanup as _register_cleanup_fn
from .sim.process_manager import get_running_simulations as _get_running_simulations_fn


def _store():
    """Return the active SimulationArtifactStore (Issue #13).

    SimulationRunner is a classmethod-only orchestrator that runs both inside
    Flask request handlers and inside the daemonic cleanup hook (no app context).
    Resolving lazily keeps both paths working without changing the call surface.
    """
    return resolve_default_store()


logger = get_logger('agora.simulation_runner')


class SimulationRunner:
    """Orchestrator for OASIS simulation subprocesses.

    After M11 Phase 5 (PRs 1-5) all heavyweight logic lives in app.services.sim.*
    submodules; this class holds shared state and provides thin delegation methods
    for backward-compat with API blueprints and existing Monkeypatch stubs.
    """

    RUN_STATE_DIR = os.path.join(os.path.dirname(__file__), '../../uploads/simulations')
    SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '../../scripts')

    # In-memory run state (class-level dicts; passed by reference to submodules)
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}
    _stderr_files: Dict[str, Any] = {}
    _graph_memory_enabled: Dict[str, bool] = {}  # simulation_id -> enabled

    @classmethod
    def get_console_log(cls, simulation_id: str, from_line: int = 0) -> Dict[str, Any]:
        """Return incremental slice of simulation.log for client-side polling."""
        all_lines = read_console_log(simulation_id, cls.RUN_STATE_DIR)

        if not all_lines and not os.path.exists(
            os.path.join(cls.RUN_STATE_DIR, simulation_id, "simulation.log")
        ):
            return {
                "lines": [],
                "total_lines": 0,
                "from_line": from_line,
                "next_line": from_line,
                "has_more": False,
            }

        total_lines = len(all_lines)
        lines = all_lines[from_line:]

        return {
            "lines": lines,
            "total_lines": total_lines,
            "from_line": from_line,
            "next_line": total_lines,
            "has_more": False,
        }

    @classmethod
    def get_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Get run state"""
        if simulation_id in cls._run_states:
            return cls._run_states[simulation_id]

        # Try to load from file
        state = cls._load_run_state(simulation_id)
        if state:
            cls._run_states[simulation_id] = state
        return state

    @classmethod
    def _load_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Load run state from disk (delegates to run_state_store.load_run_state)."""
        return load_run_state(simulation_id, cls.RUN_STATE_DIR)

    @classmethod
    def _save_run_state(cls, state: SimulationRunState) -> None:
        """Persist run state; fires event-bus publish and run-registry sync as callbacks."""
        def _publish(data: Dict[str, Any]) -> None:
            bus = resolve_default_event_bus()
            bus.publish(
                CHANNEL_STATE,
                SimulationEvent(
                    type="state.update",
                    simulation_id=state.simulation_id,
                    payload=data,
                    ts=data.get("updated_at", datetime.now().isoformat()),
                ),
            )

        def _registry_sync(simulation_id: str, data: Dict[str, Any]) -> None:
            registry = RunRegistry()
            run = registry.get_latest_by_linked_id(
                "simulation_id", simulation_id, run_type="simulation_run"
            )
            if run:
                registry.update_run(
                    run["run_id"],
                    status=state.runner_status.value,
                    progress=data.get("progress_percent", 0),
                    message=f"Runner status: {state.runner_status.value}",
                    artifacts={"simulation": {
                        "run_state": os.path.join(cls.RUN_STATE_DIR, simulation_id, "run_state.json"),
                        "simulation_log": os.path.join(cls.RUN_STATE_DIR, simulation_id, "simulation.log"),
                    }},
                )

        _save_run_state_fn(state, cls.RUN_STATE_DIR, event_bus_publish=_publish, run_registry_sync=_registry_sync)
        # Keep in-memory cache in sync
        cls._run_states[state.simulation_id] = state

    @classmethod
    def _setup_graph_memory(
        cls, sim_id: str, enable: bool, graph_id: Optional[str], storage: Any
    ) -> None:
        """Configure graph-memory updater (helper for start_simulation)."""
        if enable:
            if not graph_id:
                raise ValueError("Must provide graph_id when enabling graph memory update")
            try:
                if not storage:
                    raise ValueError("Must provide storage when enabling graph memory update")
                GraphMemoryManager.create_updater(sim_id, graph_id, storage)
                cls._graph_memory_enabled[sim_id] = True
                logger.info(f"Graph memory update enabled: simulation_id={sim_id}, graph_id={graph_id}")
            except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.error(f"Failed to create graph memory updater: {e}")
                cls._graph_memory_enabled[sim_id] = False
        else:
            cls._graph_memory_enabled[sim_id] = False

    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",
        max_rounds: int = None,
        enable_graph_memory_update: bool = False,
        graph_id: str = None,
        storage: Any = None,
        runtime_env: Optional[Dict[str, str]] = None,
    ) -> SimulationRunState:
        """Start simulation.

        Delegates fully to
        :func:`~app.services.sim.process_manager.start_simulation`.

        M11 Phase 5 PR 5 — body extracted; wrapper kept for backward-compat.
        """
        from .simulation_ipc import write_control_state as _wcs

        store = _store()

        def _on_monitor_start(sim_id: str) -> None:
            t = threading.Thread(target=cls._monitor_simulation, args=(sim_id,), daemon=True)
            t.start()
            cls._monitor_threads[sim_id] = t

        return _start_simulation_fn(
            simulation_id,
            platform,
            run_state_dir=cls.RUN_STATE_DIR,
            scripts_dir=cls.SCRIPTS_DIR,
            processes=cls._processes,
            action_queues=cls._action_queues,
            monitor_threads=cls._monitor_threads,
            stdout_files=cls._stdout_files,
            stderr_files=cls._stderr_files,
            graph_memory_enabled=cls._graph_memory_enabled,
            get_run_state=cls.get_run_state,
            save_state=cls._save_run_state,
            on_monitor_start=_on_monitor_start,
            write_control_state=_wcs,
            get_config=lambda s: store.read_json(s, "simulation_config", default=None),
            config_exists=lambda s: store.exists(s, "simulation_config"),
            setup_graph_memory=lambda s: cls._setup_graph_memory(
                s, enable_graph_memory_update, graph_id, storage
            ),
            max_rounds=max_rounds,
            runtime_env=runtime_env,
        )

    @classmethod
    def _monitor_simulation(cls, simulation_id: str) -> None:
        """Delegate to monitor.monitor_simulation (PR 3, Thread-target Monkeypatch-compat)."""
        _monitor_simulation_fn(
            simulation_id,
            run_state_dir=cls.RUN_STATE_DIR,
            processes=cls._processes,
            graph_memory_enabled=cls._graph_memory_enabled,
            action_queues=cls._action_queues,
            stdout_files=cls._stdout_files,
            stderr_files=cls._stderr_files,
            get_run_state=cls.get_run_state,
            save_state=cls._save_run_state,
        )

    @classmethod
    def _read_action_log(cls, log_path: str, position: int, state: SimulationRunState, platform: str) -> int:
        """Delegate to action_log_reader.read_action_log_chunk (PR 2, Monkeypatch-compat)."""
        return _read_action_log_chunk(
            log_path, position, state, platform,
            graph_memory_enabled=cls._graph_memory_enabled.get(state.simulation_id, False),
        )

    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """Delegate to action_log_reader.check_all_platforms_completed (PR 2, Monkeypatch-compat)."""
        return _check_all_platforms_completed_fn(
            state, base_dir=os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        )

    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 10):
        """Delegate to process_manager.terminate_process (PR 5, Monkeypatch-compat)."""
        _terminate_process_fn(process, simulation_id, timeout=timeout)

    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """Stop simulation — delegates to process_manager.stop_simulation (PR 5)."""
        return _stop_simulation_fn(
            simulation_id,
            processes=cls._processes,
            graph_memory_enabled=cls._graph_memory_enabled,
            get_run_state=cls.get_run_state,
            save_state=cls._save_run_state,
            stop_graph_memory_updater=GraphMemoryManager.stop_updater,
        )

    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None,
    ) -> List[AgentAction]:
        """Delegate to action_log_reader.read_actions_from_file (PR 2, Monkeypatch-compat)."""
        return _read_actions_from_file_fn(
            file_path, default_platform=default_platform, platform_filter=platform_filter,
            agent_id=agent_id, round_num=round_num,
        )

    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None,
    ) -> List[AgentAction]:
        """Delegate to action_log_reader.get_all_actions (PR 2, Monkeypatch-compat)."""
        return _get_all_actions_fn(
            simulation_id, cls.RUN_STATE_DIR, platform=platform,
            agent_id=agent_id, round_num=round_num,
        )

    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None,
    ) -> List[AgentAction]:
        """Delegate to action_log_reader.get_actions (PR 2, Monkeypatch-compat)."""
        return _get_actions_fn(
            simulation_id, cls.RUN_STATE_DIR, limit=limit, offset=offset,
            platform=platform, agent_id=agent_id, round_num=round_num,
        )

    @classmethod
    def get_timeline(
        cls, simulation_id: str, start_round: int = 0, end_round: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to monitor.get_timeline (PR 3, Monkeypatch-compat)."""
        return _get_timeline_fn(simulation_id, cls.RUN_STATE_DIR, start_round=start_round, end_round=end_round)

    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """Delegate to monitor.get_agent_stats (PR 3, Monkeypatch-compat)."""
        return _get_agent_stats_fn(simulation_id, cls.RUN_STATE_DIR)

    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """Clean up run logs for force restart; evicts in-memory state cache.

        Delegates file deletion to run_state_store.cleanup_run_logs.
        Does not delete simulation_config.json or profile files.
        """
        result = cleanup_run_logs(simulation_id, cls.RUN_STATE_DIR)
        cls._run_states.pop(simulation_id, None)
        return result

    # Flag to prevent duplicate cleanup (single-element list for mutability across callbacks)
    _cleanup_done: List[bool] = [False]

    @classmethod
    def _mark_store_state_stopped(cls, simulation_id: str) -> None:
        """Set ``state.json`` status=stopped for a simulation (cleanup helper)."""
        try:
            store = _store()
            if store.exists(simulation_id, "state"):
                state_data = store.read_json(simulation_id, "state", default=None)
                if state_data:
                    state_data["status"] = "stopped"
                    state_data["updated_at"] = datetime.now().isoformat()
                    store.write_json(simulation_id, "state", state_data)
                    logger.info(f"Updated state.json status to stopped: {simulation_id}")
            else:
                logger.warning(f"state.json does not exist for {simulation_id}")
        except Exception as state_err:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.warning(f"Failed to update state.json: {simulation_id}, error={state_err}")

    @classmethod
    def cleanup_all_simulations(cls) -> None:
        """Clean up all running simulation processes.

        Delegates to :func:`~app.services.sim.process_manager.cleanup_all_simulations`.

        M11 Phase 5 PR 5 — body extracted; wrapper kept for backward-compat
        (atexit/signal registrations reference this method by name).
        """
        _cleanup_all_simulations_fn(
            processes=cls._processes,
            stdout_files=cls._stdout_files,
            stderr_files=cls._stderr_files,
            graph_memory_enabled=cls._graph_memory_enabled,
            action_queues=cls._action_queues,
            get_run_state=cls.get_run_state,
            save_state=cls._save_run_state,
            stop_all_graph_memory=GraphMemoryManager.stop_all,
            update_store_state=cls._mark_store_state_stopped,
            cleanup_done_flag=cls._cleanup_done,
        )

    @classmethod
    def register_cleanup(cls) -> None:
        """Register atexit / signal handlers for cleanup (PR 5, delegates to process_manager)."""
        _register_cleanup_fn(cleanup_callable=cls.cleanup_all_simulations)

    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """Return list of running simulation IDs (PR 5, delegates to process_manager)."""
        return _get_running_simulations_fn(processes=cls._processes)

    # ============== Interview functionality ==============
    # M11 Phase 5 PR 4 — thin delegations to app.services.sim.interview_client.

    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """Check if the simulation environment is alive (can receive Interview commands)."""
        return _check_env_alive_fn(simulation_id, run_state_dir=cls.RUN_STATE_DIR)

    @classmethod
    def direct_interviews_available(cls, simulation_id: str) -> bool:
        """Check if interviews can be served in-process (personas persisted)."""
        return _direct_interviews_available_fn(
            simulation_id, run_state_dir=cls.RUN_STATE_DIR
        )

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """Return detailed status information for a simulation environment."""
        return _get_env_status_detail_fn(simulation_id)

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: Optional[str] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """Interview a single agent via IPC."""
        return _interview_agent_fn(
            simulation_id, agent_id, prompt, platform, timeout,
            run_state_dir=cls.RUN_STATE_DIR,
        )

    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: Optional[str] = None,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """Batch-interview multiple agents via IPC."""
        return _interview_agents_batch_fn(
            simulation_id, interviews, platform, timeout,
            run_state_dir=cls.RUN_STATE_DIR,
        )

    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: Optional[str] = None,
        timeout: float = 180.0,
    ) -> Dict[str, Any]:
        """Interview all agents in a simulation using the same prompt."""
        return _interview_all_agents_fn(
            simulation_id, prompt, platform, timeout,
            run_state_dir=cls.RUN_STATE_DIR,
        )

    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Send a close-environment command to a running simulation."""
        return _close_simulation_env_fn(
            simulation_id, timeout, run_state_dir=cls.RUN_STATE_DIR,
        )

    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Read interview history from a single platform SQLite database."""
        return _get_hist_from_db_fn(db_path, platform_name, agent_id, limit)

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return interview history records for a simulation."""
        return _get_interview_history_fn(
            simulation_id, platform, agent_id, limit,
            run_state_dir=cls.RUN_STATE_DIR,
        )
