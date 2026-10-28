"""Requirement-based entity selection and capping helpers for simulation preparation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from ..contracts.entity_selection_contract import EntitySelectionDecision
from ..contracts.pipeline_degradation_contract import DegradationKind, DegradationSeverity
from .degradation_collector import DegradationCollector
from .prepare_requirement_selection import select_entities_with_requirement

if TYPE_CHECKING:
    from .entity_reader import EntityNode, FilteredEntities

# Issue #1759 (A5): so viele ausgelassene Akteure nennt die Degradation namentlich.
_OMITTED_NAME_LIMIT = 8


def _replace_filtered_entities_if_reduced(
    filtered: FilteredEntities, new_entities: List[EntityNode]
) -> bool:
    """Uebernimmt ``new_entities`` in ``filtered``, falls sie die Liste verkleinert."""
    if len(new_entities) >= len(filtered.entities):
        return False
    filtered.entities = new_entities
    filtered.filtered_count = len(new_entities)
    filtered.entity_types = {
        entity.get_entity_type() or "Entity" for entity in new_entities
    }
    return True


def _build_selection_client(
    llm_runtime: Any, llm_model: Optional[str], run_id: Optional[str]
) -> Any:
    """Baut den ``LLMClient`` fuer das Auswahl-LLM (gleiche Route wie die Personas)."""
    from ..llm.client import LLMClient
    from . import prepare_service as _legacy

    api_key, base_url, provider_type = _legacy._resolve_llm_connection(
        llm_runtime, require=True
    )
    return LLMClient(
        api_key=api_key,
        base_url=base_url,
        model=llm_model,
        run_id=run_id,
        provider_type=provider_type,
    )


def _omitted_names(omitted: List[EntityNode]) -> str:
    names = [entity.name for entity in omitted[:_OMITTED_NAME_LIMIT]]
    rest = len(omitted) - len(names)
    return ", ".join(names) + (f" (+{rest} weitere)" if rest > 0 else "")


def _record_omitted_actors(
    degradations: Optional[DegradationCollector],
    omitted: List[EntityNode],
    *,
    max_agents: int,
    mode: str,
    prefix: str,
) -> None:
    """Meldet Dokument-Akteure ohne Persona-Platz sichtbar (#1759 A5)."""
    if degradations is None or not omitted:
        return
    degradations.record(
        DegradationKind.ENTITY_SELECTION_ACTORS_OMITTED,
        DegradationSeverity.WARNING,
        f"{prefix}{len(omitted)} im Dokument belegte Akteure erhalten bei "
        f"max_agents={max_agents} keinen Persona-Platz: {_omitted_names(omitted)}.",
        context={
            "omitted_count": len(omitted),
            "seat_count": max_agents,
            "selection_mode": mode,
        },
    )


def _fallback_blocker(
    *,
    llm_runtime: Any,
    use_llm_for_profiles: bool,
    has_quota_plan: bool,
) -> Optional[str]:
    """Grund, warum die Hybrid-Auswahl aus ist (``None`` = aktiv)."""
    if has_quota_plan:
        return "quota_plan gesetzt, Quote bestimmt die Plaetze"
    if not use_llm_for_profiles:
        return "use_llm_for_profiles=False"
    if llm_runtime is None:
        return "keine LLM-Route aufgeloest"
    return None


def _select_entities_for_requirement(
    entities: List[EntityNode],
    max_agents: int,
    *,
    simulation_requirement: Optional[str] = None,
    llm_runtime: Any = None,
    llm_model: Optional[str] = None,
    run_id: Optional[str] = None,
    use_llm_for_profiles: bool = True,
    has_quota_plan: bool = False,
    degradations: Optional[DegradationCollector] = None,
) -> tuple[List[EntityNode], List[EntityNode], List[EntitySelectionDecision]]:
    """Cap mit Bezug zur Simulationsfrage (Issue #1759, A5)."""
    from . import prepare_entities as _pe

    requirement = (simulation_requirement or "").strip()
    blocker = (
        _pe._fallback_blocker(
            llm_runtime=llm_runtime,
            use_llm_for_profiles=use_llm_for_profiles,
            has_quota_plan=has_quota_plan,
        )
        if requirement
        else "keine Simulationsfrage"
    )
    if blocker is None:
        result = select_entities_with_requirement(
            entities,
            max_agents=max_agents,
            requirement=requirement,
            client_factory=lambda: _pe._build_selection_client(llm_runtime, llm_model, run_id),
            fill_fallback=_pe._cap_entities_across_types,
        )
        prefix = (
            f"Relevanz-Ranking ausgefallen ({result.llm_failure}), Restplaetze "
            "nach Round-Robin. "
            if result.llm_failure
            else ""
        )
        _pe._record_omitted_actors(
            degradations,
            result.omitted,
            max_agents=max_agents,
            mode="requirement_hybrid",
            prefix=prefix,
        )
        return result.selected, result.omitted, result.decisions

    capped = _pe._cap_entities_across_types(entities, max_agents)
    selected_uuids = {entity.uuid for entity in capped}
    reserve = [entity for entity in entities if entity.uuid not in selected_uuids]
    if requirement:
        _pe._record_omitted_actors(
            degradations,
            reserve,
            max_agents=max_agents,
            mode="round_robin_fallback",
            prefix=f"Auswahl ohne Bezug zur Simulationsfrage ({blocker}): ",
        )
    return capped, reserve, []


def _apply_entity_cap(
    filtered: FilteredEntities,
    max_agents: int,
    *,
    simulation_requirement: Optional[str],
    llm_runtime: Any,
    llm_model: Optional[str],
    run_id: Optional[str],
    use_llm_for_profiles: bool,
    has_quota_plan: bool,
    degradations: Optional[DegradationCollector],
) -> None:
    """Kappt ``filtered`` auf ``max_agents`` und fuellt Reserve und Auswahlbegruendungen."""
    from . import prepare_entities as _pe
    from . import prepare_service as _legacy

    _legacy.logger.info(
        f"Capping agent count at {max_agents} "
        f"(originally {len(filtered.entities)} entities)"
    )
    selected, reserve, decisions = _pe._select_entities_for_requirement(
        filtered.entities,
        max_agents,
        simulation_requirement=simulation_requirement,
        llm_runtime=llm_runtime,
        llm_model=llm_model,
        run_id=run_id,
        use_llm_for_profiles=use_llm_for_profiles,
        has_quota_plan=has_quota_plan,
        degradations=degradations,
    )
    filtered.reserve_entities = reserve
    filtered.selection_decisions = decisions
    filtered.entities = selected
    filtered.filtered_count = len(selected)
    filtered.entity_types = {entity.get_entity_type() or "Entity" for entity in selected}
