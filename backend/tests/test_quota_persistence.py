"""Sub-Slice 22 — Gemini-Followup auf 20a.

Drei Findings auf [PR #181](https://github.com/arn0ld87/agora/pull/181):

- HIGH: ``quota_plan`` wurde im Restart-Pfad aus ``simulation_config.json``
  gelesen, aber **nirgends gespeichert** — Restart bekam immer ``None``,
  Plan-Drift beim Restart ohne Warnung.
- MEDIUM: ``except Exception`` im View-Handler maskiert echte 500er als 400.
- MEDIUM: ``ValidationError``-Import fehlt für saubere Type-Hints.

Diese Tests pinnen den Persistenz-Pfad und das Exception-Verhalten.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.contracts import PersonaQuotaPlan


# ---- Persistenz: _phase_generate_config schreibt quota_plan ----------------


def _make_phase_inputs():
    """Common-Mocks für _phase_generate_config-Aufrufe."""
    manager = MagicMock(name="SimulationManager")
    state = MagicMock(name="SimulationState")
    state.project_id = "proj_x"
    state.graph_id = "g_x"
    state.enable_twitter = True
    state.enable_reddit = True

    filtered = MagicMock(name="FilteredEntities")
    filtered.entities = []

    return manager, state, filtered


def test_phase_generate_config_persists_quota_plan(monkeypatch):
    """Wenn ein quota_plan übergeben wird, landet er als Top-Level-Key
    ``quota_plan`` im persistierten ``simulation_config``."""
    from app.services import prepare_service

    fake_params = MagicMock(
        to_json=lambda: '{"time_config": {}, "agent_config": []}',
        generation_reasoning="ok",
    )
    fake_generator = MagicMock(generate_config=MagicMock(return_value=fake_params))
    monkeypatch.setattr(
        prepare_service, "SimulationConfigGenerator", lambda **kw: fake_generator
    )

    manager, state, filtered = _make_phase_inputs()
    plan = PersonaQuotaPlan(targets={"kmu": 8, "admin": 6}, total=14)

    prepare_service._phase_generate_config(
        manager,
        state,
        "sim_xyz",
        "requirement",
        "doc",
        filtered,
        llm_model=None,
        language=None,
        quota_plan=plan,
    )

    written = manager._store.write_json.call_args
    assert written.args[0] == "sim_xyz"
    assert written.args[1] == "simulation_config"
    payload = written.args[2]
    assert "quota_plan" in payload
    assert payload["quota_plan"] == {"targets": {"kmu": 8, "admin": 6}, "total": 14}


def test_phase_generate_config_omits_quota_plan_when_none(monkeypatch):
    """Backwards-Compat: ohne quota_plan kein Schlüssel im Config."""
    from app.services import prepare_service

    fake_params = MagicMock(
        to_json=lambda: '{"time_config": {}}',
        generation_reasoning="ok",
    )
    fake_generator = MagicMock(generate_config=MagicMock(return_value=fake_params))
    monkeypatch.setattr(
        prepare_service, "SimulationConfigGenerator", lambda **kw: fake_generator
    )

    manager, state, filtered = _make_phase_inputs()

    prepare_service._phase_generate_config(
        manager,
        state,
        "sim_xyz",
        "requirement",
        "doc",
        filtered,
        llm_model=None,
        language=None,
        quota_plan=None,
    )

    written = manager._store.write_json.call_args
    payload = written.args[2]
    assert "quota_plan" not in payload


def test_quota_plan_round_trip_via_parse_helper():
    """Persisted dict aus simulation_config kann vom Restart-Helper
    ``_parse_quota_plan`` direkt wieder als ``PersonaQuotaPlan`` geparsed
    werden — kein Schema-Drift zwischen Schreib- und Lesepfad."""
    from app.api.simulation_prepare import _parse_quota_plan

    plan = PersonaQuotaPlan(targets={"kmu": 8, "admin": 6}, total=14)
    persisted_config = {
        "time_config": {},
        "quota_plan": plan.model_dump(),
    }

    parsed = _parse_quota_plan(persisted_config)
    assert isinstance(parsed, PersonaQuotaPlan)
    assert parsed.total == 14
    assert parsed.targets == {"kmu": 8, "admin": 6}


# ---- Exception-Specifity im View ------------------------------------------


def test_parse_quota_plan_raises_validation_error_not_generic():
    """Validator soll ``ValidationError`` werfen — der View kann dann
    spezifisch fangen, statt ``Exception`` zu maskieren."""
    from app.api.simulation_prepare import _parse_quota_plan

    with pytest.raises(ValidationError):
        _parse_quota_plan({"quota_plan": {"targets": {"a": 1}, "total": 99}})


def test_parse_quota_plan_raises_validation_error_for_string_payload():
    """Non-Dict-Payload löst ebenfalls Pydantic-ValidationError aus."""
    from app.api.simulation_prepare import _parse_quota_plan

    with pytest.raises(ValidationError):
        _parse_quota_plan({"quota_plan": "string-not-dict"})
