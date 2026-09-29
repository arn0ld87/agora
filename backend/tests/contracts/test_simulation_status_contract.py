"""Contract-Tests fuer den Simulationsstatus (Issue #1713 Slice S2).

``SimulationStatusValue`` (``simulation_record_contract.py``) und
``RunnerStatusValue`` (``simulation_status_contract.py``) sind als Literal
gespiegelt statt importiert, damit die Contracts keine Laufzeit-Abhaengigkeit
auf ``app.services.simulation_manager``/``app.services.sim.run_state_store``
tragen (siehe Modul-Docstrings). Diese Tests halten beide Wertemengen
deckungsgleich mit den echten Enums — ein Drift (neuer Enum-Wert ohne
Literal-Nachzug) faellt hier auf.
"""
from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from app.contracts.simulation_record_contract import SimulationStatusValue
from app.contracts.simulation_status_contract import (
    RunnerStatusValue,
    SimulationStatusResponse,
)
from app.services.simulation_manager import SimulationStatus
from app.services.sim.run_state_store import RunnerStatus


def test_simulation_status_literal_matches_enum_values():
    assert set(get_args(SimulationStatusValue)) == {s.value for s in SimulationStatus}


def test_runner_status_literal_matches_enum_values():
    assert set(get_args(RunnerStatusValue)) == {s.value for s in RunnerStatus}


def _minimal_kwargs(**overrides):
    base = dict(
        simulation_id="sim_0123456789ab",
        project_id="proj-1",
        graph_id="graph-1",
        enable_twitter=True,
        enable_reddit=True,
        status="running",
        entities_count=0,
        profiles_count=0,
        entity_types=[],
        config_generated=False,
        config_reasoning="",
        current_round=0,
        twitter_status="not_started",
        reddit_status="not_started",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        branch_depth=0,
        interview_env_alive=False,
    )
    base.update(overrides)
    return base


def test_valid_payload_round_trips():
    payload = SimulationStatusResponse(**_minimal_kwargs(status="completed", runner_status="completed"))
    dumped = payload.model_dump(mode="json")
    assert dumped["status"] == "completed"
    assert dumped["runner_status"] == "completed"
    assert dumped["interview_env_alive"] is False


def test_runner_status_none_is_allowed():
    payload = SimulationStatusResponse(**_minimal_kwargs(runner_status=None))
    assert payload.runner_status is None


def test_unknown_status_value_rejected():
    with pytest.raises(ValidationError):
        SimulationStatusResponse(**_minimal_kwargs(status="unbekannt"))


def test_unknown_runner_status_value_rejected():
    with pytest.raises(ValidationError):
        SimulationStatusResponse(**_minimal_kwargs(runner_status="unbekannt"))


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        SimulationStatusResponse(**_minimal_kwargs(unexpected_field=True))
