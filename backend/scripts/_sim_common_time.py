"""Simulation time computation helpers."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Any


def compute_start_hour_offset(
    config: dict[str, Any],
    total_rounds: int,
    minutes_per_round: int,
) -> int:
    """Pick a simulated-clock offset so short runs don't sit entirely in the
    agents' inactive hours.
    """
    time_config = config.get("time_config", {}) or {}
    explicit = time_config.get("start_hour")
    if explicit is not None:
        return int(explicit) % 24

    simulated_hours = (total_rounds * minutes_per_round) / 60.0
    if simulated_hours >= 24:
        return 0

    hour_counts: Counter[int] = Counter()
    for ac in config.get("agent_configs", []) or []:
        for h in ac.get("active_hours", []) or []:
            hour_counts[int(h) % 24] += 1
    if not hour_counts:
        return 9
    return int(hour_counts.most_common(1)[0][0])


def compute_post_sim_time(
    anchor: datetime,
    start_hour_offset: int,
    simulated_minutes: int,
    minutes_per_round: int,
    action_index: int,
    action_count: int,
) -> datetime:
    """Spread a round's actions across that round's simulated minute budget."""
    round_start = anchor + timedelta(
        minutes=start_hour_offset * 60 + simulated_minutes
    )
    if action_count <= 1 or action_index <= 0:
        return round_start
    index = min(action_index, action_count - 1)
    return round_start + timedelta(
        minutes=minutes_per_round * index / action_count
    )
