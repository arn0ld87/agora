"""Orchestrator for simulation preparation phases."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any, Callable, List, Optional

from ..contracts import PersonaQuotaPlan
from .prepare_requirement_selection import requirement_hash as _requirement_hash
from .settings_layer import get_default_service as _get_settings

if TYPE_CHECKING:
    from .degradation_collector import DegradationCollector
    from .prepare_service import LlmRuntimeInput
    from .simulation_manager import SimulationManager, SimulationState


def prepare_simulation(
    manager: SimulationManager,
    simulation_id: str,
    simulation_requirement: str,
    document_text: str,
    *,
    defined_entity_types: Optional[List[str]] = None,
    use_llm_for_profiles: bool = True,
    progress_callback: Optional[Callable] = None,
    parallel_profile_count: Optional[int] = None,
    storage: Any = None,
    llm_model: Optional[str] = None,
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str] = None,
    max_agents: Optional[int] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    run_id: Optional[str] = None,
    degradations: Optional[DegradationCollector] = None,
    force_regenerate: bool = False,
    contested_question_override: Optional[str] = None,
    activity_mode: Optional[str] = None,
) -> SimulationState:
    """Orchestrator für die drei Prepare-Phasen."""
    from . import prepare_checkpoint as _prepare_checkpoint
    from . import prepare_service as _ps
    from .report_agent import MIN_PERSONA_TABLE_ROWS
    from .sim.cancel_flag import is_cancel_requested
    from .simulation_manager import SimulationStatus

    state = manager._load_simulation_state(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    if force_regenerate:
        _prepare_checkpoint.clear_checkpoint(simulation_id)

    def _raise_if_cancelled() -> None:
        if run_id and is_cancel_requested(run_id):
            manager._set_status(state, SimulationStatus.CANCELLED_PARTIAL)
            raise _ps.PrepareCancelledError(state)

    try:
        manager._set_status(state, SimulationStatus.PREPARING)

        sim_dir = manager._get_simulation_dir(simulation_id)

        persona_floor = MIN_PERSONA_TABLE_ROWS
        if max_agents is not None and max_agents > 0:
            persona_floor = min(persona_floor, max_agents)
        state.persona_floor = persona_floor
        manager._save_simulation_state(state)

        quota_plan = _ps._apply_persona_floor_to_quota_plan(
            quota_plan, minimum=persona_floor
        )
        effective_quota_plan_snapshot = (
            quota_plan.model_dump() if quota_plan is not None else None
        )

        _raise_if_cancelled()

        filtered, resume_checkpoint, precomputed_entities = _ps._resolve_phase1_result(
            state=state,
            storage=storage,
            simulation_id=simulation_id,
            sim_dir=sim_dir,
            defined_entity_types=defined_entity_types,
            max_agents=max_agents,
            persona_floor=persona_floor,
            use_llm_for_profiles=use_llm_for_profiles,
            effective_quota_plan_snapshot=effective_quota_plan_snapshot,
            progress_callback=progress_callback,
            degradations=degradations,
            llm_model=llm_model,
            language=language,
            simulation_requirement=simulation_requirement,
            llm_runtime=llm_runtime,
            run_id=run_id,
        )

        if filtered.filtered_count == 0:
            raise ValueError(
                "No entities matching criteria found, check if graph is correctly constructed"
            )

        if parallel_profile_count is None:
            parallel_profile_count = int(
                _get_settings().effective_value("AGORA_PARALLEL_PERSONA_COUNT")
            )

        _raise_if_cancelled()

        # Phase 2: Generate Agent Profiles
        profiles, expanded_entities = _ps._phase_generate_profiles(
            state,
            storage,
            filtered,
            sim_dir,
            llm_model=llm_model,
            llm_runtime=llm_runtime,
            language=language,
            use_llm_for_profiles=use_llm_for_profiles,
            parallel_profile_count=parallel_profile_count,
            progress_callback=progress_callback,
            quota_plan=quota_plan,
            persona_floor=persona_floor,
            max_agents=max_agents,
            run_id=run_id,
            degradations=degradations,
            defined_entity_types=defined_entity_types,
            resume_checkpoint=resume_checkpoint,
            precomputed_entities=precomputed_entities,
            requirement_hash=_requirement_hash(simulation_requirement),
        )

        _raise_if_cancelled()

        if quota_plan is not None:
            _ps._validate_persona_quota(quota_plan, profiles)

        # Phase 3: LLM-driven config generation
        _ps._phase_generate_config(
            manager,
            state,
            simulation_id,
            simulation_requirement,
            document_text,
            expanded_entities=expanded_entities,
            llm_model=llm_model,
            llm_runtime=llm_runtime,
            language=language,
            use_llm=use_llm_for_profiles,
            progress_callback=progress_callback,
            quota_plan=quota_plan,
            run_id=run_id,
            degradations=degradations,
            contested_question_override=contested_question_override,
            activity_mode=activity_mode,
            profiles=profiles,
            sim_dir=sim_dir,
        )

        blocking = (
            [event for event in degradations.report().events if event.is_blocking]
            if degradations is not None
            else []
        )
        if blocking:
            state.error = " ".join(event.detail for event in blocking)
            manager._set_status(state, SimulationStatus.FAILED)
            _ps.logger.error(
                "Simulation preparation blocked by degradation: %s, kinds=%s",
                simulation_id,
                ", ".join(event.kind.value for event in blocking),
            )
            return state

        manager._set_status(state, SimulationStatus.READY)

        _ps.logger.info(
            f"Simulation preparation completed: {simulation_id}, "
            f"entities={state.entities_count}, profiles={state.profiles_count}"
        )

        return state

    except _ps.PrepareCancelledError:
        _ps.logger.info(
            "Simulation preparation cancelled by user: %s (run_id=%s)",
            simulation_id,
            run_id,
        )
        raise
    except Exception as exc:
        _ps.logger.error(
            f"Simulation preparation failed: {simulation_id}, error={exc}"
        )
        _ps.logger.error(traceback.format_exc())
        state.error = str(exc)
        manager._set_status(state, SimulationStatus.FAILED)
        raise
