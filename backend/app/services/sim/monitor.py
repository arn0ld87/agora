"""
Monitor-thread helpers and read-only timeline/stats aggregators.

Extracted from ``simulation_runner.py`` (M11 Phase 5 PR 3).
``simulation_runner.py`` keeps thin delegation class-methods for backward-compat.

Design constraints:
- No import of ``simulation_runner.py`` (avoids circular import).
- Mutable class-level dicts are passed by reference as keyword arguments.
- ``save_state`` is a callable so state can be persisted without importing
  ``SimulationRunner``.
- ``get_timeline`` / ``get_agent_stats`` are pure read functions with an
  explicit ``base_dir`` parameter instead of ``cls.RUN_STATE_DIR``.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ...observability import sim_active_gauge, sim_counter, sim_duration_histogram
from ...utils.logger import get_logger
from .action_log_reader import get_actions as _get_actions
from .action_log_reader import read_action_log_chunk
from .run_state_store import RunnerStatus, SimulationRunState

logger = get_logger("agora.monitor")

BUDGET_ABORT_FILENAME = "budget_abort.json"


def _read_budget_abort(sim_dir: str) -> Optional[Dict[str, Any]]:
    """budget_abort.json lesen (vom Subprozess-Guard oder Monitor geschrieben)."""
    import json

    path = os.path.join(sim_dir, BUDGET_ABORT_FILENAME)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_budget_abort(sim_dir: str, abort_info: Dict[str, Any]) -> None:
    """First-writer-wins — Guard und Monitor dürfen nicht überschreiben."""
    import json

    path = os.path.join(sim_dir, BUDGET_ABORT_FILENAME)
    if os.path.exists(path):
        return
    try:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(abort_info, handle)
            handle.write("\n")
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning("budget abort marker write failed: %s", exc)


def _budget_supervision(simulation_id: str, sim_dir: str) -> Optional[Dict[str, Any]]:
    """Harte Budgets im Monitor durchsetzen (Issue #764).

    Zwei Quellen: (1) der Subprozess-Guard hat budget_abort.json geschrieben
    (Token-/Kosten-/Aufruflimits an Runden-Grenzen), (2) der Monitor selbst
    prüft über den geteilten Ledger — insbesondere das Zeitbudget, das auch
    ohne Subprozess-Instrumentierung deterministisch greift.

    Bei Überschreitung: kooperativer Stop via control_state.json; die
    laufende Runde endet sauber, Teilresultate bleiben erhalten.
    """
    abort_info = _read_budget_abort(sim_dir)
    if abort_info is None:
        try:
            from ..run_budget import BudgetExceededError, RunBudgetEnforcer
            from ..run_registry import RunRegistry

            run = RunRegistry().get_latest_by_linked_id(
                "simulation_id", simulation_id, run_type="simulation_run"
            )
            if run:
                enforcer = RunBudgetEnforcer.for_run(run["run_id"])
                if enforcer is not None:
                    try:
                        enforcer.check_before_call()
                    except BudgetExceededError as exc:
                        abort_info = {
                            "dimension": exc.dimension,
                            "observed": exc.observed,
                            "threshold": exc.threshold,
                            "ts": time.time(),
                            "source": "backend-monitor",
                        }
                        _write_budget_abort(sim_dir, abort_info)
        except Exception as exc:  # noqa: BLE001 — Supervision darf Monitor nicht killen
            logger.warning("budget supervision failed for %s: %s", simulation_id, exc)
            return None

    if abort_info is not None:
        try:
            from ..simulation_ipc import write_control_state

            write_control_state(simulation_id, stop_requested=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("budget stop request failed for %s: %s", simulation_id, exc)
        return abort_info
    return None


def _compute_elapsed_seconds(started_at: Optional[str]) -> float:
    """Berechnet die vergangene Zeit seit ``started_at`` in Sekunden.

    Gibt 0.0 zurück wenn ``started_at`` fehlt oder nicht parsebar ist —
    damit Metric-Calls bei fehlerhaftem State nicht werfen.

    Args:
        started_at: ISO-8601-Zeitstempel aus ``SimulationRunState.started_at``.

    Returns:
        Vergangene Sekunden als Float (>= 0.0).
    """
    if not started_at:
        return 0.0
    try:
        start_dt = datetime.fromisoformat(started_at)
        elapsed = (datetime.now() - start_dt).total_seconds()
        return max(0.0, elapsed)
    except (ValueError, OverflowError):
        return 0.0


def monitor_simulation(
    simulation_id: str,
    *,
    run_state_dir: str,
    processes: Dict[str, subprocess.Popen],
    graph_memory_enabled: Dict[str, bool],
    action_queues: Dict[str, Any],
    stdout_files: Dict[str, Any],
    stderr_files: Dict[str, Any],
    get_run_state: Callable[[str], Optional[SimulationRunState]],
    save_state: Callable[[SimulationRunState], None],
) -> None:
    """Daemon-thread target that tails action logs and updates run state.

    All ``cls.*`` references from ``SimulationRunner._monitor_simulation`` are
    replaced by explicit keyword parameters; ``save_state`` avoids a circular
    import.
    """
    sim_dir = os.path.join(run_state_dir, simulation_id)

    # Per-platform action-log paths
    twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
    reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

    process = processes.get(simulation_id)
    state = get_run_state(simulation_id)

    if not process or not state:
        return

    twitter_position = 0
    reddit_position = 0

    try:
        while process.poll() is None:  # Process still running
            # Read Twitter action log
            if os.path.exists(twitter_actions_log):
                twitter_position = read_action_log_chunk(
                    twitter_actions_log,
                    twitter_position,
                    state,
                    "twitter",
                    graph_memory_enabled=graph_memory_enabled.get(simulation_id, False),
                )

            # Read Reddit action log
            if os.path.exists(reddit_actions_log):
                reddit_position = read_action_log_chunk(
                    reddit_actions_log,
                    reddit_position,
                    state,
                    "reddit",
                    graph_memory_enabled=graph_memory_enabled.get(simulation_id, False),
                )

            # Budget-Supervision (Issue #764): harte Limits prüfen, ggf.
            # kooperativen Stop anfordern.
            _budget_supervision(simulation_id, sim_dir)

            # Update status
            save_state(state)
            time.sleep(2)

        # After process ends, read logs one more time
        if os.path.exists(twitter_actions_log):
            read_action_log_chunk(
                twitter_actions_log,
                twitter_position,
                state,
                "twitter",
                graph_memory_enabled=graph_memory_enabled.get(simulation_id, False),
            )
        if os.path.exists(reddit_actions_log):
            read_action_log_chunk(
                reddit_actions_log,
                reddit_position,
                state,
                "reddit",
                graph_memory_enabled=graph_memory_enabled.get(simulation_id, False),
            )

        # Process ended
        exit_code = process.returncode
        elapsed_seconds = _compute_elapsed_seconds(state.started_at)

        # Budgetabbruch (Issue #764): hat Vorrang vor exit-code-Auswertung —
        # der Subprozess endet bei kooperativem Budget-Stop mit exit 0, ist
        # aber kein "completed". Budgetabbruch ≠ technischer Fehler.
        budget_abort = _read_budget_abort(sim_dir)
        if budget_abort is not None:
            state.runner_status = RunnerStatus.STOPPED
            state.completed_at = datetime.now().isoformat()
            dimension = budget_abort.get("dimension", "unknown")
            # Issue #764 (Codex P1): wenn der Subprozess beim Budget-Stop
            # trotzdem mit non-zero exit endet (Bug im Guard, race, oder
            # doppelter Marker), bleibt der RunnerStatus STOPPED und der
            # termination_reason "budget_*" korrekt — aber wir wollen den
            # exit_code sichtbar machen, damit die Diagnose nicht verloren
            # geht. Bei exit 0 verhaelt sich der Pfad exakt wie vorher.
            if exit_code != 0:
                state.error = (
                    f"budget_abort (exit_code={exit_code}): {dimension}"
                )
                logger.warning(
                    f"Simulation budget-aborted with non-zero exit: "
                    f"{simulation_id}, dimension={dimension}, exit_code={exit_code}",
                    extra={"simulation_id": simulation_id},
                )
            else:
                state.error = None
            sim_active_gauge().add(-1)
            sim_counter().add(1, {"status": "budget_abort"})
            sim_duration_histogram().record(elapsed_seconds, {"status": "budget_abort"})
            logger.info(
                f"Simulation budget-aborted: {simulation_id}, dimension={dimension}",
                extra={"simulation_id": simulation_id},
            )
            try:
                from ..run_budget import mark_budget_abort
                from ..run_registry import RunRegistry

                run = RunRegistry().get_latest_by_linked_id(
                    "simulation_id", simulation_id, run_type="simulation_run"
                )
                if run:
                    mark_budget_abort(
                        run["run_id"],
                        str(dimension),
                        int(budget_abort.get("observed", 0)),
                        int(budget_abort.get("threshold", 0)),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("budget abort registry update failed: %s", exc)
        elif exit_code == 0:
            state.runner_status = RunnerStatus.COMPLETED
            state.completed_at = datetime.now().isoformat()
            # Slice 2b: Sim-Lifecycle-Metric — RUNNING → COMPLETED
            sim_active_gauge().add(-1)
            sim_counter().add(1, {"status": "done"})
            sim_duration_histogram().record(elapsed_seconds, {"status": "done"})
            logger.info(
                f"Simulation completed: {simulation_id}",
                extra={"simulation_id": simulation_id},
            )
        else:
            state.runner_status = RunnerStatus.FAILED
            # Read error info from main log file
            main_log_path = os.path.join(sim_dir, "simulation.log")
            error_info = ""
            try:
                if os.path.exists(main_log_path):
                    with open(main_log_path, "r", encoding="utf-8") as f:
                        error_info = f.read()[-2000:]  # Take last 2000 characters
            except Exception as exc:  # noqa: BLE001 — close file handle on cleanup; exc discarded
                logger.debug("monitor: failed to read error log, continuing: %s", exc)
            state.error = f"Process exit code: {exit_code}, error: {error_info}"
            # Slice 2b: Sim-Lifecycle-Metric — RUNNING → FAILED
            sim_active_gauge().add(-1)
            sim_counter().add(1, {"status": "failed"})
            sim_duration_histogram().record(elapsed_seconds, {"status": "failed"})
            logger.error(
                f"Simulation failed: {simulation_id}, error={state.error}",
                extra={"simulation_id": simulation_id},
            )

        state.twitter_running = False
        state.reddit_running = False
        save_state(state)

    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error(f"Monitor thread exception: {simulation_id}, error={str(e)}")
        elapsed_seconds = _compute_elapsed_seconds(state.started_at)
        # Slice 2b: Sim-Lifecycle-Metric — RUNNING → FAILED (Exception-Pfad)
        sim_active_gauge().add(-1)
        sim_counter().add(1, {"status": "failed"})
        sim_duration_histogram().record(elapsed_seconds, {"status": "failed"})
        state.runner_status = RunnerStatus.FAILED
        state.error = str(e)
        save_state(state)

    finally:
        # Stop graph memory updater
        if graph_memory_enabled.get(simulation_id, False):
            try:
                # Lazy import to avoid hard cycle — GraphMemoryManager imports nothing
                # from this module.
                from ..graph_memory_updater import GraphMemoryManager  # noqa: PLC0415

                GraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"Graph memory update stopped: simulation_id={simulation_id}")
            except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.error(f"Failed to stop graph memory updater: {e}")
            graph_memory_enabled.pop(simulation_id, None)

        # Clean up process resources
        processes.pop(simulation_id, None)
        action_queues.pop(simulation_id, None)

        # Close log file handles
        if simulation_id in stdout_files:
            try:
                stdout_files[simulation_id].close()
            except Exception as exc:  # noqa: BLE001 — close file handle on cleanup; exc discarded
                logger.debug("monitor: file handle close failed, ignoring: %s", exc)
            stdout_files.pop(simulation_id, None)
        if simulation_id in stderr_files and stderr_files[simulation_id]:
            try:
                stderr_files[simulation_id].close()
            except Exception as exc:  # noqa: BLE001 — close file handle on cleanup; exc discarded
                logger.debug("monitor: file handle close failed, ignoring: %s", exc)
            stderr_files.pop(simulation_id, None)


def get_timeline(
    simulation_id: str,
    base_dir: str,
    start_round: int = 0,
    end_round: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return per-round timeline summaries for a simulation.

    Extracted from ``SimulationRunner.get_timeline``.

    Args:
        simulation_id: Simulation identifier.
        base_dir: ``SimulationRunner.RUN_STATE_DIR``.
        start_round: Lowest round number to include (inclusive).
        end_round: Highest round number to include (inclusive, ``None`` = unbounded).

    Returns:
        List of per-round summary dicts sorted by ``round_num`` ascending.
    """
    actions = _get_actions(simulation_id, base_dir, limit=10000)

    # Group by round
    rounds: Dict[int, Dict[str, Any]] = {}

    for action in actions:
        round_num = action.round_num

        if round_num < start_round:
            continue
        if end_round is not None and round_num > end_round:
            continue

        if round_num not in rounds:
            rounds[round_num] = {
                "round_num": round_num,
                "twitter_actions": 0,
                "reddit_actions": 0,
                "active_agents": set(),
                "action_types": {},
                "first_action_time": action.timestamp,
                "last_action_time": action.timestamp,
            }

        r = rounds[round_num]

        if action.platform == "twitter":
            r["twitter_actions"] += 1
        else:
            r["reddit_actions"] += 1

        r["active_agents"].add(action.agent_id)
        r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
        r["last_action_time"] = action.timestamp

    # Convert to list
    result = []
    for round_num in sorted(rounds.keys()):
        r = rounds[round_num]
        result.append(
            {
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            }
        )

    return result


def get_agent_stats(
    simulation_id: str,
    base_dir: str,
) -> List[Dict[str, Any]]:
    """Return per-agent action statistics for a simulation.

    Extracted from ``SimulationRunner.get_agent_stats``.

    Args:
        simulation_id: Simulation identifier.
        base_dir: ``SimulationRunner.RUN_STATE_DIR``.

    Returns:
        List of per-agent statistics dicts sorted by ``total_actions`` descending.
    """
    actions = _get_actions(simulation_id, base_dir, limit=10000)

    agent_stats: Dict[int, Dict[str, Any]] = {}

    for action in actions:
        agent_id = action.agent_id

        if agent_id not in agent_stats:
            agent_stats[agent_id] = {
                "agent_id": agent_id,
                "agent_name": action.agent_name,
                "total_actions": 0,
                "twitter_actions": 0,
                "reddit_actions": 0,
                "action_types": {},
                "first_action_time": action.timestamp,
                "last_action_time": action.timestamp,
            }

        stats = agent_stats[agent_id]
        stats["total_actions"] += 1

        if action.platform == "twitter":
            stats["twitter_actions"] += 1
        else:
            stats["reddit_actions"] += 1

        stats["action_types"][action.action_type] = (
            stats["action_types"].get(action.action_type, 0) + 1
        )
        stats["last_action_time"] = action.timestamp

    # Sort by total actions descending
    return sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)
