"""Bug-Fix-Test: Expanded entities propagate from Phase 2 to Phase 3.

Stellt sicher, dass _phase_generate_profiles die expandierten Entities
zurückgibt und _phase_generate_config sie an generate_config weiterleitet.
Vor dem Fix wurde generate_config mit filtered.entities (unexpanded) aufgerufen.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.contracts import PersonaQuotaPlan
from app.services import prepare_service


def _make_entity(name: str) -> MagicMock:
    e = MagicMock(name=f"Entity({name})")
    e.get_entity_type.return_value = "Person"
    return e


def _make_filtered(n: int):
    filtered = MagicMock(name="FilteredEntities")
    filtered.entities = [_make_entity(f"e{i}") for i in range(n)]
    return filtered


def test_expanded_entities_propagate_to_config_generator(monkeypatch):
    """Phase 2 gibt (profiles, expanded) zurück; Phase 3 bekommt expanded."""
    n_input = 5
    n_expanded = 50

    filtered = _make_filtered(n_input)
    quota_plan = PersonaQuotaPlan(
        targets={"Person": n_expanded},
        total=n_expanded,
    )

    # Make _expand_entities_for_quota return 50 mock entities
    fake_expanded = [_make_entity(f"exp{i}") for i in range(n_expanded)]
    monkeypatch.setattr(
        prepare_service, "_expand_entities_for_quota",
        lambda entities, plan: fake_expanded,
    )
    # Floor helper: pass-through
    monkeypatch.setattr(
        prepare_service, "_apply_persona_floor_to_entities",
        lambda entities, **kw: entities,
    )

    # Mock profile generation internals so Phase 2 completes without LLM
    fake_profile = MagicMock(name="Profile")
    fake_generator_instance = MagicMock()
    fake_generator_instance.generate_profile.return_value = fake_profile
    monkeypatch.setattr(
        prepare_service, "OasisProfileGenerator",
        lambda **kw: fake_generator_instance,
    )

    # Also stub the progress callback helper if present
    state = MagicMock(name="SimulationState")
    state.project_id = "proj_test"
    state.graph_id = "g_test"
    state.enable_twitter = False
    state.enable_reddit = True
    storage = MagicMock(name="Storage")

    profiles, expanded = prepare_service._phase_generate_profiles(
        state,
        storage,
        filtered,
        "/tmp/sim_dir",
        llm_model=None,
        llm_runtime=None,
        language="de",
        use_llm_for_profiles=False,
        parallel_profile_count=1,
        progress_callback=None,
        quota_plan=quota_plan,
    )

    assert len(expanded) == n_expanded, (
        f"Expected {n_expanded} expanded entities, got {len(expanded)}"
    )

    # Now verify Phase 3 passes expanded entities to generate_config
    fake_params = MagicMock(
        to_json=lambda: '{"time_config": {}, "agent_config": []}',
        generation_reasoning="ok",
    )
    mock_generate_config = MagicMock(return_value=fake_params)
    fake_config_generator = MagicMock()
    fake_config_generator.generate_config = mock_generate_config
    monkeypatch.setattr(
        prepare_service, "SimulationConfigGenerator",
        lambda **kw: fake_config_generator,
    )

    manager = MagicMock(name="SimulationManager")

    prepare_service._phase_generate_config(
        manager,
        state,
        "sim_test",
        "requirement",
        "doc text",
        expanded_entities=expanded,
        llm_model=None,
        llm_runtime=None,
        language="de",
        quota_plan=quota_plan,
    )

    assert mock_generate_config.called, "generate_config was not called"
    called_entities = mock_generate_config.call_args.kwargs.get("entities")
    assert called_entities is not None, "entities kwarg missing from generate_config call"
    assert len(called_entities) == n_expanded, (
        f"generate_config got {len(called_entities)} entities, expected {n_expanded}. "
        "Floor-Check in simulation_config_generator.py should no longer fire."
    )
