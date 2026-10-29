"""Unit tests for Slice #4: RunReadModel & Metrics deep module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.run_read_model import (
    build_run_detail,
    build_runs_list_response,
    extract_run_log_tail,
    extract_run_scalar_metrics,
    parse_status_param,
    resolve_run_usage,
)
from app.services.sim.run_metrics import (
    as_aware_utc,
    compute_elapsed_seconds,
    get_agent_stats,
    get_timeline,
    resolve_manifest_timing,
)
from app.services.sim.run_state_store import AgentAction


class _MultiArgs:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def getlist(self, key: str) -> list[str]:
        return list(self._values) if key == "status" else []


def test_parse_status_param_handles_comma_separated_and_multi_value() -> None:
    assert parse_status_param(_MultiArgs([])) is None
    assert parse_status_param(_MultiArgs([" , "])) is None
    assert parse_status_param(_MultiArgs(["processing, pending", "completed"])) == [
        "processing",
        "pending",
        "completed",
    ]


def test_extract_run_log_tail_limits_and_filters_empty_messages() -> None:
    assert extract_run_log_tail(None) is None
    assert extract_run_log_tail([{"message": ""}]) is None
    events = [{"message": f"msg-{i}"} for i in range(25)]
    tail = extract_run_log_tail(events, max_entries=20)
    assert tail is not None
    assert len(tail) == 20
    assert tail[0] == "msg-5"
    assert tail[-1] == "msg-24"


def test_extract_run_scalar_metrics_reads_phase_round_and_last_event_ts() -> None:
    assert extract_run_scalar_metrics({}, []) is None
    metrics = extract_run_scalar_metrics(
        {"stage": "simulation", "round": 3},
        [{"timestamp": "2026-10-29T12:00:00Z", "message": "tick"}],
    )
    assert metrics == {
        "phase": "simulation",
        "round_num": 3,
        "last_event_at": "2026-10-29T12:00:00Z",
    }


def test_build_run_detail_and_list_response_use_custom_attach_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.run_budget.get_run_budget_status",
        lambda _run_id: None,
    )
    monkeypatch.setattr(
        "app.services.run_usage_ledger.load_usage_summary",
        lambda _run_id: None,
    )
    monkeypatch.setattr(
        "app.services.run_usage_ledger.load_call_events_cached",
        lambda _run_id: [],
    )

    def _fake_attach(run: dict[str, Any], _sim: dict, _proj: dict) -> dict[str, Any]:
        copy = dict(run)
        copy["summary"] = {
            "model": "gpt-4o",
            "document_name": "doc.pdf",
            "persona_count": 12,
            "graph_id": "g1",
            "graph_name": "Graph 1",
            "branch_name": "main",
        }
        return copy

    raw_run = {
        "run_id": "run_abc123def456",
        "run_type": "simulation_run",
        "entity_id": "sim_abc123def456",
        "status": "processing",
        "progress": 50,
        "started_at": "2026-10-29T12:00:00Z",
        "created_at": "2026-10-29T12:00:00Z",
        "updated_at": "2026-10-29T12:01:00Z",
        "metadata": {"eta_seconds": 42, "phase": "round_1", "round_num": 1},
        "events": [{"timestamp": "2026-10-29T12:01:00Z", "message": "Round 1 started"}],
    }
    detail = build_run_detail(raw_run, attach_summary_fn=_fake_attach)
    assert detail["summary"]["model"] == "gpt-4o"
    assert detail["eta_seconds"] == 42
    assert detail["log_tail"] == ["Round 1 started"]
    assert detail["metrics"] == {
        "phase": "round_1",
        "round_num": 1,
        "last_event_at": "2026-10-29T12:01:00Z",
    }
    assert "usage" not in detail

    list_resp = build_runs_list_response(
        [raw_run],
        status_counts={"processing": 1, "completed": 2},
        attach_summary_fn=_fake_attach,
    )
    assert list_resp.total == 1
    assert list_resp.runs[0].run_id == "run_abc123def456"
    assert list_resp.aggregation is not None
    assert list_resp.aggregation.total == 3


def test_resolve_run_usage_distinguishes_detail_and_endpoint_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.run_usage_ledger.load_usage_summary",
        lambda _run_id: None,
    )
    monkeypatch.setattr(
        "app.services.run_usage_ledger.load_call_events_cached",
        lambda _run_id: [],
    )
    run = {"run_id": "run_abc123def456", "started_at": None, "completed_at": None}
    assert resolve_run_usage(run, require_events_for_fallback=True) is None
    empty_summary = resolve_run_usage(run, require_events_for_fallback=False)
    assert empty_summary is not None
    assert empty_summary.totals.llm_calls == 0


def test_run_metrics_timing_and_action_aggregation() -> None:
    naive = datetime(2026, 10, 29, 12, 0, 0)
    aware = as_aware_utc(naive)
    assert aware.tzinfo == timezone.utc

    assert compute_elapsed_seconds(None) == 0.0
    assert compute_elapsed_seconds("invalid-iso") == 0.0
    elapsed = compute_elapsed_seconds(
        "2026-10-29T12:00:00+00:00",
        now=datetime(2026, 10, 29, 12, 0, 15, tzinfo=timezone.utc),
    )
    assert elapsed == 15.0

    started, completed, duration = resolve_manifest_timing(
        "2026-10-29T12:00:00",
        "2026-10-29T12:02:05",
    )
    assert started.tzinfo == timezone.utc
    assert completed is not None and completed.tzinfo == timezone.utc
    assert duration == 125

    sample_actions = [
        AgentAction(
            round_num=1,
            timestamp="2026-10-29T12:00:01",
            platform="twitter",
            agent_id=1,
            agent_name="Alice",
            action_type="CREATE_POST",
        ),
        AgentAction(
            round_num=1,
            timestamp="2026-10-29T12:00:05",
            platform="reddit",
            agent_id=1,
            agent_name="Alice",
            action_type="CREATE_COMMENT",
        ),
        AgentAction(
            round_num=2,
            timestamp="2026-10-29T12:01:00",
            platform="twitter",
            agent_id=2,
            agent_name="Bob",
            action_type="CREATE_POST",
        ),
    ]

    def _get_actions(_sim_id: str, _base_dir: str, limit: int = 10000) -> list[AgentAction]:
        return sample_actions[:limit]

    timeline = get_timeline("sim_1", "/tmp", get_actions=_get_actions)
    assert len(timeline) == 2
    assert timeline[0]["total_actions"] == 2
    assert timeline[0]["twitter_actions"] == 1
    assert timeline[0]["reddit_actions"] == 1

    stats = get_agent_stats("sim_1", "/tmp", get_actions=_get_actions)
    assert len(stats) == 2
    assert stats[0]["agent_name"] == "Alice"
    assert stats[0]["total_actions"] == 2
