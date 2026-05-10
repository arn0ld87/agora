"""Sub-Slice 20a — API-Pass-Through für PersonaQuotaPlan.

Verifiziert:
- ``_parse_quota_plan`` parsed Body-Felder korrekt in ein
  ``PersonaQuotaPlan``-Modell und propagiert ``ValidationError``.
- Backwards-Compat: ohne ``quota_plan`` im Body bleibt das Verhalten
  unverändert (Helper liefert ``None``).
- ``SimulationManager.prepare_simulation`` akzeptiert den
  ``quota_plan``-kwarg und reicht ihn an ``prepare_service.prepare_simulation``
  durch (Pass-Through, keine Generator-Erzwingung — das ist 20b).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.simulation_prepare import _parse_quota_plan, _resolve_max_agents_with_floor
from app.services.report_agent import MIN_PERSONA_TABLE_ROWS
from app.contracts import PersonaQuotaPlan
from app.services import prepare_service
from app.services.simulation_manager import SimulationManager


# ---- _parse_quota_plan -----------------------------------------------------


def test_parse_quota_plan_returns_none_when_field_missing():
    assert _parse_quota_plan({}) is None


def test_parse_quota_plan_returns_none_when_field_explicit_none():
    assert _parse_quota_plan({"quota_plan": None}) is None


def test_parse_quota_plan_returns_none_when_field_empty_dict():
    # Empty dict ist kein gültiger Plan — Helper soll als "nicht gesetzt"
    # interpretieren, statt eine ValidationError für leere targets zu werfen.
    assert _parse_quota_plan({"quota_plan": {}}) is None


def test_parse_quota_plan_returns_model_for_valid_payload():
    payload = {
        "quota_plan": {
            "targets": {"kmu_ceo": 8, "it_admin": 6},
            "total": 14,
        }
    }
    plan = _parse_quota_plan(payload)
    assert isinstance(plan, PersonaQuotaPlan)
    assert plan.total == 14
    assert plan.targets == {"kmu_ceo": 8, "it_admin": 6}


def test_parse_quota_plan_propagates_validation_error_on_total_mismatch():
    payload = {
        "quota_plan": {
            "targets": {"kmu_ceo": 8, "it_admin": 6},
            "total": 99,  # !=14
        }
    }
    with pytest.raises(ValidationError):
        _parse_quota_plan(payload)


def test_parse_quota_plan_propagates_validation_error_on_invalid_target_value():
    payload = {
        "quota_plan": {
            "targets": {"kmu_ceo": 0},  # min ge=1
            "total": 0,
        }
    }
    with pytest.raises(ValidationError):
        _parse_quota_plan(payload)


def test_parse_quota_plan_rejects_non_dict_payload():
    payload = {"quota_plan": "not-a-dict"}
    with pytest.raises(ValidationError):
        _parse_quota_plan(payload)


def test_resolve_max_agents_with_floor_enforces_minimum():
    assert _resolve_max_agents_with_floor(1) == MIN_PERSONA_TABLE_ROWS
    assert _resolve_max_agents_with_floor("25") == MIN_PERSONA_TABLE_ROWS
    assert _resolve_max_agents_with_floor(MIN_PERSONA_TABLE_ROWS + 5) == MIN_PERSONA_TABLE_ROWS + 5
    assert _resolve_max_agents_with_floor(None) is None
    assert _resolve_max_agents_with_floor("invalid") is None


# ---- SimulationManager.prepare_simulation pass-through ---------------------


def test_simulation_manager_prepare_passes_quota_plan(monkeypatch):
    """``manager.prepare_simulation(quota_plan=...)`` reicht den Plan an den
    Service-Layer durch. Smoke ohne echten Storage."""
    received = {}

    def fake_prepare_simulation(manager, simulation_id, simulation_requirement,
                                document_text, **kwargs):
        received.update(kwargs)
        received["simulation_id"] = simulation_id
        return MagicMock(name="state")

    monkeypatch.setattr(
        prepare_service, "prepare_simulation", fake_prepare_simulation
    )

    plan = PersonaQuotaPlan(targets={"a": 2, "b": 3}, total=5)
    manager = SimulationManager.__new__(SimulationManager)

    manager.prepare_simulation(
        simulation_id="sim_test",
        simulation_requirement="req",
        document_text="doc",
        quota_plan=plan,
    )

    assert received["simulation_id"] == "sim_test"
    assert received["quota_plan"] is plan


def test_simulation_manager_prepare_default_quota_plan_is_none(monkeypatch):
    """Backwards-Compat: alter Caller ohne ``quota_plan`` darf weiter
    funktionieren, Service bekommt ``None``."""
    received = {}

    def fake_prepare_simulation(manager, simulation_id, simulation_requirement,
                                document_text, **kwargs):
        received.update(kwargs)
        return MagicMock(name="state")

    monkeypatch.setattr(
        prepare_service, "prepare_simulation", fake_prepare_simulation
    )

    manager = SimulationManager.__new__(SimulationManager)
    manager.prepare_simulation(
        simulation_id="sim_test",
        simulation_requirement="req",
        document_text="doc",
    )

    assert received.get("quota_plan") is None
