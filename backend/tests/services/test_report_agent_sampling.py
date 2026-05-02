"""Tests fuer _sample_actions_timeseries (Sub-Slice 13)."""
from __future__ import annotations

from app.services.report_agent import ReportAgent


def _action(rid: int, **kw):
    base = {"action_id": f"a{rid}", "round_num": rid, "agent_id": rid}
    base.update(kw)
    return base


def test_empty_returns_empty():
    assert ReportAgent._sample_actions_timeseries([], 8) == []


def test_below_threshold_keeps_all_no_marker():
    actions = [_action(i) for i in range(5)]
    out = ReportAgent._sample_actions_timeseries(actions, 8)
    assert len(out) == 5
    assert all("_sampling" not in a for a in out)


def test_stratified_over_round_num():
    actions = [_action(i) for i in range(100)]
    out = ReportAgent._sample_actions_timeseries(actions, 8)
    assert len(out) == 8
    bins = {a["_sampling"]["bin"] for a in out}
    assert bins == set(range(8))
    rounds = sorted(a["round_num"] for a in out)
    # erste Bin: round_num zwischen 0 und 12, letzte: ab 87
    assert rounds[0] < 13
    assert rounds[-1] >= 87


def test_deterministic():
    actions = [_action(i) for i in range(100)]
    out1 = ReportAgent._sample_actions_timeseries(actions, 8)
    out2 = ReportAgent._sample_actions_timeseries(actions, 8)
    assert [a["action_id"] for a in out1] == [a["action_id"] for a in out2]


def test_fallback_to_created_at_when_round_num_missing():
    actions = [
        {"action_id": f"a{i}", "created_at": f"2026-05-02T{i:02d}:00:00"}
        for i in range(20)
    ]
    out = ReportAgent._sample_actions_timeseries(actions, 8)
    assert len(out) == 8
    assert all("_sampling" in a for a in out)


def test_marker_includes_total():
    actions = [_action(i) for i in range(50)]
    out = ReportAgent._sample_actions_timeseries(actions, 8)
    assert all(a["_sampling"]["sampled_from_total"] == 50 for a in out)
