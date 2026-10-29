"""Pure read-only aggregation for persisted simulation actions.

Kept separate from monitor supervision so timeline/statistics logic has no
process, cancellation or manifest-finalisation side effects.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .run_state_store import AgentAction

GetActions = Callable[..., list[AgentAction]]


def as_aware_utc(dt: datetime) -> datetime:
    """Ensure a ``datetime`` is timezone-aware (assuming UTC for naive values)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def compute_elapsed_seconds(
    started_at: str | None,
    *,
    now: datetime | None = None,
) -> float:
    """Compute non-negative elapsed seconds since ISO-8601 ``started_at``."""
    if not started_at:
        return 0.0
    try:
        start_dt = datetime.fromisoformat(started_at)
        ref_now = now or (
            datetime.now(start_dt.tzinfo) if start_dt.tzinfo is not None else datetime.now()
        )
        elapsed = (ref_now - start_dt).total_seconds()
        return max(0.0, elapsed)
    except ValueError, OverflowError, TypeError:
        return 0.0


def resolve_manifest_timing(
    started_at_iso: str | None,
    completed_at_iso: str | None,
) -> tuple[datetime, datetime | None, int | None]:
    """Derive ``(started_at, completed_at, duration_seconds)`` as UTC-aware datetimes."""
    started_at = (
        as_aware_utc(datetime.fromisoformat(started_at_iso))
        if started_at_iso
        else datetime.now(timezone.utc)
    )
    completed_at = (
        as_aware_utc(datetime.fromisoformat(completed_at_iso)) if completed_at_iso else None
    )
    duration_seconds = (
        int((completed_at - started_at).total_seconds()) if completed_at is not None else None
    )
    return started_at, completed_at, duration_seconds


def _accumulate_action_bucket(bucket: dict[str, Any], action: AgentAction) -> None:
    """Update platform counters, action_type histogram, and last_action_time in-place."""
    if action.platform == "twitter":
        bucket["twitter_actions"] += 1
    else:
        bucket["reddit_actions"] += 1
    bucket["action_types"][action.action_type] = (
        bucket["action_types"].get(action.action_type, 0) + 1
    )
    bucket["last_action_time"] = action.timestamp


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
        _accumulate_action_bucket(summary, action)
        summary["active_agents"].add(action.agent_id)

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
        _accumulate_action_bucket(stats, action)

    return sorted(
        agent_stats.values(),
        key=lambda item: item["total_actions"],
        reverse=True,
    )
