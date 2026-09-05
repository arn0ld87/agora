"""
Subprocess lifecycle management for OASIS simulations.

Extracted from ``simulation_runner.py`` (M11 Phase 5 PR 5).
``simulation_runner.py`` keeps thin delegation class-methods for backward-compat.

Design constraints:
- No import of ``simulation_runner.py`` (avoids circular import).
- Mutable class-level dicts are passed by reference as keyword arguments.
  Python dicts are passed by reference, so mutations are visible to the caller.
- ``save_state`` is a callable so state can be persisted without importing
  ``SimulationRunner``.
- atexit / signal handler registration is self-contained; the cleanup action
  is injected as ``cleanup_callable`` to decouple from the class.

Security — Subprozess-Env-Whitelist (Code-Review 2026-05-17 §1.6):
    ``os.environ.copy()`` würde das vollständige Prozess-Environment an den
    OASIS-Subprozess vererben — damit auch Secrets wie ``SECRET_KEY``,
    ``AGORA_AUTH_TOKEN``, ``NEO4J_PASSWORD``, ``LLM_API_KEY`` und
    ``AGORA_FERNET_KEY``. Stattdessen wird nur die explizite Whitelist
    ``SAFE_ENV_KEYS`` übernommen. LLM-Credentials werden ausschließlich
    via ``runtime_env`` (Parameter von ``start_simulation``) übergeben,
    da die OASIS-Skripte diese aus dem Env lesen müssen.
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime
from queue import Queue
from typing import Any, Callable, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from ...llm.providers.codex_cli import CLI_TRANSPORT_VALUE, TRANSPORT_ENV_KEY
from ...observability import sim_active_gauge, sim_counter
from ...utils.logger import get_logger
from .run_state_store import RunnerStatus, SimulationRunState

_tracer = trace.get_tracer(__name__)

logger = get_logger("agora.process_manager")

_SAFE_SIMULATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _validate_simulation_id(simulation_id: str) -> None:
    if not _SAFE_SIMULATION_ID_RE.fullmatch(simulation_id):
        raise ValueError("Invalid simulation_id")


def _resolve_child_path(base_dir: str, child_name: str, *, kind: str) -> Path:
    base = Path(base_dir).expanduser().resolve()
    child = (base / child_name).resolve()
    try:
        child.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Invalid {kind} path") from exc
    return child

# ---------------------------------------------------------------------------
# Subprozess-Env-Whitelist (Code-Review 2026-05-17 §1.6)
# ---------------------------------------------------------------------------
# Nur diese Keys werden aus os.environ in den OASIS-Subprozess vererbt.
# Secrets (SECRET_KEY, AGORA_AUTH_TOKEN, NEO4J_PASSWORD, LLM_API_KEY,
# AGORA_FERNET_KEY) werden bewusst NICHT weitergegeben. LLM-Credentials
# kommen ausschließlich über den ``runtime_env``-Parameter.
#
# Optionale Connection-Keys:
# - ``REDIS_URL``: enthaelt potenziell ein Passwort (Format
#   ``redis://:pw@host:port/db``). Wir lassen es bewusst zu, weil die
#   Redis-IPC-Bridge (``scripts/subprocess_redis_bridge.py``) sonst im
#   Subprozess inaktiv bleibt. Wer das nicht will, leert REDIS_URL vor
#   dem ``start_simulation``-Call.
# - ``HF_TOKEN``: Hugging-Face-Authentifizierung fuer private/Gated
#   Models (z.B. ``Twitter/twhin-bert-base`` ist zwar public, aber
#   Custom-Mirrors koennen Auth verlangen). Public Models funktionieren
#   ohne Token.
# - ``AGORA_CODEX_CLI_BIN`` / ``AGORA_CODEX_CLI_TIMEOUT_SECONDS``: Pfad und
#   Timeout der Codex-CLI (Issue #1423). Kein Secret — die CLI
#   authentifiziert ueber die lokale ``codex login``-Session, nicht ueber
#   einen Key. Ohne diese Keys faellt der Subprozess auf ``codex`` im PATH
#   und 180 s zurueck, was fuer den Regelfall stimmt.
SAFE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PATH",
        "PYTHONPATH",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "TZ",
        "LLM_BASE_URL",
        "LLM_MODEL_NAME",
        "LLM_MAX_OUTPUT_TOKENS",
        "OLLAMA_THINKING",
        "REDIS_URL",
        "HF_TOKEN",
        "AGORA_CODEX_CLI_BIN",
        "AGORA_CODEX_CLI_TIMEOUT_SECONDS",
    }
)

def _build_subprocess_env(
    runtime_env: Optional[Dict[str, str]], sim_dir: Any
) -> Dict[str, str]:
    """Env für den OASIS-Subprozess — Whitelist-only (Code-Review 2026-05-17 §1.6).

    Nur explizit erlaubte Keys aus ``os.environ``; Secrets wie SECRET_KEY,
    AGORA_AUTH_TOKEN oder NEO4J_PASSWORD werden bewusst NICHT vererbt.
    ``runtime_env``-Werte kommen immer mit und überschreiben Whitelist-Werte
    (enthält u. a. LLM_API_KEY und OPENAI_API_KEY für den Subprozess).

    Aus ``start_simulation`` extrahiert, als der CLI-Sonderfall unten die
    Funktion über das radon-Gate (MAI-17) gehoben hätte.
    """
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_KEYS}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if runtime_env:
        env.update({k: v for k, v in runtime_env.items() if v})
    # Issue #1423: Bei CLI-Transport (codex_cli) darf das aus der Whitelist
    # geerbte ``LLM_BASE_URL`` NICHT stehen bleiben. Der Provider hat keinen
    # HTTP-Endpunkt; das geerbte Feld ist die ``.env``-URL des Backends, und
    # der Subprozess schickte das geroutete Modell genau dorthin (beobachtet:
    # ``gpt-5.6-luna`` an ``api.minimax.io`` → HTTP 400 (2013)). Das Signal
    # setzt ``build_route_subprocess_env`` anhand von
    # ``ProviderConnectionDefinition.transport``.
    if env.get(TRANSPORT_ENV_KEY, "").strip().lower() == CLI_TRANSPORT_VALUE:
        env.pop("LLM_BASE_URL", None)
    # Sub-Slice 21: OASIS-DB pro Sim ins schreibbare uploads/-Volume
    _inject_oasis_db_env(env, str(sim_dir))
    return env


# Flag whether cleanup function is registered
_cleanup_registered = False

# Platform detection
IS_WINDOWS = sys.platform == "win32"

# Sub-Slice 21 — OASIS-DB-Pfad pro Sim, damit OASIS keine DB ins
# read-only Site-Packages-Verzeichnis schreibt.
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


def terminate_process(
    process: subprocess.Popen,  # type: ignore[type-arg]
    simulation_id: str,
    timeout: int = 10,
) -> None:
    """Cross-platform: terminate a simulation process and its children.

    Args:
        process:       The Popen object to terminate.
        simulation_id: Simulation ID (for logging only).
        timeout:       Seconds to wait for graceful exit before SIGKILL.
    """
    if IS_WINDOWS:
        # Windows: Use taskkill command to terminate process tree
        # /F = force terminate, /T = terminate process tree (including child processes)
        logger.info(
            f"Terminate process tree (Windows): simulation={simulation_id}, pid={process.pid}"
        )
        try:
            # Try graceful termination first
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T"],
                capture_output=True,
                timeout=5,
            )
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Force terminate
                logger.warning(
                    f"Process not responding, force terminating: {simulation_id}"
                )
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(process.pid), "/T"],
                    capture_output=True,
                    timeout=5,
                )
                process.wait(timeout=5)
        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
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
        logger.info(
            f"Terminate process group (Unix): simulation={simulation_id}, pgid={pgid}"
        )

        # First send SIGTERM to the entire process group
        os.killpg(pgid, signal.SIGTERM)

        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # If still not ended after timeout, force send SIGKILL
            logger.warning(
                f"Process group not responding to SIGTERM, force terminating: {simulation_id}"
            )
            os.killpg(pgid, signal.SIGKILL)
            process.wait(timeout=5)


def start_simulation(
    simulation_id: str,
    platform: str,
    *,
    run_state_dir: str,
    scripts_dir: str,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
    action_queues: Dict[str, Queue],  # type: ignore[type-arg]
    monitor_threads: Dict[str, threading.Thread],
    stdout_files: Dict[str, Any],
    stderr_files: Dict[str, Any],
    graph_memory_enabled: Dict[str, bool],
    get_run_state: Callable[[str], Optional[SimulationRunState]],
    save_state: Callable[[SimulationRunState], None],
    on_monitor_start: Callable[[str], None],
    write_control_state: Callable[..., None],
    get_config: Callable[[str], Optional[Dict[str, Any]]],
    config_exists: Callable[[str], bool],
    setup_graph_memory: Callable[[str], None],
    max_rounds: Optional[int] = None,
    runtime_env: Optional[Dict[str, str]] = None,
) -> SimulationRunState:
    """Start an OASIS simulation: validate, init state, launch subprocess, start monitor.

    All mutable class-level dicts from ``SimulationRunner`` are passed by
    reference — mutations here are visible to the caller.

    Args:
        simulation_id:          Simulation ID.
        platform:               ``twitter`` / ``reddit`` / ``parallel``.
        run_state_dir:          ``SimulationRunner.RUN_STATE_DIR``.
        scripts_dir:            ``SimulationRunner.SCRIPTS_DIR``.
        processes:              ``SimulationRunner._processes`` (mutated).
        action_queues:          ``SimulationRunner._action_queues`` (mutated).
        monitor_threads:        ``SimulationRunner._monitor_threads`` (mutated).
        stdout_files:           ``SimulationRunner._stdout_files`` (mutated).
        stderr_files:           ``SimulationRunner._stderr_files`` (mutated).
        graph_memory_enabled:   ``SimulationRunner._graph_memory_enabled``.
        get_run_state:          Callable to load current run state.
        save_state:             Callable to persist run state.
        on_monitor_start:       Callable(simulation_id) to spawn monitor thread.
        write_control_state:    Callable to reset control_state.json.
        get_config:             Callable(simulation_id) → config dict or None.
        config_exists:          Callable(simulation_id) → bool.
        setup_graph_memory:     Callable(simulation_id) that configures graph
                                memory and mutates ``graph_memory_enabled``.
        max_rounds:             Optional round cap (passed to script CLI).

    Returns:
        Updated ``SimulationRunState`` (status RUNNING).

    Raises:
        ValueError: if already running, config missing, or script not found.
    """
    _validate_simulation_id(simulation_id)

    # Check if already running
    existing = get_run_state(simulation_id)
    if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
        raise ValueError(f"Simulation already running: {simulation_id}")

    if not config_exists(simulation_id):
        raise ValueError("Simulation config does not exist, call /prepare endpoint first")

    # Reset control_state.json so a previous paused/stop_requested flag does not
    # silently freeze the new subprocess on round 0.
    try:
        write_control_state(simulation_id, paused=False, stop_requested=False)
    except Exception as ctrl_err:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(f"Could not reset control_state.json before start: {ctrl_err}")

    config = get_config(simulation_id)
    if not config:
        raise ValueError("Simulation config is unreadable")

    # Derive total rounds from time config
    time_config = config.get("time_config", {})
    total_hours = time_config.get("total_simulation_hours", 72)
    minutes_per_round = time_config.get("minutes_per_round", 30)
    total_rounds = int(total_hours * 60 / minutes_per_round)

    if max_rounds is not None and max_rounds > 0:
        original_rounds = total_rounds
        total_rounds = min(total_rounds, max_rounds)
        if total_rounds < original_rounds:
            logger.info(
                f"Rounds truncated: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})"
            )

    state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.STARTING,
        total_rounds=total_rounds,
        total_simulation_hours=total_hours,
        started_at=datetime.now().isoformat(),
    )

    save_state(state)

    # Configure graph memory via injected callback
    setup_graph_memory(simulation_id)

    sim_dir = _resolve_child_path(run_state_dir, simulation_id, kind="simulation")

    # Determine which script to run
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

    script_path = _resolve_child_path(scripts_dir, script_name, kind="script")

    if not script_path.is_file():
        raise ValueError(f"Script does not exist: {script_path}")

    # Create action queue
    action_queue: Queue = Queue()  # type: ignore[type-arg]
    action_queues[simulation_id] = action_queue

    try:
        # Build run command
        config_path = sim_dir / "simulation_config.json"
        cmd = [sys.executable, str(script_path), "--config", str(config_path)]

        if max_rounds is not None and max_rounds > 0:
            cmd.extend(["--max-rounds", str(max_rounds)])

        # Create main log file
        main_log_path = sim_dir / "simulation.log"
        main_log_file = open(main_log_path, "w", encoding="utf-8")

        env = _build_subprocess_env(runtime_env, sim_dir)

        # Slice 1c: Trace-Context via W3C-traceparent in den Subprozess propagieren.
        with _tracer.start_as_current_span("agora.subprocess.spawn") as span:
            span.set_attribute("agora.simulation.id", simulation_id)
            span.set_attribute("agora.subprocess.cmd", " ".join(cmd))
            carrier: dict[str, str] = {}
            TraceContextTextMapPropagator().inject(carrier)
            traceparent = carrier.get("traceparent", "")
            if traceparent:
                env["TRACEPARENT"] = traceparent

            process = subprocess.Popen(
                cmd,
                cwd=str(sim_dir),
                stdout=main_log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
                start_new_session=True,
            )

        stdout_files[simulation_id] = main_log_file
        stderr_files[simulation_id] = None

        state.process_pid = process.pid
        state.runner_status = RunnerStatus.RUNNING
        processes[simulation_id] = process
        # Slice 2b: Sim-Lifecycle-Metric — PENDING → RUNNING
        sim_active_gauge().add(1)
        sim_counter().add(1, {"status": "started"})
        save_state(state)

        # Start monitoring thread via injected callback
        on_monitor_start(simulation_id)

        logger.info(
            f"Simulation started successfully: {simulation_id}, pid={process.pid}, platform={platform}",
            extra={"simulation_id": simulation_id},
        )

    except Exception as e:
        state.runner_status = RunnerStatus.FAILED
        state.error = str(e)
        save_state(state)
        raise

    return state


def stop_simulation(
    simulation_id: str,
    *,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
    graph_memory_enabled: Dict[str, bool],
    get_run_state: Callable[[str], Optional[SimulationRunState]],
    save_state: Callable[[SimulationRunState], None],
    stop_graph_memory_updater: Callable[[str], None],
) -> SimulationRunState:
    """Stop a running simulation and clean up its process.

    Args:
        simulation_id:              Simulation ID.
        processes:                  ``SimulationRunner._processes``.
        graph_memory_enabled:       ``SimulationRunner._graph_memory_enabled``.
        get_run_state:              Callable to load current run state.
        save_state:                 Callable to persist updated state.
        stop_graph_memory_updater:  Callable(simulation_id) to stop updater.

    Returns:
        Updated ``SimulationRunState`` (status STOPPED).
    """
    state = get_run_state(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
        raise ValueError(
            f"Simulation not running: {simulation_id}, status={state.runner_status}"
        )

    state.runner_status = RunnerStatus.STOPPING
    save_state(state)

    # Terminate process
    process = processes.get(simulation_id)
    if process and process.poll() is None:
        try:
            terminate_process(process, simulation_id)
        except ProcessLookupError:
            pass
        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error(
                f"Failed to terminate process group: {simulation_id}, error={e}"
            )
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:  # noqa: BLE001 — process termination; exc discarded, kill follows
                process.kill()

    state.runner_status = RunnerStatus.STOPPED
    state.twitter_running = False
    state.reddit_running = False
    state.completed_at = datetime.now().isoformat()
    save_state(state)

    # Stop graph memory updater
    if graph_memory_enabled.get(simulation_id, False):
        try:
            stop_graph_memory_updater(simulation_id)
            logger.info(f"Graph memory update stopped: simulation_id={simulation_id}")
        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error(f"Failed to stop graph memory updater: {e}")
        graph_memory_enabled.pop(simulation_id, None)

    logger.info(
        f"Simulation stopped: {simulation_id}",
        extra={"simulation_id": simulation_id},
    )
    return state


def cleanup_all_simulations(
    *,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
    stdout_files: Dict[str, Any],
    stderr_files: Dict[str, Any],
    graph_memory_enabled: Dict[str, bool],
    action_queues: Dict[str, Any],
    get_run_state: Callable[[str], Optional[SimulationRunState]],
    save_state: Callable[[SimulationRunState], None],
    stop_all_graph_memory: Callable[[], None],
    update_store_state: Callable[[str], None],
    cleanup_done_flag: List[bool],
) -> None:
    """Terminate all running simulation processes.

    Called when the server closes; ensures all child processes are terminated.

    Args:
        processes:             ``SimulationRunner._processes``.
        stdout_files:          ``SimulationRunner._stdout_files``.
        stderr_files:          ``SimulationRunner._stderr_files``.
        graph_memory_enabled:  ``SimulationRunner._graph_memory_enabled``.
        action_queues:         ``SimulationRunner._action_queues``.
        get_run_state:         Callable to load current run state.
        save_state:            Callable to persist updated state.
        stop_all_graph_memory: Callable() to stop all graph memory updaters.
        update_store_state:    Callable(simulation_id) to update state.json.
        cleanup_done_flag:     Single-element list used as a mutable bool flag.
    """
    # Prevent duplicate cleanup
    if cleanup_done_flag[0]:
        return
    cleanup_done_flag[0] = True

    has_processes = bool(processes)
    has_updaters = bool(graph_memory_enabled)

    if not has_processes and not has_updaters:
        return

    logger.info("Cleaning up all simulation processes...")

    # Stop all graph memory updaters
    try:
        stop_all_graph_memory()
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error(f"Failed to stop graph memory updater: {e}")
    graph_memory_enabled.clear()

    # Copy dict to avoid modification during iteration
    process_list = list(processes.items())

    for simulation_id, process in process_list:
        try:
            if process.poll() is None:
                logger.info(
                    f"Terminate simulation process: {simulation_id}, pid={process.pid}"
                )

                try:
                    terminate_process(process, simulation_id, timeout=5)
                except (ProcessLookupError, OSError):
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except Exception:  # noqa: BLE001 — process termination; exc discarded, kill follows
                        process.kill()

                # Update run_state.json
                state = get_run_state(simulation_id)
                if state:
                    state.runner_status = RunnerStatus.STOPPED
                    state.twitter_running = False
                    state.reddit_running = False
                    state.completed_at = datetime.now().isoformat()
                    state.error = "Server closed, simulation terminated"
                    save_state(state)

                # Update state.json via injected callback
                try:
                    update_store_state(simulation_id)
                except Exception as state_err:  # noqa: BLE001 — exception is logged; swallowed intentionally
                    logger.warning(
                        f"Failed to update state.json: {simulation_id}, error={state_err}"
                    )

        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error(f"Failed to clean up process: {simulation_id}, error={e}")

    # Clean up file handles
    for _sim_id, file_handle in list(stdout_files.items()):
        try:
            if file_handle:
                file_handle.close()
        except Exception as exc:  # noqa: BLE001 — file handle close; exc discarded
            logger.debug("process_manager: file handle close failed, ignoring: %s", exc)
    stdout_files.clear()

    for _sim_id, file_handle in list(stderr_files.items()):
        try:
            if file_handle:
                file_handle.close()
        except Exception as exc:  # noqa: BLE001 — file handle close; exc discarded
            logger.debug("process_manager: file handle close failed, ignoring: %s", exc)
    stderr_files.clear()

    # Clean up in-memory state
    processes.clear()
    action_queues.clear()

    logger.info("Simulation process cleanup completed")


def register_cleanup(*, cleanup_callable: Callable[[], None]) -> None:
    """Register atexit and signal handlers to clean up simulation processes.

    Called when Flask app starts. The actual cleanup action is injected as
    ``cleanup_callable`` so this module remains independent of
    ``SimulationRunner``.

    Reloader-Child-Guard: In Flask debug mode, only register in the reloader
    child process (``WERKZEUG_RUN_MAIN=true``). In non-debug mode, always
    register.

    Args:
        cleanup_callable: Zero-argument callable (typically
                          ``SimulationRunner.cleanup_all_simulations``).
    """
    global _cleanup_registered

    if _cleanup_registered:
        return

    # env-only: werkzeug/subprocess intern, kein settings_layer-Kandidat
    is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    is_debug_mode = (
        os.environ.get("FLASK_DEBUG") == "1"  # env-only: werkzeug/subprocess intern
        or os.environ.get("WERKZEUG_RUN_MAIN") is not None  # env-only: werkzeug/subprocess intern
    )

    # In debug mode, only register in reloader child process;
    # always register in non-debug mode.
    if is_debug_mode and not is_reloader_process:
        _cleanup_registered = True
        return

    # Save original signal handlers
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    original_sighup = None
    has_sighup = hasattr(signal, "SIGHUP")
    if has_sighup:
        original_sighup = signal.getsignal(signal.SIGHUP)

    def cleanup_handler(signum: Any = None, frame: Any = None) -> None:
        """Signal handler: clean up simulation processes first, then forward."""
        logger.info(f"Received signal {signum}, starting cleanup...")
        cleanup_callable()

        if signum == signal.SIGINT and callable(original_sigint):
            original_sigint(signum, frame)
        elif signum == signal.SIGTERM and callable(original_sigterm):
            original_sigterm(signum, frame)
        elif has_sighup and signum == signal.SIGHUP:
            if callable(original_sighup):
                original_sighup(signum, frame)  # type: ignore[misc]
            else:
                sys.exit(0)
        else:
            raise KeyboardInterrupt

    # Register atexit handler (as fallback)
    atexit.register(cleanup_callable)

    # Register signal handler (only in main thread)
    try:
        signal.signal(signal.SIGTERM, cleanup_handler)
        signal.signal(signal.SIGINT, cleanup_handler)
        if has_sighup:
            signal.signal(signal.SIGHUP, cleanup_handler)
    except ValueError:
        logger.warning(
            "Cannot register signal handler (not in main thread), only using atexit"
        )

    _cleanup_registered = True


def terminate_run(
    run_id: str,
    *,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
    grace_period: float = 5.0,
) -> bool:
    """Beende den OASIS-Subprozess für ``run_id`` kooperativ (SIGTERM + Grace → SIGKILL).

    Idempotent: Wenn kein Prozess läuft oder der Prozess bereits beendet ist,
    wird kein Fehler geworfen und ``False`` zurückgegeben.

    Args:
        run_id:       Simulation-ID (= Prozess-Schlüssel in ``processes``).
        processes:    ``SimulationRunner._processes`` (by reference).
        grace_period: Sekunden, die nach SIGTERM gewartet wird, bevor SIGKILL
                      gesendet wird.

    Returns:
        ``True``, wenn ein laufender Prozess terminiert wurde.
        ``False``, wenn kein Prozess vorhanden oder bereits beendet war.
    """
    process = processes.get(run_id)
    if process is None or process.poll() is not None:
        return False

    timeout_int = max(1, int(grace_period))
    try:
        terminate_process(process, run_id, timeout=timeout_int)
    except ProcessLookupError:
        pass
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "terminate_run: graceful terminate failed for %s, forcing kill: %s",
            run_id,
            exc,
        )
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception as kill_err:  # noqa: BLE001 — process termination; kill_err discarded
            logger.debug("process_manager: process kill failed, ignoring: %s", kill_err)
    return True


def get_running_simulations(
    *,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
) -> List[str]:
    """Return list of simulation IDs whose subprocesses are still running.

    Args:
        processes: ``SimulationRunner._processes``.

    Returns:
        List of simulation IDs with ``process.poll() is None``.
    """
    return [sim_id for sim_id, proc in processes.items() if proc.poll() is None]
