"""Tests für Run Budget Enforcement — weiche/harte Limits (Issue #764)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services import run_budget as rb
from app.services.run_budget import (
    BudgetExceededError,
    RunBudgetEnforcer,
    get_run_budget_status,
    mark_budget_abort,
)
from app.services.run_registry import RunRegistry
from app.services.run_usage_ledger import reset_usage_cache


@pytest.fixture()
def run_env(tmp_path, monkeypatch):
    """Isolierte Registry + Run-Dir pro Test."""
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    run_dirs = tmp_path / "runs"
    run_dirs.mkdir()
    monkeypatch.setattr(
        "app.services.run_usage_ledger.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    monkeypatch.setattr(
        "app.services.run_budget.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    reset_usage_cache()
    yield run_dirs
    RunRegistry._instance = None
    reset_usage_cache()


def _create_run(budget: dict | None = None, started_at: str | None = None) -> str:
    manifest = RunRegistry().create_run(
        "simulation_run", "sim_1", metadata={"budget": budget} if budget else None
    )
    if started_at:
        RunRegistry().update_run(manifest["run_id"])
        # started_at direkt im Manifest setzen (update_run kennt das Feld nicht)
        raw = RunRegistry().get_run(manifest["run_id"])
        raw["started_at"] = started_at
        RunRegistry()._write_run(raw)
    return manifest["run_id"]


def _write_events(run_dirs: Path, run_id: str, events: list[dict]) -> None:
    run_dir = run_dirs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "llm_call_events.jsonl", "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    reset_usage_cache()


def _event(**overrides) -> dict:
    base = {
        "stage": "simulation_rounds",
        "provider_id": "openai",
        "model": "gpt-4o-mini",
        "base_url_sanitized": "https://api.openai.com",
        "timestamp": 1_700_000_000.0,
        "latency_ms": 100.0,
        "success": True,
        "prompt_tokens": 1000,
        "completion_tokens": 500,
    }
    base.update(overrides)
    return base


class TestHardLimits:
    def test_token_limit_blocks_call(self, run_env):
        run_id = _create_run({"max_tokens": 1000, "enforcement": "hard"})
        _write_events(run_env, run_id, [_event()])
        enforcer = RunBudgetEnforcer.for_run(run_id)
        with pytest.raises(BudgetExceededError) as exc_info:
            enforcer.check_before_call()
        assert exc_info.value.dimension == "tokens"
        assert exc_info.value.termination_reason == "budget_tokens"

    def test_cost_limit_blocks_call(self, run_env):
        run_id = _create_run({"max_cost_micros": 100, "enforcement": "hard"})
        _write_events(run_env, run_id, [_event()])
        enforcer = RunBudgetEnforcer.for_run(run_id)
        with pytest.raises(BudgetExceededError) as exc_info:
            enforcer.check_before_call()
        assert exc_info.value.dimension == "cost"

    def test_time_limit_blocks_call(self, run_env):
        past = (datetime.now() - timedelta(seconds=120)).isoformat()
        run_id = _create_run(
            {"max_duration_seconds": 60, "enforcement": "hard"}, started_at=past
        )
        enforcer = RunBudgetEnforcer.for_run(run_id)
        with pytest.raises(BudgetExceededError) as exc_info:
            enforcer.check_before_call()
        assert exc_info.value.dimension == "time"

    def test_calls_limit_blocks_call(self, run_env):
        run_id = _create_run({"max_llm_calls": 2, "enforcement": "hard"})
        _write_events(run_env, run_id, [_event(), _event()])
        enforcer = RunBudgetEnforcer.for_run(run_id)
        with pytest.raises(BudgetExceededError) as exc_info:
            enforcer.check_before_call()
        assert exc_info.value.dimension == "calls"

    def test_under_limit_allows_call(self, run_env):
        run_id = _create_run({"max_tokens": 999_999, "enforcement": "hard"})
        _write_events(run_env, run_id, [_event()])
        RunBudgetEnforcer.for_run(run_id).check_before_call()  # kein Raise

    def test_unknown_cost_cannot_trip_cost_limit(self, run_env):
        run_id = _create_run({"max_cost_micros": 1, "enforcement": "hard"})
        _write_events(
            run_env, run_id, [_event(provider_id="minimax", model="MiniMax-M9-x")]
        )
        # Kosten unbekannt → ehrlich kein Abbruch auf Basis erfundener Werte
        RunBudgetEnforcer.for_run(run_id).check_before_call()

    def test_no_budget_no_enforcer(self, run_env):
        run_id = _create_run()
        assert RunBudgetEnforcer.for_run(run_id) is None
        assert get_run_budget_status(run_id) is None


class TestSoftLimits:
    def test_soft_limit_warns_and_continues(self, run_env):
        run_id = _create_run({"max_tokens": 1000, "enforcement": "soft"})
        _write_events(run_env, run_id, [_event()])
        enforcer = RunBudgetEnforcer.for_run(run_id)
        enforcer.check_before_call()  # soft: kein Raise
        enforcer.record_after_call()

        warnings = rb.load_warnings(run_id)
        assert len(warnings) == 1
        assert warnings[0].dimension == "tokens"
        assert warnings[0].severity == "soft"

        status = get_run_budget_status(run_id)
        assert status is not None
        assert status.status == "warning"

    def test_warning_deduped_per_dimension(self, run_env):
        run_id = _create_run({"max_tokens": 1000, "enforcement": "soft"})
        _write_events(run_env, run_id, [_event()])
        enforcer = RunBudgetEnforcer.for_run(run_id)
        enforcer.record_after_call()
        enforcer.record_after_call()
        assert len(rb.load_warnings(run_id)) == 1

    def test_warning_audited_as_manifest_event(self, run_env):
        run_id = _create_run({"max_tokens": 1000, "enforcement": "soft"})
        _write_events(run_env, run_id, [_event()])
        RunBudgetEnforcer.for_run(run_id).record_after_call()
        events = RunRegistry().get_events(run_id)
        budget_events = [e for e in events if e["type"] == "budget_warning"]
        assert len(budget_events) == 1
        assert budget_events[0]["details"]["dimension"] == "tokens"


class TestBudgetAbort:
    def test_mark_budget_abort_sets_stopped_and_reason(self, run_env):
        run_id = _create_run({"max_tokens": 1000, "enforcement": "hard"})
        _write_events(run_env, run_id, [_event()])
        mark_budget_abort(run_id, "tokens", observed=1500, threshold=1000)

        manifest = RunRegistry().get_run(run_id)
        assert manifest["status"] == "stopped"
        assert manifest["termination_reason"] == "budget_tokens"
        assert manifest["completed_at"] is not None
        abort_events = [e for e in manifest["events"] if e["type"] == "budget_abort"]
        assert len(abort_events) == 1

        status = get_run_budget_status(run_id)
        assert status.status == "exceeded"
        assert status.exceeded_dimension == "tokens"

    def test_partial_results_survive_abort(self, run_env):
        run_id = _create_run({"max_tokens": 2000, "enforcement": "hard"})
        _write_events(run_env, run_id, [_event()])
        mark_budget_abort(run_id, "tokens", observed=1500, threshold=2000)
        # Ledger bleibt lesbar: Teilresultate (bereits verbuchte Calls) erhalten
        status = get_run_budget_status(run_id)
        assert status.consumed.total_tokens == 1500
        assert status.consumed.llm_calls == 1

    def test_abort_reason_distinct_from_technical_error(self, run_env):
        run_id = _create_run({"max_llm_calls": 1, "enforcement": "hard"})
        mark_budget_abort(run_id, "calls", observed=1, threshold=1)
        manifest = RunRegistry().get_run(run_id)
        assert manifest["termination_reason"] == "budget_calls"
        assert manifest["status"] != "failed"
