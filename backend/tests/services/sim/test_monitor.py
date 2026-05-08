"""
Smoke-tests for ``app.services.sim.monitor``.

These tests exercise the pure read functions ``get_timeline`` and
``get_agent_stats`` in isolation — no filesystem, no subprocesses.
They use ``monkeypatch`` to stub ``get_actions`` inside the monitor module so
that we can feed fixture data without touching the disk.
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from unittest.mock import patch

from app.services.sim.monitor import get_agent_stats, get_timeline
from app.services.sim.run_state_store import AgentAction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_action(
    agent_id: int,
    agent_name: str,
    platform: str,
    action_type: str,
    round_num: int,
    timestamp: str | None = None,
) -> AgentAction:
    return AgentAction(
        round_num=round_num,
        timestamp=timestamp or datetime.now().isoformat(),
        platform=platform,
        agent_id=agent_id,
        agent_name=agent_name,
        action_type=action_type,
        action_args={},
        result=None,
        success=True,
    )


FIXTURE_ACTIONS: List[AgentAction] = [
    # Round 1
    _make_action(1, "Alice", "twitter", "tweet", 1, "2026-01-01T10:00:00"),
    _make_action(2, "Bob", "reddit", "post", 1, "2026-01-01T10:01:00"),
    _make_action(1, "Alice", "twitter", "retweet", 1, "2026-01-01T10:02:00"),
    # Round 2
    _make_action(3, "Carol", "twitter", "tweet", 2, "2026-01-01T11:00:00"),
    _make_action(2, "Bob", "reddit", "comment", 2, "2026-01-01T11:01:00"),
    _make_action(3, "Carol", "reddit", "post", 2, "2026-01-01T11:02:00"),
]


# ---------------------------------------------------------------------------
# get_timeline tests
# ---------------------------------------------------------------------------


def _stub_get_actions(simulation_id: str, base_dir: str, limit: int = 10000):
    return FIXTURE_ACTIONS


class TestGetTimeline:
    def test_round_grouping(self) -> None:
        """Actions must be grouped by round_num with correct counts."""
        with patch(
            "app.services.sim.monitor._get_actions",
            side_effect=_stub_get_actions,
        ):
            result = get_timeline("sim-001", base_dir="/fake")

        assert len(result) == 2, "Expected two rounds"

        r1 = result[0]
        assert r1["round_num"] == 1
        assert r1["twitter_actions"] == 2
        assert r1["reddit_actions"] == 1
        assert r1["total_actions"] == 3
        assert r1["active_agents_count"] == 2
        assert set(r1["active_agents"]) == {1, 2}
        assert r1["action_types"] == {"tweet": 1, "retweet": 1, "post": 1}

        r2 = result[1]
        assert r2["round_num"] == 2
        assert r2["twitter_actions"] == 1
        assert r2["reddit_actions"] == 2
        assert r2["total_actions"] == 3
        assert r2["active_agents_count"] == 2
        assert set(r2["active_agents"]) == {2, 3}

    def test_start_round_filter(self) -> None:
        """start_round must exclude earlier rounds."""
        with patch(
            "app.services.sim.monitor._get_actions",
            side_effect=_stub_get_actions,
        ):
            result = get_timeline("sim-001", base_dir="/fake", start_round=2)

        assert len(result) == 1
        assert result[0]["round_num"] == 2

    def test_end_round_filter(self) -> None:
        """end_round must exclude later rounds."""
        with patch(
            "app.services.sim.monitor._get_actions",
            side_effect=_stub_get_actions,
        ):
            result = get_timeline("sim-001", base_dir="/fake", end_round=1)

        assert len(result) == 1
        assert result[0]["round_num"] == 1

    def test_empty_actions(self) -> None:
        """Empty action list must return an empty timeline."""
        with patch("app.services.sim.monitor._get_actions", return_value=[]):
            result = get_timeline("sim-empty", base_dir="/fake")

        assert result == []


# ---------------------------------------------------------------------------
# get_agent_stats tests
# ---------------------------------------------------------------------------


class TestGetAgentStats:
    def test_aggregation(self) -> None:
        """Stats must be correctly aggregated per agent."""
        with patch(
            "app.services.sim.monitor._get_actions",
            side_effect=_stub_get_actions,
        ):
            result = get_agent_stats("sim-001", base_dir="/fake")

        # All three agents must appear
        agent_ids = [s["agent_id"] for s in result]
        assert set(agent_ids) == {1, 2, 3}

        stats_by_id = {s["agent_id"]: s for s in result}

        # Alice (id=1): 2 twitter, 0 reddit
        alice = stats_by_id[1]
        assert alice["total_actions"] == 2
        assert alice["twitter_actions"] == 2
        assert alice["reddit_actions"] == 0
        assert alice["action_types"] == {"tweet": 1, "retweet": 1}
        assert alice["agent_name"] == "Alice"

        # Bob (id=2): 0 twitter, 2 reddit
        bob = stats_by_id[2]
        assert bob["total_actions"] == 2
        assert bob["twitter_actions"] == 0
        assert bob["reddit_actions"] == 2
        assert bob["action_types"] == {"post": 1, "comment": 1}

        # Carol (id=3): 1 twitter, 1 reddit
        carol = stats_by_id[3]
        assert carol["total_actions"] == 2
        assert carol["twitter_actions"] == 1
        assert carol["reddit_actions"] == 1

    def test_sorted_by_total_desc(self) -> None:
        """Result must be sorted by total_actions descending."""
        with patch(
            "app.services.sim.monitor._get_actions",
            side_effect=_stub_get_actions,
        ):
            result = get_agent_stats("sim-001", base_dir="/fake")

        totals = [s["total_actions"] for s in result]
        assert totals == sorted(totals, reverse=True)

    def test_empty_actions(self) -> None:
        """Empty action list must return an empty stats list."""
        with patch("app.services.sim.monitor._get_actions", return_value=[]):
            result = get_agent_stats("sim-empty", base_dir="/fake")

        assert result == []
