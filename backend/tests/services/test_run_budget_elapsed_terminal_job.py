"""Zeitbudget beendeter Jobs: Laufdauer statt Wanduhr (#1805, F1).

UI-Interviews buchen auf den ``simulation_run``-Job. Ein regulaer im Limit
beendeter Lauf darf nach Ablauf der Wanduhrzeit weder Interviews ablehnen noch
eine harte Zeit-Warnung ins Manifest bekommen. Laufende Jobs und alle anderen
Dimensionen bleiben unveraendert. Alle Tests nutzen den echten Enforcer, die
echte ``RunRegistry`` und den echten Ledger.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from app.services.run_budget import (
    BudgetExceededError,
    RunBudgetEnforcer,
    load_warnings,
)
from app.services.run_registry import RunRegistry
from app.services.run_usage_ledger import reset_usage_cache

SIM_ID = "sim_0123456789ab"


@pytest.fixture
def run_dirs(tmp_path, monkeypatch) -> Path:
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    dirs = tmp_path / "runs"
    dirs.mkdir()
    for target in (
        "app.services.run_budget.ArtifactLocator.run_dir",
        "app.services.run_usage_ledger.ArtifactLocator.run_dir",
    ):
        monkeypatch.setattr(target, staticmethod(lambda run_id: str(dirs / run_id)))
    reset_usage_cache()
    yield dirs
    RunRegistry._instance = None
    reset_usage_cache()


def _create_job(
    *,
    status: str,
    started_ago: timedelta,
    duration: Optional[timedelta],
    budget: Dict[str, Any],
) -> str:
    """Job mit festem Start (``started_ago`` her) und optionalem Ende anlegen."""
    registry = RunRegistry()
    run = registry.create_run(
        "simulation_run",
        SIM_ID,
        linked_ids={"simulation_id": SIM_ID},
        metadata={"budget": budget},
    )
    manifest = registry._read_run(run["run_id"])
    assert manifest is not None
    started = datetime.now() - started_ago
    manifest["status"] = status
    manifest["started_at"] = started.isoformat()
    manifest["completed_at"] = (
        (started + duration).isoformat() if duration is not None else None
    )
    registry._write_run(manifest)
    return run["run_id"]


def _enforcer(run_id: str) -> RunBudgetEnforcer:
    enforcer = RunBudgetEnforcer.for_run(run_id)
    assert enforcer is not None
    return enforcer


def _write_events(run_dirs: Path, run_id: str, count: int, tokens: int = 100) -> None:
    run_dir = run_dirs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "stage": "simulation_rounds",
        "provider_id": "openai",
        "model": "gpt-4o-mini",
        "base_url_sanitized": "https://api.openai.com",
        "timestamp": 1_700_000_000.0,
        "latency_ms": 100.0,
        "success": True,
        "prompt_tokens": tokens,
        "completion_tokens": 0,
    }
    with open(run_dir / "llm_call_events.jsonl", "w", encoding="utf-8") as handle:
        for _ in range(count):
            handle.write(json.dumps(event) + "\n")
    reset_usage_cache()


HARD_60S = {"max_duration_seconds": 60, "enforcement": "hard"}


def test_finished_job_within_limit_does_not_trip_time_dimension(run_dirs):
    run_id = _create_job(
        status="completed",
        started_ago=timedelta(hours=1),
        duration=timedelta(seconds=30),
        budget=HARD_60S,
    )
    enforcer = _enforcer(run_id)

    enforcer.check_before_call()  # wirft nicht
    enforcer.record_after_call()

    assert enforcer._observed(enforcer.consumed())["time"] == 30
    assert load_warnings(run_id) == []


def test_finished_job_that_exceeded_its_own_limit_still_trips_time(run_dirs):
    run_id = _create_job(
        status="stopped",
        started_ago=timedelta(hours=1),
        duration=timedelta(seconds=90),
        budget=HARD_60S,
    )

    with pytest.raises(BudgetExceededError) as excinfo:
        _enforcer(run_id).check_before_call()

    assert excinfo.value.dimension == "time"
    assert excinfo.value.observed == 90
    assert excinfo.value.threshold == 60


def test_running_job_over_time_trips_as_before(run_dirs):
    run_id = _create_job(
        status="processing",
        started_ago=timedelta(hours=1),
        duration=None,
        budget=HARD_60S,
    )

    with pytest.raises(BudgetExceededError) as excinfo:
        _enforcer(run_id).check_before_call()

    assert excinfo.value.dimension == "time"
    assert excinfo.value.observed >= 3600
    assert [w.dimension for w in load_warnings(run_id)] == ["time"]


def test_finished_job_still_enforces_call_limit(run_dirs):
    run_id = _create_job(
        status="completed",
        started_ago=timedelta(hours=1),
        duration=timedelta(seconds=30),
        budget={"max_duration_seconds": 60, "max_llm_calls": 2, "enforcement": "hard"},
    )
    _write_events(run_dirs, run_id, count=2)

    with pytest.raises(BudgetExceededError) as excinfo:
        _enforcer(run_id).check_before_call()

    assert excinfo.value.dimension == "calls"
    assert excinfo.value.termination_reason == "budget_calls"


def test_finished_job_still_enforces_token_limit(run_dirs):
    run_id = _create_job(
        status="completed",
        started_ago=timedelta(hours=1),
        duration=timedelta(seconds=30),
        budget={"max_duration_seconds": 60, "max_tokens": 150, "enforcement": "hard"},
    )
    _write_events(run_dirs, run_id, count=2, tokens=100)

    with pytest.raises(BudgetExceededError) as excinfo:
        _enforcer(run_id).check_before_call()

    assert excinfo.value.dimension == "tokens"
    assert excinfo.value.observed == 200
