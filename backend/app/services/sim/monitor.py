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

from ...utils.logger import get_logger
from .action_log_reader import get_actions as _get_actions
from .action_log_reader import read_action_log_chunk
from .run_state_store import RunnerStatus, SimulationRunState

logger = get_logger("agora.monitor")


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

        if exit_code == 0:
            state.runner_status = RunnerStatus.COMPLETED
            state.completed_at = datetime.now().isoformat()
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
            except Exception:
                pass
            state.error = f"Process exit code: {exit_code}, error: {error_info}"
            logger.error(
                f"Simulation failed: {simulation_id}, error={state.error}",
                extra={"simulation_id": simulation_id},
            )

        state.twitter_running = False
        state.reddit_running = False
        save_state(state)

    except Exception as e:
        logger.error(f"Monitor thread exception: {simulation_id}, error={str(e)}")
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
            except Exception as e:
                logger.error(f"Failed to stop graph memory updater: {e}")
            graph_memory_enabled.pop(simulation_id, None)

        # Clean up process resources
        processes.pop(simulation_id, None)
        action_queues.pop(simulation_id, None)

        # Close log file handles
        if simulation_id in stdout_files:
            try:
                stdout_files[simulation_id].close()
            except Exception:
                pass
            stdout_files.pop(simulation_id, None)
        if simulation_id in stderr_files and stderr_files[simulation_id]:
            try:
                stderr_files[simulation_id].close()
            except Exception:
                pass
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
