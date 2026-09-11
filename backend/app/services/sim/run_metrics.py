"""Pure read-only aggregation for persisted simulation actions.

Kept separate from monitor supervision so timeline/statistics logic has no
process, cancellation or manifest-finalisation side effects.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .run_state_store import AgentAction

GetActions = Callable[..., list[AgentAction]]


def get_timeline(
    simulation_id: str,
    base_dir: str,
    start_round: int = 0,
    end_round: int | None = None,
    *,
    get_actions: GetActions,
) -> list[dict[str, Any]]:
    """Return per-round timeline summaries sorted by round number."""
    actions = get_actions(simulation_id, base_dir, limit=10000)
    rounds: dict[int, dict[str, Any]] = {}

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

        summary = rounds[round_num]
        if action.platform == "twitter":
            summary["twitter_actions"] += 1
        else:
            summary["reddit_actions"] += 1
        summary["active_agents"].add(action.agent_id)
        summary["action_types"][action.action_type] = (
            summary["action_types"].get(action.action_type, 0) + 1
        )
        summary["last_action_time"] = action.timestamp

    result: list[dict[str, Any]] = []
    for round_num in sorted(rounds):
        summary = rounds[round_num]
        result.append(
            {
                "round_num": round_num,
                "twitter_actions": summary["twitter_actions"],
                "reddit_actions": summary["reddit_actions"],
                "total_actions": summary["twitter_actions"] + summary["reddit_actions"],
                "active_agents_count": len(summary["active_agents"]),
                "active_agents": list(summary["active_agents"]),
                "action_types": summary["action_types"],
                "first_action_time": summary["first_action_time"],
                "last_action_time": summary["last_action_time"],
            }
        )
    return result


def get_agent_stats(
    simulation_id: str,
    base_dir: str,
    *,
    get_actions: GetActions,
) -> list[dict[str, Any]]:
    """Return per-agent action statistics sorted by total actions."""
    actions = get_actions(simulation_id, base_dir, limit=10000)
    agent_stats: dict[int, dict[str, Any]] = {}

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

    return sorted(
        agent_stats.values(),
        key=lambda item: item["total_actions"],
        reverse=True,
    )
