"""Process termination and cleanup operations for simulation subprocesses."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ...utils.logger import get_logger
from .process_cancel import _write_cancel_abort
from .process_environment import _resolve_child_path
from .run_state_store import RunnerStatus, SimulationRunState

logger = get_logger("agora.process_manager")
IS_WINDOWS = sys.platform == "win32"

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


def stop_simulation(
    simulation_id: str,
    *,
    run_state_dir: str,
    processes: Dict[str, subprocess.Popen],  # type: ignore[type-arg]
    graph_memory_enabled: Dict[str, bool],
    get_run_state: Callable[[str], Optional[SimulationRunState]],
    save_state: Callable[[SimulationRunState], None],
    stop_graph_memory_updater: Callable[[str], None],
) -> SimulationRunState:
    """Stop a running simulation and clean up its process.

    Args:
        simulation_id:              Simulation ID.
        run_state_dir:              ``SimulationRunner.RUN_STATE_DIR``.
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

    # Nutzer-Stop-Marker (B2, Issue-Review 2026-09-07): VOR dem Terminieren
    # schreiben, damit monitor_simulation den SIGTERM-Exit (returncode -15)
    # nicht faelschlich als FAILED klassifiziert, sondern als STOPPED mit
    # termination_reason="user_stop" erkennt.
    sim_dir = _resolve_child_path(run_state_dir, simulation_id, kind="simulation")
    _write_cancel_abort(str(sim_dir), {"source": "user_stop", "ts": time.time()})

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
