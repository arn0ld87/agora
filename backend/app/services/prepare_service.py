"""Prepare-Service für Simulationen.

Issue #43 (EPIC-06-ST-03): Aus ``SimulationManager.prepare_simulation`` (244
LOC) in drei klare Phasen-Funktionen plus Top-Level-Orchestrator extrahiert.
Funktionen nehmen einen ``SimulationManager`` als ersten Parameter — gleiches
Muster wie ``branching_service``, vermeidet zirkuläre Importe.

Phasen:

* :func:`_phase_read_entities` — Graph anbinden, Entities filtern, optional
  ``max_agents``-Cap.
* :func:`_phase_generate_profiles` — OASIS-Profiles generieren (parallel,
  Realtime-Save), für Reddit als JSON, für Twitter als CSV speichern.
* :func:`_phase_generate_config` — Simulation-Config per LLM generieren,
  atomar in den ``ArtifactStore`` schreiben.

Der Orchestrator :func:`prepare_simulation` setzt FSM-Status PREPARING/READY
um die Phasen herum und routet Fehler ins FAILED.
"""

from __future__ import annotations

import json
import os
import traceback
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..contracts import PersonaQuotaActual, PersonaQuotaPlan
from ..utils.logger import get_logger
from .entity_reader import EntityReader
from .oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator
from .simulation_config_generator import SimulationConfigGenerator

if TYPE_CHECKING:
    from .simulation_manager import SimulationManager, SimulationState

logger = get_logger("agora.prepare")


def _phase_read_entities(
    state: SimulationState,
    storage: Any,
    defined_entity_types: Optional[List[str]],
    max_agents: Optional[int],
    progress_callback: Optional[Callable] = None,
):
    """Phase 1: Entities aus dem Graphen lesen + filtern + cappen.

    Aktualisiert ``state.entities_count`` und ``state.entity_types`` als
    Seiteneffekt; gibt das ``FilteredEntities``-Objekt zurück.
    """
    if progress_callback:
        progress_callback("reading", 0, "Connecting to graph...")

    if not storage:
        raise ValueError("storage (GraphStorage) is required for prepare_simulation")
    reader = EntityReader(storage)

    if progress_callback:
        progress_callback("reading", 30, "Reading node data...")

    filtered = reader.filter_defined_entities(
        graph_id=state.graph_id,
        defined_entity_types=defined_entity_types,
        enrich_with_edges=True,
    )

    # User-controlled cap on number of agents (optional).
    # Truncates the entity list before persona generation. Entities are
    # kept in reader order so the most relevant ones win if the reader
    # already sorts by degree/importance.
    if (
        max_agents is not None
        and max_agents > 0
        and len(filtered.entities) > max_agents
    ):
        logger.info(
            f"Capping agent count at {max_agents} "
            f"(originally {len(filtered.entities)} entities)"
        )
        filtered.entities = filtered.entities[:max_agents]
        filtered.filtered_count = len(filtered.entities)

    state.entities_count = filtered.filtered_count
    state.entity_types = list(filtered.entity_types)

    if progress_callback:
        progress_callback(
            "reading", 100,
            f"Completed, total {filtered.filtered_count} entities",
            current=filtered.filtered_count,
            total=filtered.filtered_count,
        )

    return filtered


