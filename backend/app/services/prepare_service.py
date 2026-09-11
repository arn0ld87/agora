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
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

from ..contracts import (
    PersonaQuotaPlan,
    PersonaTargetContract,
)
from ..contracts.llm_routing_contract import ResolvedRoute
from ..utils.logger import get_logger
from .degradation_collector import DegradationCollector
from .entity_reader import EntityReader as EntityReader
from .settings_layer import get_default_service as _get_settings
from .llm_runtime import RuntimeLlmConfig
from .oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator
from .persona_eligibility import filter_eligible_entities as filter_eligible_entities
from .persona_quota_defaults import default_dach_industry_quota
from .report_agent import MIN_PERSONA_TABLE_ROWS
from .simulation_config_generator import SimulationConfigGenerator

if TYPE_CHECKING:
    from .entity_reader import EntityNode
    from .simulation_manager import SimulationManager, SimulationState

from . import prepare_llm as _prepare_llm
from . import prepare_entities as _prepare_entities
from . import prepare_quota as _prepare_quota

logger = get_logger("agora.prepare")


LlmRuntimeInput = RuntimeLlmConfig | ResolvedRoute


def _resolve_llm_connection(llm_runtime: Optional[LlmRuntimeInput], *, require: bool=True) -> tuple[Optional[str], Optional[str], Optional[str]]:
    return _prepare_llm._resolve_llm_connection(llm_runtime, require=require)


# Bestimmte und unbestimmte Artikel, die einer Entitaetsbezeichnung
# voranstehen koennen ("der digitale Zwilling", "die Lernplattform"). Nur das
# erste Token wird geprueft — Artikel mitten im Namen ("KI-Version der
# Lehrkraft") sind Teil der Bezeichnung und werden nicht angetastet.
_LEADING_ARTICLES = frozenset(
    {
        "der", "die", "das", "den", "dem", "des",
        "ein", "eine", "einen", "einem", "einer", "eines",
    }
)

# Schwache/starke Adjektivendungen, absteigend nach Laenge geprueft, damit
# "digitalen" auf "en" statt versehentlich auf ein kuerzeres Suffix trifft.
_ADJECTIVE_SUFFIXES = ("er", "es", "em", "en", "e")

# Mindestlaenge des verbleibenden Stamms nach Endungs-Abzug. Bewusst auf 4
# gesetzt statt z. B. 3: bei 3 wuerde "ohne" (Praeposition, kein Adjektiv) zu
# "ohn" verstuemmelt. Ein zu kurzer Stamm ist ein Indiz, dass das Wort gar
# kein flektiertes Adjektiv ist — dann lieber nicht anfassen.
_MIN_ADJECTIVE_STEM_LENGTH = 4


def _strip_leading_article(tokens: list[str]) -> list[str]:
    return _prepare_entities._strip_leading_article(tokens)


def _normalize_adjective_endings(tokens: list[str]) -> list[str]:
    return _prepare_entities._normalize_adjective_endings(tokens)


def _entity_identity_key(entity: 'EntityNode') -> tuple[str, str]:
    return _prepare_entities._entity_identity_key(entity)


def _dedupe_entities(entities: 'List[EntityNode]') -> 'tuple[List[EntityNode], int]':
    return _prepare_entities._dedupe_entities(entities)


def _cap_entities_across_types(entities: 'List[EntityNode]', max_agents: int) -> 'List[EntityNode]':
    return _prepare_entities._cap_entities_across_types(entities, max_agents)


def _phase_read_entities(state: SimulationState, storage: Any, defined_entity_types: Optional[List[str]], max_agents: Optional[int], progress_callback: Optional[Callable]=None, degradations: Optional[DegradationCollector]=None):
    return _prepare_entities._phase_read_entities(state, storage, defined_entity_types, max_agents, progress_callback, degradations)


