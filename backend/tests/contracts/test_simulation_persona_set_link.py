"""Rueckverweis vom Lauf auf den Personasatz (Issue #1807, E7-B1).

``persona_set_id`` steht optional am Simulationszustand. Ohne Satz bleiben
``state.json`` und Antworten byte-identisch (Schluessel fehlt), Altbestand ohne
das Feld bleibt lesbar.
"""

from __future__ import annotations

from app.contracts.persona_contract import PersonaModel
from app.contracts.simulation_record_contract import SimulationRecord
from app.contracts.simulation_status_contract import SimulationStatusResponse
from app.services.simulation_manager import SimulationState, SimulationStatus


def _state(**overrides) -> SimulationState:
    return SimulationState(
        simulation_id="sim_link00000001",
        project_id="proj_000000000001",
        graph_id="",
        status=SimulationStatus.READY,
        **overrides,
    )


def _status_kwargs(**overrides):
    base = dict(
        simulation_id="sim_link00000001",
        project_id="proj-1",
        graph_id="",
        enable_twitter=True,
        enable_reddit=True,
        status="ready",
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


def test_zustand_ohne_satz_schreibt_den_schluessel_nicht():
    assert "persona_set_id" not in _state().to_dict()
    assert "persona_set_id" not in SimulationRecord.from_dict(_state().to_dict()).to_dict()


def test_zustand_mit_satz_schreibt_und_liest_den_verweis_verlustfrei():
    state = _state(persona_set_id="pset_000000000001")

    data = state.to_dict()
    record = SimulationRecord.from_dict(data)

    assert data["persona_set_id"] == "pset_000000000001"
    assert record.persona_set_id == "pset_000000000001"
    assert record.to_dict() == data


def test_schluesselmenge_von_zustand_und_record_bleibt_gleich():
    for state in (_state(), _state(persona_set_id="pset_000000000001")):
        assert set(state.to_dict()) == set(
            SimulationRecord.from_dict(state.to_dict()).to_dict()
        )


def test_altbestand_ohne_das_feld_bleibt_lesbar():
    legacy = _state().to_dict()
    assert "persona_set_id" not in legacy

    record = SimulationRecord.from_dict(legacy)

    assert record.persona_set_id is None


def test_altbestand_mit_explizitem_null_bleibt_lesbar():
    record = SimulationRecord.from_dict(
        {**_state().to_dict(), "persona_set_id": None}
    )

    assert record.persona_set_id is None
    assert "persona_set_id" not in record.to_dict()


def test_leseantwort_ohne_satz_laesst_das_feld_aus():
    dumped = SimulationStatusResponse(**_status_kwargs()).model_dump(mode="json")

    assert "persona_set_id" not in dumped


def test_leseantwort_mit_satz_liefert_die_kennung():
    dumped = SimulationStatusResponse(
        **_status_kwargs(persona_set_id="pset_000000000001")
    ).model_dump(mode="json")

    assert dumped["persona_set_id"] == "pset_000000000001"


def test_laufprofil_kennt_die_herkunft_im_satz_optional():
    assert PersonaModel.model_fields["persona_set_origin"].default is None
    assert PersonaModel.model_fields["persona_set_origin"].is_required() is False