def _phase_generate_profiles(
    state: SimulationState,
    storage: Any,
    filtered,
    sim_dir: str,
    *,
    llm_model: Optional[str],
    language: Optional[str],
    use_llm_for_profiles: bool,
    parallel_profile_count: int,
    progress_callback: Optional[Callable] = None,
) -> List[Any]:
    """Phase 2: OASIS-Profiles generieren und im Sim-Dir ablegen.

    Aktualisiert ``state.profiles_count`` als Seiteneffekt; gibt die
    Liste der generierten Profile zurück.
    """
    total_entities = len(filtered.entities)

    if progress_callback:
        progress_callback(
            "generating_profiles", 0,
            "Starting generation...",
            current=0,
            total=total_entities,
        )

    # Pass graph_id to enable graph retrieval functionality, get richer context.
    # Per-simulation overrides for model + language come from API request.
    generator = OasisProfileGenerator(
        storage=storage,
        graph_id=state.graph_id,
        model_name=llm_model,
        language=language,
    )

    def profile_progress(current, total, msg):
        if progress_callback:
            progress_callback(
                "generating_profiles",
                int(current / total * 100),
                msg,
                current=current,
                total=total,
                item_name=msg,
            )

    # Set real-time save file path (prefer Reddit JSON format)
    realtime_output_path: Optional[str] = None
    realtime_platform = "reddit"
    if state.enable_reddit:
        realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
        realtime_platform = "reddit"
    elif state.enable_twitter:
        realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
        realtime_platform = "twitter"

    profiles = generator.generate_profiles_from_entities(
        entities=filtered.entities,
        use_llm=use_llm_for_profiles,
        progress_callback=profile_progress,
        graph_id=state.graph_id,
        parallel_count=parallel_profile_count,
        realtime_output_path=realtime_output_path,
        output_platform=realtime_platform,
    )

    state.profiles_count = len(profiles)

    # Save Profile files (Note: Twitter uses CSV format, Reddit uses JSON format)
    # Reddit has been saved in real-time during generation, save once more here to ensure completeness
    if progress_callback:
        progress_callback(
            "generating_profiles", 95,
            "Saving Profile files...",
            current=total_entities,
            total=total_entities,
        )

    if state.enable_reddit:
        generator.save_profiles(
            profiles=profiles,
            file_path=os.path.join(sim_dir, "reddit_profiles.json"),
            platform="reddit",
        )

    if state.enable_twitter:
        # Twitter uses CSV format! This is OASIS requirement
        generator.save_profiles(
            profiles=profiles,
            file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
            platform="twitter",
        )

    if progress_callback:
        progress_callback(
            "generating_profiles", 100,
            f"Completed, total {len(profiles)} Profiles",
            current=len(profiles),
            total=len(profiles),
        )

    return profiles


def _phase_generate_config(
    manager: SimulationManager,
    state: SimulationState,
    simulation_id: str,
    simulation_requirement: str,
    document_text: str,
    filtered,
    *,
    llm_model: Optional[str],
    language: Optional[str],
    progress_callback: Optional[Callable] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
) -> None:
    """Phase 3: Simulation-Config per LLM erzeugen + atomar persistieren.

    Aktualisiert ``state.config_generated`` und ``state.config_reasoning``
    als Seiteneffekt; speichert die Config über den ``ArtifactStore``.

    Sub-Slice 22 (Gemini-Followup auf 20a): wenn ``quota_plan`` gesetzt
    ist, wird er als Top-Level-Key ``quota_plan`` in
    ``simulation_config.json`` mitgeschrieben — der Restart-Pfad in
    ``runs.py`` liest ihn von dort über ``_parse_quota_plan(config)``
    wieder ein. Ohne Persistenz war der Plan beim Restart immer ``None``.
    """
    if progress_callback:
        progress_callback(
            "generating_config", 0,
            "Analyzing simulation requirements...",
            current=0,
            total=3,
        )

    config_generator = SimulationConfigGenerator(
        model_name=llm_model,
        language=language,
    )

    if progress_callback:
        progress_callback(
            "generating_config", 30,
            "Calling LLM to generate config...",
            current=1,
            total=3,
        )

    sim_params = config_generator.generate_config(
        simulation_id=simulation_id,
        project_id=state.project_id,
        graph_id=state.graph_id,
        simulation_requirement=simulation_requirement,
        document_text=document_text,
        entities=filtered.entities,
        enable_twitter=state.enable_twitter,
        enable_reddit=state.enable_reddit,
    )

    if progress_callback:
        progress_callback(
            "generating_config", 70,
            "Saving config files...",
            current=2,
            total=3,
        )

    # Save config files (atomic via store — fixes prior non-atomic write).
    config_payload = json.loads(sim_params.to_json())
    if quota_plan is not None:
        config_payload["quota_plan"] = quota_plan.model_dump()
    manager._store.write_json(
        simulation_id,
        "simulation_config",
        config_payload,
    )

    state.config_generated = True
    state.config_reasoning = sim_params.generation_reasoning

    if progress_callback:
        progress_callback(
            "generating_config", 100,
            "Config generation completed",
            current=3,
            total=3,
        )