def _phase_generate_profiles(
    state: SimulationState,
    storage: Any,
    filtered,
    sim_dir: str,
    *,
    llm_model: Optional[str],
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str],
    run_id: Optional[str] = None,
    use_llm_for_profiles: bool,
    parallel_profile_count: int,
    progress_callback: Optional[Callable] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    persona_floor: int = MIN_PERSONA_TABLE_ROWS,
    max_agents: Optional[int] = None,
    degradations: Optional[DegradationCollector] = None,
) -> Tuple[List[Any], List[Any]]:
    """Phase 2: OASIS-Profiles generieren und im Sim-Dir ablegen.

    Aktualisiert ``state.profiles_count`` als Seiteneffekt und gibt ein
    Tuple ``(profiles, expanded_entities)`` zurück: die Liste der
    generierten Profile sowie die auf die Quota expandierte
    Entity-Liste, die Phase 3 weiterverarbeitet.

    Sub-Slice 20b — Quota-Erzwingung: wenn ``quota_plan`` gesetzt ist,
    wird ``filtered.entities`` vor der Generation per
    ``_expand_entities_for_quota`` auf die Quota expandiert (Round-Robin
    auf zu kleinen Pools). Ohne Plan bleibt das Verhalten "1 Persona pro
    Entity" unverändert.
    """
    entities = _expand_entities_for_quota(filtered.entities, quota_plan)
    if quota_plan is None:
        entities = _apply_persona_floor_to_entities(entities, minimum=persona_floor)
    # Issue #1034: Der Nenner des Fortschrittszählers kommt aus derselben
    # Funktion, die auch die Preview-Antwort füllt. Vorher stand hier
    # ``len(entities)`` — richtig, aber eben nur hier: die UI bekam den
    # Vor-Floor-Wert aus einer zweiten Berechnung und zeigte „22 / 7“.
    total_entities = compute_persona_target(
        len(filtered.entities),
        max_agents=max_agents,
        quota_plan=quota_plan,
        floor=persona_floor,
    ).persona_target_count

    if progress_callback:
        progress_callback(
            "generating_profiles", 0,
            "Starting generation...",
            current=0,
            total=total_entities,
        )

    # Pass graph_id to enable graph retrieval functionality, get richer context.
    # Per-simulation overrides for model + language come from API request.
    # Issue #215: Branchenverteilung-Plan für LLM-Prompt — Default Destatis WZ 2008
    # (IT-Cap ≤ 12 %). total_entities als Pool-Größe für proportionale Verteilung.
    industry_plan = default_dach_industry_quota(max(total_entities, 1))

    # ``require`` folgt dem expliziten Nutzerwunsch: nur wenn LLM-Personas
    # verlangt sind, ist eine fehlende Route ein Fehler. Bei
    # ``use_llm_for_profiles=False`` ist regelbasiert das gewollte Ergebnis.
    api_key, base_url, provider_type = _resolve_llm_connection(
        llm_runtime, require=use_llm_for_profiles
    )

    generator = OasisProfileGenerator(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
        storage=storage,
        graph_id=state.graph_id,
        model_name=llm_model,
        language=language,
        industry_quota_plan=industry_plan,
        # Budget-Enforcement (#984): run-gebundene LLM-Calls statt budgetfrei.
        run_id=run_id,
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
        entities=entities,
        use_llm=use_llm_for_profiles,
        progress_callback=profile_progress,
        graph_id=state.graph_id,
        parallel_count=parallel_profile_count,
        realtime_output_path=realtime_output_path,
        output_platform=realtime_platform,
        # Issue #1034: Der Parameter existiert seit #1029 (Slice 12,
        # regelbasierte Fallback-Profile), wurde aus dem produktiven
        # Prepare-Pfad aber nie gefüllt — ``_report_persona_degradation``
        # lief damit nie. Ohne diese Zeile bleibt die Meldung dort tot.
        degradations=degradations,
        # Issue #1247: Nachrücker für Kandidaten, die der Generator als nicht
        # personenfähig zurückweist.
        reserve_entities=getattr(filtered, "reserve_entities", None),
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

    return profiles, entities


def _phase_generate_config(
    manager: SimulationManager,
    state: SimulationState,
    simulation_id: str,
    simulation_requirement: str,
    document_text: str,
    *,
    expanded_entities: List[Any],
    llm_model: Optional[str],
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str],
    run_id: Optional[str] = None,
    use_llm: bool = True,
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

    api_key, base_url, provider_type = _resolve_llm_connection(llm_runtime, require=use_llm)

    config_generator = SimulationConfigGenerator(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
        model_name=llm_model,
        language=language,
        # Budget-Enforcement (#984): run-gebundene LLM-Calls statt budgetfrei.
        run_id=run_id,
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
        entities=expanded_entities,
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


def _expand_entities_for_quota(entities: List[Any], plan: Optional[PersonaQuotaPlan]) -> List[Any]:
    return _prepare_quota._expand_entities_for_quota(entities, plan)


def _apply_persona_floor_to_entities(entities: List[Any], *, minimum: int=MIN_PERSONA_TABLE_ROWS) -> List[Any]:
    return _prepare_quota._apply_persona_floor_to_entities(entities, minimum=minimum)


def _apply_persona_floor_to_quota_plan(plan: Optional[PersonaQuotaPlan], *, minimum: int=MIN_PERSONA_TABLE_ROWS) -> Optional[PersonaQuotaPlan]:
    return _prepare_quota._apply_persona_floor_to_quota_plan(plan, minimum=minimum)


def compute_persona_target(entity_count: int, *, max_agents: Optional[int]=None, quota_plan: Optional[PersonaQuotaPlan]=None, floor: Optional[int]=None) -> PersonaTargetContract:
    return _prepare_quota.compute_persona_target(entity_count, max_agents=max_agents, quota_plan=quota_plan, floor=floor)


def _validate_persona_quota(plan: PersonaQuotaPlan, profiles: List[OasisAgentProfile]) -> None:
    return _prepare_quota._validate_persona_quota(plan, profiles)


class PrepareCancelledError(Exception):
    """Signalisiert kooperativen Abbruch während ``prepare_simulation()``.

    Issue B2 (PLAN.md „Abbrechen & Pause“): das Cancel-Flag wird an den
    Phasengrenzen geprüft (analog ``report_agent/workflow.py::_is_cancel_requested``
    an den Stage-Boundaries). Anders als ``BudgetExceededError`` ist ein
    Nutzerabbruch kein Fehler — deshalb eine eigene Exception statt eines
    ``ValueError``, damit der generische ``except Exception``-Zweig unten
    (FSM → FAILED) sie nicht mit einem echten Fehlschlag verwechselt.

    Trägt den zuletzt gespeicherten ``SimulationState``, damit der Aufrufer
    (``api/simulation_prepare.py::_make_prepare_job``) den Abbruch-Endzustand
    bauen kann, ohne die Simulation erneut zu laden.
    """

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
) -> SimulationState:
    """Orchestrator für die drei Prepare-Phasen.

    Setzt FSM-Status PREPARING vor Phase 1, READY nach Phase 3, FAILED bei
    jeder Exception. ``state.error`` wird im Fehlerfall mit der Exception-
    Message gesetzt; die Exception wird nach State-Update weiter geworfen.

    Zwischen den drei Phasen wird das Cancel-Flag geprüft (``run_id``,
    ``services/sim/cancel_flag.py``) — kooperativer Abbruch analog
    ``report_agent/workflow.py``. Bereits geschriebene Artefakte (Profildatei
    aus Phase 2, Entity-Zählung aus Phase 1) bleiben unangetastet stehen;
    nur der FSM-Status wechselt auf ``CANCELLED_PARTIAL`` statt ``READY``.
    """
    from .simulation_manager import SimulationStatus
    from .sim.cancel_flag import is_cancel_requested

    state = manager._load_simulation_state(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    def _raise_if_cancelled() -> None:
        if run_id and is_cancel_requested(run_id):
            manager._set_status(state, SimulationStatus.CANCELLED_PARTIAL)
            raise PrepareCancelledError(state)

    try:
        manager._set_status(state, SimulationStatus.PREPARING)

        sim_dir = manager._get_simulation_dir(simulation_id)

        _raise_if_cancelled()

        # Phase 1: Read & filter entities
        filtered = _phase_read_entities(
            state,
            storage,
            defined_entity_types,
            max_agents,
            progress_callback=progress_callback,
            degradations=degradations,
        )

        if filtered.filtered_count == 0:
            raise ValueError(
                "No entities matching criteria found, "
                "check if graph is correctly constructed"
            )

        # Resolve parallel_profile_count: None → env AGORA_PARALLEL_PERSONA_COUNT → 10.
        # Auflösung hier (einmalig), damit _phase_generate_profiles ein konkretes int erhält.
        if parallel_profile_count is None:
            parallel_profile_count = int(
                _get_settings().effective_value('AGORA_PARALLEL_PERSONA_COUNT')
            )

        # Effektiver Persona-Floor (Task: 50-Personas-Minimum dynamisch):
        # Der Report-Contract verlangt MIN_PERSONA_TABLE_ROWS, aber ein
        # explizit kleineres max_agents gewinnt (Nutzer-Wunsch schlägt
        # Contract). Der Wert wird im State persistiert, damit das
        # Report-Gate in workflow.py denselben Floor prüft.
        persona_floor = MIN_PERSONA_TABLE_ROWS
        if max_agents is not None and max_agents > 0:
            persona_floor = min(persona_floor, max_agents)
        state.persona_floor = persona_floor
        manager._save_simulation_state(state)

        quota_plan = _apply_persona_floor_to_quota_plan(
            quota_plan, minimum=persona_floor
        )

        _raise_if_cancelled()

        # Phase 2: Generate Agent Profiles
        profiles, expanded_entities = _phase_generate_profiles(
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
        )

        # Review-Finding (PR #1371, Befund 2): der Cancel-Check MUSS vor der
        # Quota-Validierung laufen. Bricht die Persona-Generierung
        # kooperativ mitten in der as_completed-Schleife ab
        # (oasis_profile_generator.py), liefert sie eine gekürzte
        # Profilliste zurück — bei gesetztem quota_plan (tolerance=0)
        # scheitert ``_validate_persona_quota`` daran zwangsläufig mit
        # ``ValidationError``. Lief die Prüfung zuerst, landete genau der
        # Fall, für den dieses Feature existiert, im generischen
        # except-Zweig unten und endete als FAILED statt als der
        # kooperative Abbruch, den der Nutzer angefordert hat.
        _raise_if_cancelled()

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
            expanded_entities=expanded_entities,
            llm_model=llm_model,
            llm_runtime=llm_runtime,
            language=language,
            use_llm=use_llm_for_profiles,
            progress_callback=progress_callback,
            quota_plan=quota_plan,
            run_id=run_id,
        )

        # Run scripts remain in backend/scripts/ directory, no longer copy to
        # simulation directory. When starting simulation, simulation_runner
        # runs scripts from scripts/ directory.

        # Issue #1419: ``BLOCKING`` heisst laut
        # ``pipeline_degradation_contract`` woertlich, dass der Schritt den
        # Zustand "bereit" nicht erreichen darf, auch wenn technisch kein
        # Fehler aufgetreten ist. Ohne dieses Gate war das eine
        # Absichtserklaerung: eine Vorbereitung, in der keine einzige Persona
        # vom Modell kam, ging als READY hinaus und war regulaer startbar.
        # Der Collector bleibt im Task-Ergebnis erhalten — dort steht die
        # Begruendung, die die Oberflaeche anzeigt.
        blocking = (
            [event for event in degradations.report().events if event.is_blocking]
            if degradations is not None
            else []
        )
        if blocking:
            state.error = " ".join(event.detail for event in blocking)
            manager._set_status(state, SimulationStatus.FAILED)
            logger.error(
                "Simulation preparation blocked by degradation: %s, kinds=%s",
                simulation_id,
                ", ".join(event.kind.value for event in blocking),
            )
            return state

        manager._set_status(state, SimulationStatus.READY)

        logger.info(
            f"Simulation preparation completed: {simulation_id}, "
            f"entities={state.entities_count}, profiles={state.profiles_count}"
        )

        return state

    except PrepareCancelledError:
        # FSM steht bereits auf CANCELLED_PARTIAL (in _raise_if_cancelled
        # gesetzt) — kein Fehlschlag, also nicht in den FAILED-Zweig unten.
        logger.info(
            "Simulation preparation cancelled by user: %s (run_id=%s)",
            simulation_id,
            run_id,
        )
        raise
    except Exception as exc:
        logger.error(
            f"Simulation preparation failed: {simulation_id}, error={exc}"
        )
        logger.error(traceback.format_exc())
        state.error = str(exc)
        manager._set_status(state, SimulationStatus.FAILED)
        raise


__all__ = [
    "prepare_simulation",
    "PrepareCancelledError",
    "compute_persona_target",
    "_apply_persona_floor_to_entities",
    "_apply_persona_floor_to_quota_plan",
    "_validate_persona_quota",
]
