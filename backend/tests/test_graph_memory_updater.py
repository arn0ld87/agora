"""
Tests for the bounded-queue + backpressure behaviour of GraphMemoryUpdater.

The worker thread is intentionally NOT started in these tests — we exercise
``add_activity`` in isolation so we can reason about queue state deterministically.
"""

from unittest.mock import MagicMock

from app.services.graph_memory_updater import (
    AgentActivity,
    GraphMemoryUpdater,
)


def _make_activity(i: int = 0) -> AgentActivity:
    return AgentActivity(
        platform="twitter",
        agent_id=i,
        agent_name=f"agent_{i}",
        action_type="CREATE_POST",
        action_args={"content": f"hello {i}"},
        round_num=1,
        timestamp="2026-04-23T00:00:00",
    )


def test_bounded_queue_drops_overflow_events():
    """When the queue is saturated ``add_activity`` drops events instead of blocking forever."""
    storage = MagicMock()
    updater = GraphMemoryUpdater(
        graph_id="g1",
        storage=storage,
        max_queue_size=2,
        put_timeout=0.05,  # keep tests fast
    )

    updater.add_activity(_make_activity(0))
    updater.add_activity(_make_activity(1))
    # Queue is now full; this event must be dropped, not block indefinitely.
    updater.add_activity(_make_activity(2))

    stats = updater.get_stats()
    assert stats["queue_size"] == 2
    assert stats["queue_max"] == 2
    assert stats["total_activities"] == 2, "Only successful puts count as queued"
    assert stats["dropped_count"] == 1
    assert stats["skipped_count"] == 0


def test_do_nothing_activities_are_skipped_not_queued():
    storage = MagicMock()
    updater = GraphMemoryUpdater(
        graph_id="g1",
        storage=storage,
        max_queue_size=5,
        put_timeout=0.05,
    )

    noop = AgentActivity(
        platform="twitter",
        agent_id=0,
        agent_name="noop",
        action_type="DO_NOTHING",
        action_args={},
        round_num=0,
        timestamp="2026-04-23T00:00:00",
    )

    updater.add_activity(noop)

    stats = updater.get_stats()
    assert stats["queue_size"] == 0
    assert stats["skipped_count"] == 1
    assert stats["dropped_count"] == 0
    assert stats["total_activities"] == 0


def test_unbounded_mode_preserves_legacy_behaviour():
    """``max_queue_size=0`` keeps the legacy unbounded semantics as an opt-in."""
    storage = MagicMock()
    updater = GraphMemoryUpdater(
        graph_id="g1",
        storage=storage,
        max_queue_size=0,
        put_timeout=0.01,
    )

    for i in range(20):
        updater.add_activity(_make_activity(i))

    stats = updater.get_stats()
    assert stats["queue_max"] == 0
    assert stats["queue_size"] == 20
    assert stats["dropped_count"] == 0
    assert stats["total_activities"] == 20


def test_stats_exposes_queue_limits_and_drop_count():
    storage = MagicMock()
    updater = GraphMemoryUpdater(
        graph_id="g1",
        storage=storage,
        max_queue_size=3,
        put_timeout=0.01,
    )

    stats = updater.get_stats()
    assert "dropped_count" in stats
    assert "queue_max" in stats
    assert stats["queue_max"] == 3
    assert stats["running"] is False
