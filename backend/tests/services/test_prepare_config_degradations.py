"""#1759 A6-Verdrahtung: ``_phase_generate_config`` reicht den Sammler durch.

``SimulationConfigGenerator.generate_config`` meldet ``stance_position_unrepresented``
und ``initial_post_stance_conflict`` seit Slice 2b über einen
``DegradationCollector``. Ohne Durchreichung aus dem Prepare-Lauf standen sie nur
im Log, nie im Task-Ergebnis.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services import prepare_service
from app.services.degradation_collector import DegradationCollector
from app.services.llm_runtime import RuntimeLlmConfig


def _runtime() -> RuntimeLlmConfig:
    return RuntimeLlmConfig(
        provider="custom_openai",
        api_key="runtime-override-placeholder",
        base_url="http://llm.invalid/v1",
    )


def _phase_inputs():
    manager = MagicMock(name="SimulationManager")
    state = MagicMock(name="SimulationState")
    state.project_id = "proj_x"
    state.graph_id = "g_x"
    state.enable_twitter = True
    state.enable_reddit = True
    return manager, state


def _patch_generator(monkeypatch):
    fake_params = MagicMock(
        to_json=lambda: '{"time_config": {}}',
        generation_reasoning="ok",
    )
    generator = MagicMock(generate_config=MagicMock(return_value=fake_params))
    monkeypatch.setattr(
        prepare_service, "SimulationConfigGenerator", lambda **kw: generator
    )
    return generator


def test_phase_generate_config_passes_collector_to_generator(monkeypatch):
    generator = _patch_generator(monkeypatch)
    manager, state = _phase_inputs()
    collector = DegradationCollector()

    prepare_service._phase_generate_config(
        manager,
        state,
        "sim_xyz",
        "requirement",
        "doc",
        expanded_entities=[],
        llm_model=None,
        llm_runtime=_runtime(),
        language=None,
        degradations=collector,
    )

    assert generator.generate_config.call_args.kwargs["degradations"] is collector


def test_phase_generate_config_without_collector_passes_none(monkeypatch):
    generator = _patch_generator(monkeypatch)
    manager, state = _phase_inputs()

    prepare_service._phase_generate_config(
        manager,
        state,
        "sim_xyz",
        "requirement",
        "doc",
        expanded_entities=[],
        llm_model=None,
        llm_runtime=_runtime(),
        language=None,
    )

    assert generator.generate_config.call_args.kwargs["degradations"] is None
