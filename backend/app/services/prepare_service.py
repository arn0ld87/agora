"""Prepare-Service für Simulationen."""

from __future__ import annotations

import json  # noqa: F401
import os  # noqa: F401
import traceback  # noqa: F401
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple  # noqa: F401

from ..contracts import (
    PersonaQuotaPlan,
)
from ..contracts.llm_routing_contract import ResolvedRoute
from ..contracts.pipeline_degradation_contract import (
    DegradationKind,  # noqa: F401
    DegradationSeverity,  # noqa: F401
)
from ..utils.logger import get_logger
from .degradation_collector import DegradationCollector  # noqa: F401
from .entity_reader import EntityReader as EntityReader
from .llm_runtime import RuntimeLlmConfig
from .oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator  # noqa: F401
from .persona_eligibility import filter_eligible_entities as filter_eligible_entities
from .persona_identity_binding import write_identity_binding_manifest  # noqa: F401
from .persona_quota_defaults import default_dach_industry_quota  # noqa: F401
from .prepare_requirement_selection import requirement_hash as _requirement_hash  # noqa: F401
from .settings_layer import get_default_service as _get_settings  # noqa: F401
from .simulation_config_generator import SimulationConfigGenerator  # noqa: F401

if TYPE_CHECKING:
    from .entity_reader import EntityNode  # noqa: F401
    from .oasis_profile_models import PersonaDemographicSlot  # noqa: F401
    from .simulation_manager import SimulationManager, SimulationState

from . import prepare_checkpoint as _prepare_checkpoint  # noqa: F401
from . import prepare_entities as _prepare_entities
from . import prepare_llm as _prepare_llm
from . import prepare_quota as _prepare_quota
from . import prepare_service_helpers as _prepare_service_helpers
from . import prepare_service_orchestrator as _prepare_service_orchestrator
from . import prepare_skeptic_profiles as _prepare_skeptic_profiles

logger = get_logger("agora.prepare")

LlmRuntimeInput = RuntimeLlmConfig | ResolvedRoute


def _resolve_llm_connection(
    llm_runtime: Optional[LlmRuntimeInput], *, require: bool = True
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    return _prepare_llm._resolve_llm_connection(llm_runtime, require=require)


# Bestimmte und unbestimmte Artikel für Entitätsbezeichnungen.
_LEADING_ARTICLES = frozenset(
    {
        "der", "die", "das", "den", "dem", "des",
        "ein", "eine", "einen", "einem", "einer", "eines",
    }
)
_ADJECTIVE_SUFFIXES = ("er", "es", "em", "en", "e")
_MIN_ADJECTIVE_STEM_LENGTH = 4

# Entity normalization and filtering delegates
_strip_leading_article = _prepare_entities._strip_leading_article
_normalize_adjective_endings = _prepare_entities._normalize_adjective_endings
_entity_identity_key = _prepare_entities._entity_identity_key
_dedupe_entities = _prepare_entities._dedupe_entities
_cap_entities_across_types = _prepare_entities._cap_entities_across_types
_phase_read_entities = _prepare_entities._phase_read_entities
_phase_read_entities_from_checkpoint = _prepare_entities._phase_read_entities_from_checkpoint
_lookup_expanded_entities_from_checkpoint = _prepare_entities._lookup_expanded_entities_from_checkpoint

# Phase 2 & 3 delegates
_entity_uuids_or_none = _prepare_service_helpers._entity_uuids_or_none
_selection_reasons_or_empty = _prepare_service_helpers._selection_reasons_or_empty
_build_profile_checkpoint_hooks = _prepare_service_helpers._build_profile_checkpoint_hooks
_persist_identity_bindings = _prepare_service_helpers._persist_identity_bindings
_phase_generate_profiles = _prepare_service_helpers._phase_generate_profiles
_phase_generate_config = _prepare_service_helpers._phase_generate_config
_phase_profile_synthetic_skeptics = _prepare_skeptic_profiles._phase_profile_synthetic_skeptics
_resolve_phase1_result = _prepare_service_helpers._resolve_phase1_result

# Quota delegates
_expand_entities_for_quota = _prepare_quota._expand_entities_for_quota
_apply_persona_floor_to_entities = _prepare_quota._apply_persona_floor_to_entities
_apply_persona_floor_to_quota_plan = _prepare_quota._apply_persona_floor_to_quota_plan
compute_persona_target = _prepare_quota.compute_persona_target
_validate_persona_quota = _prepare_quota._validate_persona_quota


class PrepareCancelledError(Exception):
    """Signalisiert kooperativen Abbruch während ``prepare_simulation()``."""

    def __init__(self, state: "SimulationState") -> None:
        super().__init__(f"prepare_simulation cancelled for {state.simulation_id}")
        self.state = state


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
    return _prepare_service_orchestrator.prepare_simulation(
        manager,
        simulation_id,
        simulation_requirement,
        document_text,
        defined_entity_types=defined_entity_types,
        use_llm_for_profiles=use_llm_for_profiles,
        progress_callback=progress_callback,
        parallel_profile_count=parallel_profile_count,
        storage=storage,
        llm_model=llm_model,
        llm_runtime=llm_runtime,
        language=language,
        max_agents=max_agents,
        quota_plan=quota_plan,
        run_id=run_id,
        degradations=degradations,
        force_regenerate=force_regenerate,
        contested_question_override=contested_question_override,
        activity_mode=activity_mode,
    )


__all__ = [
    "prepare_simulation",
    "PrepareCancelledError",
    "compute_persona_target",
    "_apply_persona_floor_to_entities",
    "_apply_persona_floor_to_quota_plan",
    "_validate_persona_quota",
]
