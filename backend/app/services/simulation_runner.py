"""
OASIS Simulation Runner
Run simulations in the background and record actions for each Agent, supporting real-time status monitoring
"""

from __future__ import annotations

import os
import sys
import json
import threading
import subprocess
import signal
import atexit
from typing import Dict, Any, List, Optional
from datetime import datetime
from queue import Queue

from ..utils.logger import get_logger
from .artifact_store import resolve_default_store
from .event_bus import CHANNEL_STATE, SimulationEvent, resolve_default_event_bus
from .run_registry import RunRegistry
from .graph_memory_updater import GraphMemoryManager
from .simulation_ipc import SimulationIPCClient

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


def _store():
    """Return the active SimulationArtifactStore (Issue #13).

    SimulationRunner is a classmethod-only orchestrator that runs both inside
    Flask request handlers and inside the daemonic cleanup hook (no app context).
    Resolving lazily keeps both paths working without changing the call surface.
    """
    return resolve_default_store()

logger = get_logger('agora.simulation_runner')

# Flag whether cleanup function is registered
_cleanup_registered = False

# Platform detection
IS_WINDOWS = sys.platform == 'win32'



# Sub-Slice 21 — OASIS-DB-Pfad pro Sim, damit OASIS keine DB ins
# read-only Site-Packages-Verzeichnis schreibt. Standalone-Helper, damit
# sie unit-testbar bleiben (kein Subprozess-Setup nötig).

_OASIS_DB_DIR_NAME = "oasis_db"
_OASIS_DB_FILE_NAME = "social_media.db"


def _compute_oasis_db_path(sim_dir: str) -> str:
    """Liefert ``<sim_dir>/oasis_db/social_media.db`` und legt das
    Verzeichnis an (idempotent). OASIS' ``get_db_path()`` macht **kein**
    ``mkdir``, wenn ``OASIS_DB_PATH``-ENV gesetzt ist — das Verzeichnis
    muss vorhanden sein, bevor der Subprozess startet."""
    db_dir = os.path.join(sim_dir, _OASIS_DB_DIR_NAME)
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, _OASIS_DB_FILE_NAME)


def _inject_oasis_db_env(env: Dict[str, str], sim_dir: str) -> None:
    """Setzt ``OASIS_DB_PATH`` im Subprozess-Env auf einen sim-spezifischen
    Pfad — aber nur, wenn der User es nicht selbst überschrieben hat
    (z. B. via Compose-Env oder ``.env``)."""
    if env.get("OASIS_DB_PATH"):
        return
    env["OASIS_DB_PATH"] = _compute_oasis_db_path(sim_dir)