def _validate_persona_quota(
    plan: PersonaQuotaPlan,
    profiles: List[OasisAgentProfile],
) -> None:
    """Validate actual persona segment counts against ``plan``.

    Raises ``pydantic.ValidationError`` (propagates to caller) when:
    - A required segment is missing or has wrong count (tolerance=0).
    - Profiles contain segments not declared in the plan.
    """
    actual_counts: Dict[str, int] = {}
    for p in profiles:
        seg = getattr(p, "segment", None)
        if seg:
            actual_counts[seg] = actual_counts.get(seg, 0) + 1
    PersonaQuotaActual.model_validate(
        {
            "plan": plan.model_dump(),
            "actual_counts": actual_counts,
            "tolerance": 0,
        }
    )


def prepare_simulation(
    manager: SimulationManager,
    simulation_id: str,
    simulation_requirement: str,
    document_text: str,
    *,
    defined_entity_types: Optional[List[str]] = None,
    use_llm_for_profiles: bool = True,
    progress_callback: Optional[Callable] = None,
    parallel_profile_count: int = 3,
    storage: Any = None,
    llm_model: Optional[str] = None,
    language: Optional[str] = None,
    max_agents: Optional[int] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
) -> SimulationState:
    """Orchestrator für die drei Prepare-Phasen.

    Setzt FSM-Status PREPARING vor Phase 1, READY nach Phase 3, FAILED bei
    jeder Exception. ``state.error`` wird im Fehlerfall mit der Exception-
    Message gesetzt; die Exception wird nach State-Update weiter geworfen.
    """
    from .simulation_manager import SimulationStatus

    state = manager._load_simulation_state(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    try:
        manager._set_status(state, SimulationStatus.PREPARING)

        sim_dir = manager._get_simulation_dir(simulation_id)

        # Phase 1: Read & filter entities
        filtered = _phase_read_entities(
            state,
            storage,
            defined_entity_types,
            max_agents,
            progress_callback=progress_callback,
        )

        if filtered.filtered_count == 0:
            raise ValueError(
                "No entities matching criteria found, "
                "check if graph is correctly constructed"
            )

        # Phase 2: Generate Agent Profiles
        profiles = _phase_generate_profiles(
            state,
            storage,
            filtered,
            sim_dir,
            llm_model=llm_model,
            language=language,
            use_llm_for_profiles=use_llm_for_profiles,
            parallel_profile_count=parallel_profile_count,
            progress_callback=progress_callback,
        )

        # Optional quota check: ValidationError propagates → FAILED state.
        if quota_plan is not None:
            _validate_persona_quota(quota_plan, profiles)

        # Phase 3: LLM-driven config generation
        _phase_generate_config(
            manager,
            state,
            simulation_id,
            simulation_requirement,
            document_text,
            filtered,
            llm_model=llm_model,
            language=language,
            progress_callback=progress_callback,
            quota_plan=quota_plan,
        )

        # Run scripts remain in backend/scripts/ directory, no longer copy to
        # simulation directory. When starting simulation, simulation_runner
        # runs scripts from scripts/ directory.

        manager._set_status(state, SimulationStatus.READY)

        logger.info(
            f"Simulation preparation completed: {simulation_id}, "
            f"entities={state.entities_count}, profiles={state.profiles_count}"
        )

        return state

    except Exception as exc:
        logger.error(
            f"Simulation preparation failed: {simulation_id}, error={exc}"
        )
        logger.error(traceback.format_exc())
        state.error = str(exc)
        manager._set_status(state, SimulationStatus.FAILED)
        raise


__all__ = ["prepare_simulation", "_validate_persona_quota"]
