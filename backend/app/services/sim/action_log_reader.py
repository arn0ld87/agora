"""
Action-log reader helpers for OASIS simulation runs.

Extracted from ``simulation_runner.py`` as part of M11 Phase 5 PR 2.
``simulation_runner.py`` re-exports all five functions as class methods on
``SimulationRunner`` for backward-compat (Monkeypatch-Stubs in tests).

Design constraints
------------------
* No import of ``simulation_runner.py`` — only imports from ``.run_state_store``
  (which is the authoritative location for the data-classes since PR 1).
* ``_graph_memory_enabled`` is **not** accessed as global class state.
  ``read_action_log_chunk`` receives the flag as an optional keyword argument;
  the caller (``SimulationRunner._monitor_simulation``) passes
  ``cls._graph_memory_enabled.get(simulation_id, False)``.
* The legacy single-file fallback (``actions.jsonl`` in the sim root) is
  preserved in ``get_all_actions`` exactly as it was in the original code.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ...utils.logger import get_logger
from .run_state_store import AgentAction, RunnerStatus, SimulationRunState

logger = get_logger("agora.action_log_reader")


# ---------------------------------------------------------------------------
# Chunk reader (called by the monitor thread)
# ---------------------------------------------------------------------------


def read_action_log_chunk(
    log_path: str,
    position: int,
    state: SimulationRunState,
    platform: str,
    *,
    graph_memory_enabled: bool = False,
) -> int:
    """Read a JSONL action log from *position* and update *state* in place.

    Args:
        log_path: Absolute path to the ``.jsonl`` file.
        position: File offset (bytes) from which to start reading.
        state: Mutable run-state object; mutated in place.
        platform: ``"twitter"`` or ``"reddit"``.
        graph_memory_enabled: If ``True``, discovered actions are also forwarded
            to the ``GraphMemoryManager`` updater for the simulation.

    Returns:
        New file offset after reading.
    """
    graph_updater = None
    if graph_memory_enabled:
        # Lazy import to avoid a hard cycle — graph_memory_updater imports
        # nothing from this module.
        from ..graph_memory_updater import GraphMemoryManager  # noqa: PLC0415

        graph_updater = GraphMemoryManager.get_updater(state.simulation_id)

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            f.seek(position)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    action_data = json.loads(line)

                    # Handle event-type entries (simulation_end, round_end, …)
                    if "event_type" in action_data:
                        event_type = action_data.get("event_type")

                        if event_type == "simulation_end":
                            if platform == "twitter":
                                state.twitter_completed = True
                                state.twitter_running = False
                                logger.info(
                                    f"Twitter simulation completed: {state.simulation_id}, "
                                    f"total_rounds={action_data.get('total_rounds')}, "
                                    f"total_actions={action_data.get('total_actions')}"
                                )
                            elif platform == "reddit":
                                state.reddit_completed = True
                                state.reddit_running = False
                                logger.info(
                                    f"Reddit simulation completed: {state.simulation_id}, "
                                    f"total_rounds={action_data.get('total_rounds')}, "
                                    f"total_actions={action_data.get('total_actions')}"
                                )

                            all_completed = check_all_platforms_completed(
                                state, base_dir=os.path.dirname(os.path.dirname(log_path))
                            )
                            if all_completed:
                                state.runner_status = RunnerStatus.COMPLETED
                                state.completed_at = datetime.now().isoformat()
                                logger.info(
                                    f"All platform simulations completed: {state.simulation_id}"
                                )

                        elif event_type == "round_end":
                            round_num = action_data.get("round", 0)
                            simulated_hours = action_data.get("simulated_hours", 0)

                            if platform == "twitter":
                                if round_num > state.twitter_current_round:
                                    state.twitter_current_round = round_num
                                state.twitter_simulated_hours = simulated_hours
                            elif platform == "reddit":
                                if round_num > state.reddit_current_round:
                                    state.reddit_current_round = round_num
                                state.reddit_simulated_hours = simulated_hours

                            if round_num > state.current_round:
                                state.current_round = round_num
                            state.simulated_hours = max(
                                state.twitter_simulated_hours, state.reddit_simulated_hours
                            )

                        continue

                    action = AgentAction(
                        round_num=action_data.get("round", 0),
                        timestamp=action_data.get("timestamp", datetime.now().isoformat()),
                        platform=platform,
                        agent_id=action_data.get("agent_id", 0),
                        agent_name=action_data.get("agent_name", ""),
                        action_type=action_data.get("action_type", ""),
                        action_args=action_data.get("action_args", {}),
                        result=action_data.get("result"),
                        success=action_data.get("success", True),
                    )
                    state.add_action(action)

                    if action.round_num and action.round_num > state.current_round:
                        state.current_round = action.round_num

                    if graph_updater:
                        graph_updater.add_activity_from_dict(action_data, platform)

                except json.JSONDecodeError:
                    pass
            return f.tell()
    except Exception as e:
        logger.warning(f"Failed to read action log: {log_path}, error={e}")
        return position


# ---------------------------------------------------------------------------
# Platform-completion check
# ---------------------------------------------------------------------------


def check_all_platforms_completed(
    state: SimulationRunState,
    base_dir: str | Path,
) -> bool:
    """Return ``True`` when all enabled platforms have emitted ``simulation_end``.

    A platform is considered *enabled* when its ``actions.jsonl`` file exists.

    Args:
        state: Current run state.
        base_dir: The simulation's run-state directory
            (``<RUN_STATE_DIR>/<simulation_id>``).
    """
    sim_dir = str(base_dir)
    twitter_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
    reddit_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

    twitter_enabled = os.path.exists(twitter_log)
    reddit_enabled = os.path.exists(reddit_log)

    if twitter_enabled and not state.twitter_completed:
        return False
    if reddit_enabled and not state.reddit_completed:
        return False

    return twitter_enabled or reddit_enabled


# ---------------------------------------------------------------------------
# Single-file reader
# ---------------------------------------------------------------------------


def read_actions_from_file(
    file_path: str,
    default_platform: Optional[str] = None,
    platform_filter: Optional[str] = None,
    agent_id: Optional[int] = None,
    round_num: Optional[int] = None,
) -> List[AgentAction]:
    """Read and filter ``AgentAction`` objects from a single ``.jsonl`` file.

    Args:
        file_path: Absolute path to the ``.jsonl`` file.
        default_platform: Fallback platform string when the record omits the
            ``"platform"`` field.
        platform_filter: If set, only records whose effective platform matches
            this value are returned.
        agent_id: If set, only records for this agent are returned.
        round_num: If set, only records from this round are returned.

    Returns:
        List of matching ``AgentAction`` objects.
    """
    if not os.path.exists(file_path):
        return []

    actions: List[AgentAction] = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                # Skip event-type records (simulation_start, round_start, …)
                if "event_type" in data:
                    continue

                # Skip records without agent_id
                if "agent_id" not in data:
                    continue

                record_platform = data.get("platform") or default_platform or ""

                if platform_filter and record_platform != platform_filter:
                    continue
                if agent_id is not None and data.get("agent_id") != agent_id:
                    continue
                if round_num is not None and data.get("round") != round_num:
                    continue

                actions.append(
                    AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    )
                )
            except json.JSONDecodeError:
                continue

    return actions


# ---------------------------------------------------------------------------
# Aggregate readers
# ---------------------------------------------------------------------------


def get_all_actions(
    simulation_id: str,
    base_dir: str | Path,
    platform: Optional[str] = None,
    agent_id: Optional[int] = None,
    round_num: Optional[int] = None,
) -> List[AgentAction]:
    """Return the complete action history for a simulation (no pagination).

    Reads per-platform ``.jsonl`` files (``twitter/actions.jsonl``,
    ``reddit/actions.jsonl``) and falls back to the legacy single-file layout
    (``actions.jsonl`` in the simulation root) when neither per-platform file
    yields any results.

    Args:
        simulation_id: Simulation identifier.
        base_dir: Root directory that contains per-simulation sub-directories
            (``<RUN_STATE_DIR>``).
        platform: If set, only actions for this platform are returned.
        agent_id: If set, only actions for this agent are returned.
        round_num: If set, only actions from this round are returned.

    Returns:
        Complete action list sorted by timestamp, newest first.
    """
    sim_dir = os.path.join(str(base_dir), simulation_id)
    actions: List[AgentAction] = []

    twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
    if not platform or platform == "twitter":
        actions.extend(
            read_actions_from_file(
                twitter_actions_log,
                default_platform="twitter",
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num,
            )
        )

    reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
    if not platform or platform == "reddit":
        actions.extend(
            read_actions_from_file(
                reddit_actions_log,
                default_platform="reddit",
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num,
            )
        )

    # Legacy fallback: single actions.jsonl in the simulation root
    if not actions:
        legacy_log = os.path.join(sim_dir, "actions.jsonl")
        actions = read_actions_from_file(
            legacy_log,
            default_platform=None,
            platform_filter=platform,
            agent_id=agent_id,
            round_num=round_num,
        )

    actions.sort(key=lambda x: x.timestamp, reverse=True)
    return actions


def get_actions(
    simulation_id: str,
    base_dir: str | Path,
    limit: int = 100,
    offset: int = 0,
    platform: Optional[str] = None,
    agent_id: Optional[int] = None,
    round_num: Optional[int] = None,
) -> List[AgentAction]:
    """Return a paginated slice of the action history.

    Args:
        simulation_id: Simulation identifier.
        base_dir: Root directory that contains per-simulation sub-directories.
        limit: Maximum number of actions to return.
        offset: Number of actions to skip from the beginning of the sorted list.
        platform: Optional platform filter.
        agent_id: Optional agent filter.
        round_num: Optional round filter.

    Returns:
        Paginated action list.
    """
    all_actions = get_all_actions(
        simulation_id=simulation_id,
        base_dir=base_dir,
        platform=platform,
        agent_id=agent_id,
        round_num=round_num,
    )
    return all_actions[offset : offset + limit]