class SimulationRunner:
    """
    Simulation Runner

    Responsible for:
    1. Running OASIS simulations in background processes
    2. Parsing run logs and recording actions for each Agent
    3. Providing real-time status query interfaces
    4. Supporting pause/stop/resume operations
    """
    
    # Storage directory for run state
    RUN_STATE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )
    
    # Script directory
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../scripts'
    )
    
    # In-memory run state
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}  # Store stdout file handles
    _stderr_files: Dict[str, Any] = {}  # Store stderr file handles
    
    # Graph memory update configuration
    _graph_memory_enabled: Dict[str, bool] = {}  # simulation_id -> enabled
    
    @classmethod
    def get_console_log(cls, simulation_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Read raw stdout/stderr capture from the OASIS subprocess.

        The subprocess in start_simulation pipes stdout+stderr to
        `{sim_dir}/simulation.log`. This reader returns an incremental slice
        for client-side polling (same shape as ReportManager.get_console_log).

        Delegates I/O to :func:`~app.services.sim.run_state_store.read_console_log`.
        """
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
        """Load run state from file.

        Delegates to :func:`~app.services.sim.run_state_store.load_run_state`.
        """
        return load_run_state(simulation_id, cls.RUN_STATE_DIR)
    
    @classmethod
    def _save_run_state(cls, state: SimulationRunState) -> None:
        """Save run state to file.

        Delegates pure I/O to :func:`~app.services.sim.run_state_store.save_run_state`.
        Side-effects (event-bus publish, run-registry sync) are passed as
        callbacks so ``run_state_store`` stays free of those imports.
        """
        def _publish(data: Dict[str, Any]) -> None:
            # Issue #9 Phase B — mirror the snapshot to the bus so live
            # subscribers (frontend SSE in Phase C, future analytics workers)
            # get a push instead of polling run_state.json.
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
                    artifacts={
                        "simulation": {
                            "run_state": os.path.join(
                                cls.RUN_STATE_DIR, simulation_id, "run_state.json"
                            ),
                            "simulation_log": os.path.join(
                                cls.RUN_STATE_DIR, simulation_id, "simulation.log"
                            ),
                        }
                    },
                )

        _save_run_state_fn(
            state,
            cls.RUN_STATE_DIR,
            event_bus_publish=_publish,
            run_registry_sync=_registry_sync,
        )
        # Keep in-memory cache in sync
        cls._run_states[state.simulation_id] = state
    
    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int = None,  # Maximum simulation rounds (optional, for truncating long simulations)
        enable_graph_memory_update: bool = False,  # Whether to update activities to the graph
        graph_id: str = None,  # Graph ID (required when enabling graph updates)
        storage: Any = None  # GraphStorage instance (required if enable_graph_memory_update)
    ) -> SimulationRunState:
        """
        Start simulation

        Args:
            simulation_id: Simulation ID
            platform: Platform to run (twitter/reddit/parallel)
            max_rounds: Maximum simulation rounds (optional, for truncating long simulations)
            enable_graph_memory_update: Whether to dynamically update Agent activities to the graph
            graph_id: Graph ID (required when enabling graph updates)

        Returns:
            SimulationRunState
        """
        # Check if already running
        existing = cls.get_run_state(simulation_id)
        if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
            raise ValueError(f"Simulation already running: {simulation_id}")
        
        # Load simulation config
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        store = _store()

        if not store.exists(simulation_id, "simulation_config"):
            raise ValueError("Simulation config does not exist, call /prepare endpoint first")

        # Reset control_state.json so a previous paused/stop_requested flag from a
        # killed run does not silently freeze the new subprocess on round 0.
        try:
            from .simulation_ipc import write_control_state
            write_control_state(simulation_id, paused=False, stop_requested=False)
        except Exception as ctrl_err:
            logger.warning(f"Could not reset control_state.json before start: {ctrl_err}")

        config = store.read_json(simulation_id, "simulation_config", default=None)
        if not config:
            raise ValueError("Simulation config is unreadable")
        
        # Initialize run state
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)
        
        # If max_rounds specified, truncate
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(f"Rounds truncated: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
        
        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )
        
        cls._save_run_state(state)
        
        # If graph memory update enabled, create updater
        if enable_graph_memory_update:
            if not graph_id:
                raise ValueError("Must provide graph_id when enabling graph memory update")
            
            try:
                if not storage:
                    raise ValueError("Must provide storage (GraphStorage) when enabling graph memory update")
                GraphMemoryManager.create_updater(simulation_id, graph_id, storage)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(f"Graph memory update enabled: simulation_id={simulation_id}, graph_id={graph_id}")
            except Exception as e:
                logger.error(f"Failed to create graph memory updater: {e}")
                cls._graph_memory_enabled[simulation_id] = False
        else:
            cls._graph_memory_enabled[simulation_id] = False
        
        # Determine which script to run (scripts located in backend/scripts/ directory)
        if platform == "twitter":
            script_name = "run_twitter_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_reddit_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True
        
        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)
        
        if not os.path.exists(script_path):
            raise ValueError(f"Script does not exist: {script_path}")
        
        # Create action queue
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue
        
        # Start simulation process
        try:
            # Build run command with full paths
            # New log structure:
            #   twitter/actions.jsonl - Twitter action log
            #   reddit/actions.jsonl  - Reddit action log
            #   simulation.log        - Main process log

            # OASIS subprocess scripts expect a real filesystem path for --config;
            # the artifact store is Flask-side only.
            config_path = os.path.join(sim_dir, "simulation_config.json")
            cmd = [
                sys.executable,  # Python interpreter
                script_path,
                "--config", config_path,  # Use full config file path
            ]
            
            # If max_rounds specified, add to command-line arguments
            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])
            
            # Create main log file to avoid stdout/stderr pipe buffer overflow
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, 'w', encoding='utf-8')
            
            # Set subprocess environment variables to ensure UTF-8 encoding on Windows
            # This fixes third-party libraries (like OASIS) not specifying encoding when reading files
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'  # Python 3.7+ support, make all open() use UTF-8 by default
            env['PYTHONIOENCODING'] = 'utf-8'  # Ensure stdout/stderr use UTF-8
            # Sub-Slice 21: OASIS-DB pro Sim ins schreibbare uploads/-Volume
            # legen, sonst crashed OASIS auf read-only-FS beim Anlegen von
            # site-packages/oasis/data/.
            _inject_oasis_db_env(env, sim_dir)
            
            # Set working directory to simulation directory (database files etc. will be generated here)
            # Use start_new_session=True to create new process group, ensuring all child processes can be terminated via os.killpg
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,  # stderr also written to same file
                text=True,
                encoding='utf-8',  # Explicitly specify encoding
                bufsize=1,
                env=env,  # Pass environment variables with UTF-8 settings
                start_new_session=True,  # Create new process group, ensure all related processes terminate when server closes
            )
            
            # Save file handle for later closing
            cls._stdout_files[simulation_id] = main_log_file
            cls._stderr_files[simulation_id] = None  # No longer need separate stderr
            
            state.process_pid = process.pid
            state.runner_status = RunnerStatus.RUNNING
            cls._processes[simulation_id] = process
            cls._save_run_state(state)
            
            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=cls._monitor_simulation,
                args=(simulation_id,),
                daemon=True
            )
            monitor_thread.start()
            cls._monitor_threads[simulation_id] = monitor_thread
            
            logger.info(
                f"Simulation started successfully: {simulation_id}, pid={process.pid}, platform={platform}",
                extra={'simulation_id': simulation_id},
            )
            
        except Exception as e:
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
            raise
        
        return state
    
    @classmethod
    def _monitor_simulation(cls, simulation_id: str):
        """Delegate to ``monitor.monitor_simulation``.

        M11 Phase 5 PR 3 — body extracted; wrapper kept so that
        ``threading.Thread(target=cls._monitor_simulation, args=(simulation_id,))``
        continues to work unchanged and Monkeypatch-Stubs still apply.
        """
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
    def _read_action_log(
        cls,
        log_path: str,
        position: int,
        state: SimulationRunState,
        platform: str,
    ) -> int:
        """Delegate to ``action_log_reader.read_action_log_chunk``.

        M11 Phase 5 PR 2 — body extracted; wrapper kept for Monkeypatch-compat.
        """
        return _read_action_log_chunk(
            log_path,
            position,
            state,
            platform,
            graph_memory_enabled=cls._graph_memory_enabled.get(state.simulation_id, False),
        )
    
    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """Delegate to ``action_log_reader.check_all_platforms_completed``.

        M11 Phase 5 PR 2 — body extracted; wrapper kept for Monkeypatch-compat.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        return _check_all_platforms_completed_fn(state, base_dir=sim_dir)
    
    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 10):
        """
        Cross-platform terminate process and its child processes
        
        Args:
            process: Process to terminate
            simulation_id: Simulation ID (for logging)
            timeout: Timeout for process exit (seconds)
        """
        if IS_WINDOWS:
            # Windows: Use taskkill command to terminate process tree
            # /F = force terminate, /T = terminate process tree (including child processes)
            logger.info(f"Terminate process tree (Windows): simulation={simulation_id}, pid={process.pid}")
            try:
                # Try graceful termination first
                subprocess.run(
                    ['taskkill', '/PID', str(process.pid), '/T'],
                    capture_output=True,
                    timeout=5
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Force terminate
                    logger.warning(f"Process not responding, force terminating: {simulation_id}")
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(process.pid), '/T'],
                        capture_output=True,
                        timeout=5
                    )
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"taskkill failed, trying terminate: {e}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        else:
            # Unix: Use process group termination
            # Since start_new_session=True, process group ID equals main process PID
            pgid = os.getpgid(process.pid)
            logger.info(f"Terminate process group (Unix): simulation={simulation_id}, pgid={pgid}")
            
            # First send SIGTERM to the entire process group
            os.killpg(pgid, signal.SIGTERM)
            
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # If still not ended after timeout, force send SIGKILL
                logger.warning(f"Process group not responding to SIGTERM, force terminating: {simulation_id}")
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)
    
    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """Stop simulation"""
        state = cls.get_run_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation does not exist: {simulation_id}")
        
        if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
            raise ValueError(f"Simulation not running: {simulation_id}, status={state.runner_status}")
        
        state.runner_status = RunnerStatus.STOPPING
        cls._save_run_state(state)
        
        # Terminate process
        process = cls._processes.get(simulation_id)
        if process and process.poll() is None:
            try:
                cls._terminate_process(process, simulation_id)
            except ProcessLookupError:
                # Process no longer exists
                pass
            except Exception as e:
                logger.error(f"Failed to terminate process group: {simulation_id}, error={e}")
                # Fallback to direct process termination
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
        
        state.runner_status = RunnerStatus.STOPPED
        state.twitter_running = False
        state.reddit_running = False
        state.completed_at = datetime.now().isoformat()
        cls._save_run_state(state)
        
        # Stop graph memory updater
        if cls._graph_memory_enabled.get(simulation_id, False):
            try:
                GraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"Graph memory update stopped: simulation_id={simulation_id}")
            except Exception as e:
                logger.error(f"Failed to stop graph memory updater: {e}")
            cls._graph_memory_enabled.pop(simulation_id, None)
        
        logger.info(
            f"Simulation stopped: {simulation_id}",
            extra={'simulation_id': simulation_id},
        )
        return state
    
    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None,
    ) -> List[AgentAction]:
        """Delegate to ``action_log_reader.read_actions_from_file``.

        M11 Phase 5 PR 2 — body extracted; wrapper kept for Monkeypatch-compat.
        """
        return _read_actions_from_file_fn(
            file_path,
            default_platform=default_platform,
            platform_filter=platform_filter,
            agent_id=agent_id,
            round_num=round_num,
        )
    
    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None,
    ) -> List[AgentAction]:
        """Delegate to ``action_log_reader.get_all_actions``.

        M11 Phase 5 PR 2 — body extracted; wrapper kept for Monkeypatch-compat
        (``monkeypatch.setattr(SimulationRunner, "get_all_actions", …)``).
        """
        return _get_all_actions_fn(
            simulation_id,
            cls.RUN_STATE_DIR,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num,
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
        """Delegate to ``action_log_reader.get_actions``.

        M11 Phase 5 PR 2 — body extracted; wrapper kept for Monkeypatch-compat.
        """
        return _get_actions_fn(
            simulation_id,
            cls.RUN_STATE_DIR,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num,
        )
    
    @classmethod
    def get_timeline(
        cls,
        simulation_id: str,
        start_round: int = 0,
        end_round: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to ``monitor.get_timeline``.

        M11 Phase 5 PR 3 — body extracted; wrapper kept for Monkeypatch-compat.
        """
        return _get_timeline_fn(
            simulation_id,
            cls.RUN_STATE_DIR,
            start_round=start_round,
            end_round=end_round,
        )
    
    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """Delegate to ``monitor.get_agent_stats``.

        M11 Phase 5 PR 3 — body extracted; wrapper kept for Monkeypatch-compat.
        """
        return _get_agent_stats_fn(simulation_id, cls.RUN_STATE_DIR)
    
    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Clean up simulation run logs (for force restart).

        Delegates file deletion to
        :func:`~app.services.sim.run_state_store.cleanup_run_logs` and
        additionally evicts the in-memory run-state cache entry.

        Note: Does not delete config files (simulation_config.json) and profile files.

        Args:
            simulation_id: Simulation ID

        Returns:
            Cleanup result information
        """
        result = cleanup_run_logs(simulation_id, cls.RUN_STATE_DIR)

        # Evict in-memory cache so next get_run_state() re-reads from disk
        cls._run_states.pop(simulation_id, None)

        return result
    
    # Flag to prevent duplicate cleanup
    _cleanup_done = False
    
    @classmethod
    def cleanup_all_simulations(cls):
        """
        Clean up all running simulation processes
        
        Called when server closes, ensures all child processes are terminated
        """
        # Prevent duplicate cleanup
        if cls._cleanup_done:
            return
        cls._cleanup_done = True
        
        # Check if there is content to clean (avoid empty process printing useless logs)
        has_processes = bool(cls._processes)
        has_updaters = bool(cls._graph_memory_enabled)
        
        if not has_processes and not has_updaters:
            return  # No content to clean, return silently
        
        logger.info("Cleaning up all simulation processes...")
        
        # First stop all graph memory updaters (stop_all prints logs internally)
        try:
            GraphMemoryManager.stop_all()
        except Exception as e:
            logger.error(f"Failed to stop graph memory updater: {e}")
        cls._graph_memory_enabled.clear()
        
        # Copy dict to avoid modification during iteration
        processes = list(cls._processes.items())
        
        for simulation_id, process in processes:
            try:
                if process.poll() is None:  # Process still running
                    logger.info(f"Terminate simulation process: {simulation_id}, pid={process.pid}")
                    
                    try:
                        # Use cross-platform process termination method
                        cls._terminate_process(process, simulation_id, timeout=5)
                    except (ProcessLookupError, OSError):
                        # Process may no longer exist, try direct termination
                        try:
                            process.terminate()
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()
                    
                    # Update run_state.json
                    state = cls.get_run_state(simulation_id)
                    if state:
                        state.runner_status = RunnerStatus.STOPPED
                        state.twitter_running = False
                        state.reddit_running = False
                        state.completed_at = datetime.now().isoformat()
                        state.error = "Server closed, simulation terminated"
                        cls._save_run_state(state)
                    
                    # Also update state.json, set status to stopped
                    try:
                        store = _store()
                        if store.exists(simulation_id, "state"):
                            state_data = store.read_json(simulation_id, "state", default=None)
                            if state_data:
                                state_data['status'] = 'stopped'
                                state_data['updated_at'] = datetime.now().isoformat()
                                store.write_json(simulation_id, "state", state_data)
                                logger.info(f"Updated state.json status to stopped: {simulation_id}")
                        else:
                            logger.warning(f"state.json does not exist for {simulation_id}")
                    except Exception as state_err:
                        logger.warning(f"Failed to update state.json: {simulation_id}, error={state_err}")
                        
            except Exception as e:
                logger.error(f"Failed to clean up process: {simulation_id}, error={e}")
        
        # Clean up file handles
        for simulation_id, file_handle in list(cls._stdout_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stdout_files.clear()
        
        for simulation_id, file_handle in list(cls._stderr_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stderr_files.clear()
        
        # Clean up in-memory state
        cls._processes.clear()
        cls._action_queues.clear()
        
        logger.info("Simulation process cleanup completed")
    
    @classmethod
    def register_cleanup(cls):
        """
        Register cleanup function
        
        Called when Flask app starts, ensures all simulation processes are cleaned when server closes
        """
        global _cleanup_registered
        
        if _cleanup_registered:
            return
        
        # In Flask debug mode, only register cleanup in reloader child process (process actually running the app)
        # WERKZEUG_RUN_MAIN=true indicates it is a reloader child process
        # If not in debug mode, no such environment variable, also need to register
        is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('WERKZEUG_RUN_MAIN') is not None
        
        # In debug mode, only register in reloader child process; always register in non-debug mode
        if is_debug_mode and not is_reloader_process:
            _cleanup_registered = True  # Mark as registered, prevent child process from trying again
            return
        
        # Save original signal handler
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        # SIGHUP only exists on Unix systems (macOS/Linux), not on Windows
        original_sighup = None
        has_sighup = hasattr(signal, 'SIGHUP')
        if has_sighup:
            original_sighup = signal.getsignal(signal.SIGHUP)
        
        def cleanup_handler(signum=None, frame=None):
            """Signal handler: clean up simulation processes first, then call original handler"""
            # Only print logs if there are processes to clean
            if cls._processes or cls._graph_memory_enabled:
                logger.info(f"Received signal {signum}, starting cleanup...")
            cls.cleanup_all_simulations()
            
            # Call original signal handler, let Flask exit normally
            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif has_sighup and signum == signal.SIGHUP:
                # SIGHUP: Sent when terminal closes
                if callable(original_sighup):
                    original_sighup(signum, frame)
                else:
                    # Default behavior: exit normally
                    sys.exit(0)
            else:
                # If original handler not callable (such as SIG_DFL), use default behavior
                raise KeyboardInterrupt
        
        # Register atexit handler (as fallback)
        atexit.register(cls.cleanup_all_simulations)
        
        # Register signal handler (only in main thread)
        try:
            # SIGTERM: default signal for kill command
            signal.signal(signal.SIGTERM, cleanup_handler)
            # SIGINT: Ctrl+C
            signal.signal(signal.SIGINT, cleanup_handler)
            # SIGHUP: terminal close (Unix only)
            if has_sighup:
                signal.signal(signal.SIGHUP, cleanup_handler)
        except ValueError:
            # Not in main thread, can only use atexit
            logger.warning("Cannot register signal handler (not in main thread), only using atexit")
        
        _cleanup_registered = True
    
    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """
        Get list of all running simulation IDs
        """
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running
    
    # ============== Interview functionality ==============
    
    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        Check if simulation environment is alive (can receive Interview commands)

        Args:
            simulation_id: Simulation ID

        Returns:
            True means environment is alive, False means environment is closed
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return False

        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Get detailed status information of simulation environment

        Args:
            simulation_id: Simulation ID

        Returns:
            Status details dict, contains status, twitter_available, reddit_available, timestamp
        """
        default_status = {
            "status": "stopped",
            "twitter_available": False,
            "reddit_available": False,
            "timestamp": None
        }

        store = _store()
        status = store.read_json(simulation_id, "env_status", default=None)
        if not status:
            return default_status
        return {
            "status": status.get("status", "stopped"),
            "twitter_available": status.get("twitter_available", False),
            "reddit_available": status.get("reddit_available", False),
            "timestamp": status.get("timestamp")
        }

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Interview single Agent

        Args:
            simulation_id: Simulation ID
            agent_id: Agent ID
            prompt: Interview question
            platform: Specify platform (optional)
                - "twitter": only interview Twitter platform
                - "reddit": only interview Reddit platform
                - None: interview both platforms simultaneously in dual-platform simulations, return integrated results
            timeout: Timeout (seconds)

        Returns:
            Interview result dict

        Raises:
            ValueError: Simulation does not exist or environment not running
            TimeoutError: Timeout waiting for response
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulation does not exist: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"Simulation environment not running or closed, cannot execute Interview: {simulation_id}")

        logger.info(f"Send Interview command: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}")

        response = ipc_client.send_interview(
            agent_id=agent_id,
            prompt=prompt,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Batch interview multiple Agents

        Args:
            simulation_id: Simulation ID
            interviews: List of interviews, each element contains {"agent_id": int, "prompt": str, "platform": str(optional)}
            platform: Default platform (optional, overridden by each interview item's platform)
                - "twitter": default only interview Twitter platform
                - "reddit": default only interview Reddit platform
                - None: interview each Agent on both platforms simultaneously in dual-platform simulations
            timeout: Timeout (seconds)

        Returns:
            Batch interview result dict

        Raises:
            ValueError: Simulation does not exist or environment not running
            TimeoutError: Timeout waiting for response
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulation does not exist: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"Simulation environment not running or closed, cannot execute Interview: {simulation_id}")

        logger.info(f"Send batch Interview command: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}")

        response = ipc_client.send_batch_interview(
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: str = None,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        Interview all Agents (global interview)

        Interview all Agents in the simulation using the same question

        Args:
            simulation_id: Simulation ID
            prompt: Interview question (all Agents use the same question)
            platform: Specify platform (optional)
                - "twitter": only interview Twitter platform
                - "reddit": only interview Reddit platform
                - None: interview each Agent on both platforms simultaneously in dual-platform simulations
            timeout: Timeout (seconds)

        Returns:
            Global interview result dict
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulation does not exist: {simulation_id}")

        # Get all Agent information from config file
        store = _store()
        if not store.exists(simulation_id, "simulation_config"):
            raise ValueError(f"Simulation config does not exist: {simulation_id}")

        config = store.read_json(simulation_id, "simulation_config", default=None)
        if not config:
            raise ValueError(f"Simulation config is unreadable: {simulation_id}")

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise ValueError(f"No agents in simulation config: {simulation_id}")

        # Build batch interview list
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({
                    "agent_id": agent_id,
                    "prompt": prompt
                })

        logger.info(f"Send global Interview command: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}")

        return cls.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )
    
    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Close simulation environment (not stop simulation process)
        
        Send close environment command to simulation to gracefully exit command wait mode
        
        Args:
            simulation_id: Simulation ID
            timeout: Timeout (seconds)
            
        Returns:
            Operation result dict
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulation does not exist: {simulation_id}")
        
        ipc_client = SimulationIPCClient(sim_dir)
        
        if not ipc_client.check_env_alive():
            return {
                "success": True,
                "message": "Environment already closed"
            }
        
        logger.info(f"Send close environment command: simulation_id={simulation_id}")
        
        try:
            response = ipc_client.send_close_env(timeout=timeout)
            
            return {
                "success": response.status.value == "completed",
                "message": "Close environment command sent",
                "result": response.result,
                "timestamp": response.timestamp
            }
        except TimeoutError:
            # Timeout may be because environment is closing
            return {
                "success": True,
                "message": "Close environment command sent (timeout waiting for response, environment may be closing)"
            }
    
    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get Interview history from single database"""
        import sqlite3
        
        if not os.path.exists(db_path):
            return []
        
        results = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if agent_id is not None:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview' AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))
            else:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            for user_id, info_json, created_at in cursor.fetchall():
                try:
                    info = json.loads(info_json) if info_json else {}
                except json.JSONDecodeError:
                    info = {"raw": info_json}
                
                results.append({
                    "agent_id": user_id,
                    "response": info.get("response", info),
                    "prompt": info.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name
                })
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to read Interview history ({platform_name}): {e}")
        
        return results

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get Interview history records (read from database)
        
        Args:
            simulation_id: Simulation ID
            platform: Platform type (reddit/twitter/None)
                - "reddit": only get Reddit platform history
                - "twitter": only get Twitter platform history
                - None: get all history from both platforms
            agent_id: Specify Agent ID (optional, only get history for that Agent)
            limit: Return count limit per platform
            
        Returns:
            Interview history records list
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        results = []
        
        # Determine platforms to query
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # When platform not specified, query both platforms
            platforms = ["twitter", "reddit"]
        
        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = cls._get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit
            )
            results.extend(platform_results)
        
        # Sort by time in descending order
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # If queried multiple platforms, limit total count
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]
        
        return results
