"""Job-Auflösung für Interview-Budgets (#1805, F3).

``_resolve_budget_run_id`` wählt bei mehreren ``simulation_run``-Jobs einer
Simulation (Neustart) deterministisch den jüngsten nach Anlagezeit, warnt bei
mehr als einem Treffer und protokolliert einen Job ohne Budget-Konfiguration als
``interview_unbudgeted … reason=no_budget_config``. Echte ``RunRegistry``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.api.simulation_interviews import _resolve_budget_run_id
from app.services.run_registry import RunRegistry

SIM_ID = "sim_0123456789ab"
BUDGET = {"max_tokens": 1000, "enforcement": "hard"}


@pytest.fixture
def fake_logger(monkeypatch) -> MagicMock:
    logger = MagicMock()
    monkeypatch.setattr("app.api.simulation_interviews.logger", logger)
    return logger


def _create_job(
    *,
    started_ago: timedelta,
    budget: Optional[Dict[str, Any]] = BUDGET,
    run_type: str = "simulation_run",
    simulation_id: str = SIM_ID,
) -> str:
    registry = RunRegistry()
    run = registry.create_run(
        run_type,
        simulation_id,
        linked_ids={"simulation_id": simulation_id},
        metadata={"budget": budget} if budget else {},
    )
    manifest = registry._read_run(run["run_id"])
    assert manifest is not None
    manifest["started_at"] = (datetime.now() - started_ago).isoformat()
    registry._write_run(manifest)
    return run["run_id"]


def _messages(logger: MagicMock) -> List[str]:
    return [call.args[0] for call in logger.warning.call_args_list]


def test_newest_job_by_creation_wins_over_most_recently_updated(fake_logger):
    older = _create_job(started_ago=timedelta(hours=2))
    newer = _create_job(started_ago=timedelta(hours=1))
    # Der ältere Job wird zuletzt aktualisiert: ``get_latest_by_linked_id``
    # (Sortierung nach ``updated_at``) lieferte ihn, die Anlagezeit nicht.
    RunRegistry().update_run(older, message="nachträglich aktualisiert")
    latest = RunRegistry().get_latest_by_linked_id(
        "simulation_id", SIM_ID, run_type="simulation_run"
    )
    assert latest is not None and latest["run_id"] == older

    assert _resolve_budget_run_id(SIM_ID) == newer

    multi = [m for m in _messages(fake_logger) if "interview_budget_multiple_runs" in m]
    assert len(multi) == 1
    call = next(
        c for c in fake_logger.warning.call_args_list
        if "interview_budget_multiple_runs" in c.args[0]
    )
    assert call.args[1:] == (SIM_ID, 2, newer)


def test_single_job_is_resolved_without_warning(fake_logger):
    job = _create_job(started_ago=timedelta(hours=1))

    assert _resolve_budget_run_id(SIM_ID) == job
    fake_logger.warning.assert_not_called()


def test_job_without_budget_config_is_logged_as_unbudgeted(fake_logger):
    job = _create_job(started_ago=timedelta(hours=1), budget=None)

    assert _resolve_budget_run_id(SIM_ID) == job

    fake_logger.warning.assert_called_once()
    call = fake_logger.warning.call_args
    assert "interview_unbudgeted" in call.args[0]
    assert "reason=no_budget_config" in call.args[0]
    assert call.args[1:] == (SIM_ID, job)


def test_budget_is_judged_on_the_chosen_job(fake_logger):
    """Ein älterer Job ohne Budget zählt nicht, wenn der jüngste eines hat."""
    _create_job(started_ago=timedelta(hours=2), budget=None)
    newer = _create_job(started_ago=timedelta(hours=1))

    assert _resolve_budget_run_id(SIM_ID) == newer

    assert [m for m in _messages(fake_logger) if "interview_unbudgeted" in m] == []


def test_without_simulation_run_keeps_no_simulation_run_reason(fake_logger):
    _create_job(started_ago=timedelta(hours=1), run_type="report_generate")

    assert _resolve_budget_run_id(SIM_ID) is None

    fake_logger.warning.assert_called_once()
    assert "reason=no_simulation_run" in fake_logger.warning.call_args.args[0]


def test_jobs_of_other_simulations_are_ignored(fake_logger):
    _create_job(started_ago=timedelta(hours=1), simulation_id="sim_ffffffffffff")

    assert _resolve_budget_run_id(SIM_ID) is None
