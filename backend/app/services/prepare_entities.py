"""Entity selection and graph-read phase for simulation preparation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, List, Optional

from ..contracts.entity_selection_contract import EntitySelectionDecision  # noqa: F401
from ..contracts.pipeline_degradation_contract import (
    DegradationKind,  # noqa: F401
    DegradationSeverity,  # noqa: F401
)
from . import prepare_service as _legacy
from .degradation_collector import DegradationCollector
from .entity_alias_resolution import resolve_aliases
from .persona_eligibility import load_project_ontology
from .prepare_entities_merge import (
    _ORGAN_RELATION_TYPES,
    _ORGAN_WORDS,
    _REPRESENTATION_RELATION_TYPES,
    _VARIANT_FUNCTION_WORDS,
    _VARIANT_LEGAL_FORMS,
    _absorb_variants,
    _apply_collective_affiliation,
    _apply_single_representative_merge,
    _build_eligible_uuid_pool,
    _find_representatives,
    _genitive_stem,
    _is_organization_entity,
    _is_representation_edge,
    _lookup_entities_by_uuid,
    _lookup_expanded_entities_from_checkpoint,
    _merge_entity_variants,
    _merge_persons_with_organizations,
    _organ_base_index,
    _organ_split,
    _organ_target_index,
    _phase_read_entities_from_checkpoint,
    _pick_variant_survivor,
    _remap_edge_targets,
    _representation_target,
    _union_entity_variants,
    _union_name_variants,
    _variant_tokens,
)
from .prepare_entities_normalize import (
    _cap_entities_across_types,
    _dedupe_entities,
    _entity_identity_key,
    _normalize_adjective_endings,
    _strip_leading_article,
)
from .prepare_entities_selection import (
    _OMITTED_NAME_LIMIT,
    _apply_entity_cap,
    _build_selection_client,
    _fallback_blocker,
    _omitted_names,
    _record_omitted_actors,
    _replace_filtered_entities_if_reduced,
    _select_entities_for_requirement,
)
from .prepare_requirement_selection import select_entities_with_requirement  # noqa: F401

if TYPE_CHECKING:
    from .simulation_manager import SimulationState

_logger = logging.getLogger("agora.prepare_entities")


def _phase_read_entities(
    state: SimulationState,
    storage: Any,
    defined_entity_types: Optional[List[str]],
    max_agents: Optional[int],
    progress_callback: Optional[Callable] = None,
    degradations: Optional[DegradationCollector] = None,
    *,
    simulation_requirement: Optional[str] = None,
    llm_runtime: Any = None,
    llm_model: Optional[str] = None,
    run_id: Optional[str] = None,
    use_llm_for_profiles: bool = True,
    has_quota_plan: bool = False,
):
    """Phase 1: Entities aus dem Graphen lesen + filtern + cappen.

    Aktualisiert ``state.entities_count`` und ``state.entity_types`` als
    Seiteneffekt; gibt das ``FilteredEntities``-Objekt zurück.

    Issue #1759 (A5): Die Keyword-Argumente ab ``simulation_requirement``
    steuern die fragebezogene Hybrid-Auswahl beim ``max_agents``-Cap
    (``_select_entities_for_requirement``); ohne Frage bleibt es beim
    bisherigen Round-Robin-Cap.
    """
    if progress_callback:
        progress_callback("reading", 0, "Connecting to graph...")

    if not storage:
        raise ValueError("storage (GraphStorage) is required for prepare_simulation")
    reader = _legacy.EntityReader(storage)

    if progress_callback:
        progress_callback("reading", 30, "Reading node data...")

    filtered = reader.filter_defined_entities(
        graph_id=state.graph_id,
        defined_entity_types=defined_entity_types,
        enrich_with_edges=True,
    )

    # Issue #1034: entity_type-Filter (label-technisch) findet auch
    # Entitäten ohne menschlichen Träger — "USA" (Country), "Agora"
    # (Product) usw. Der Eignungsfilter schließt sie vor dem
    # max_agents-Cap aus, damit sie weder zählen noch generiert werden.
    # Issue #1759 (B2/B3): die Typ-Definition der Ontologie steuert die Eignung.
    eligibility = _legacy.filter_eligible_entities(
        filtered.entities,
        degradations=degradations,
        ontology=load_project_ontology(getattr(state, "project_id", None)),
    )
    _replace_filtered_entities_if_reduced(filtered, eligibility.eligible)

    # Issue #1470 (Slice 4.2): Alias-Auflösung vor Dedupe/Cap.
    entities_before_alias = len(filtered.entities)
    alias_resolved = resolve_aliases(filtered.entities)
    if _replace_filtered_entities_if_reduced(filtered, alias_resolved):
        _legacy.logger.info(
            "Alias-Aufloesung: %d → %d Entitaeten nach Cluster-Bildung",
            entities_before_alias,
            len(alias_resolved),
        )

    # Issue #1713/#1470: Person und die von ihr vertretene Organisation zu
    # einem Agenten zusammenlegen, bevor dedupliziert/gecappt wird.
    # Issue #1759 (A4): Vorher Namensvarianten derselben Organisation
    # zusammenfuehren und Kanten auf den Survivor umzeigen.
    variant_merged = _merge_entity_variants(filtered.entities)
    _replace_filtered_entities_if_reduced(filtered, variant_merged)
    merged_entities = _merge_persons_with_organizations(
        filtered.entities, degradations=degradations
    )
    _replace_filtered_entities_if_reduced(filtered, merged_entities)

    # Issue #1177: Vor dem Cap deduplizieren.
    deduped, duplicate_count = _dedupe_entities(filtered.entities)
    if duplicate_count:
        _legacy.logger.info(
            "Persona-Kandidaten: %d Dublette(n) vor dem Cap entfernt (%d → %d Entitaeten)",
            duplicate_count,
            len(filtered.entities),
            len(deduped),
        )
        filtered.entities = deduped
        filtered.filtered_count = len(deduped)

    # User-controlled cap on number of agents (optional).
    if (
        max_agents is not None
        and max_agents > 0
        and len(filtered.entities) > max_agents
    ):
        _apply_entity_cap(
            filtered,
            max_agents,
            simulation_requirement=simulation_requirement,
            llm_runtime=llm_runtime,
            llm_model=llm_model,
            run_id=run_id,
            use_llm_for_profiles=use_llm_for_profiles,
            has_quota_plan=has_quota_plan,
            degradations=degradations,
        )

    state.entities_count = filtered.filtered_count
    state.entity_types = list(filtered.entity_types)

    if progress_callback:
        progress_callback(
            "reading",
            100,
            f"Completed, total {filtered.filtered_count} entities",
            current=filtered.filtered_count,
            total=filtered.filtered_count,
        )

    return filtered


__all__ = [
    "_OMITTED_NAME_LIMIT",
    "_ORGAN_RELATION_TYPES",
    "_ORGAN_WORDS",
    "_REPRESENTATION_RELATION_TYPES",
    "_VARIANT_FUNCTION_WORDS",
    "_VARIANT_LEGAL_FORMS",
    "_absorb_variants",
    "_apply_collective_affiliation",
    "_apply_entity_cap",
    "_apply_single_representative_merge",
    "_build_eligible_uuid_pool",
    "_build_selection_client",
    "_cap_entities_across_types",
    "_dedupe_entities",
    "_entity_identity_key",
    "_fallback_blocker",
    "_find_representatives",
    "_genitive_stem",
    "_is_organization_entity",
    "_is_representation_edge",
    "_lookup_entities_by_uuid",
    "_lookup_expanded_entities_from_checkpoint",
    "_merge_entity_variants",
    "_merge_persons_with_organizations",
    "_normalize_adjective_endings",
    "_omitted_names",
    "_organ_base_index",
    "_organ_split",
    "_organ_target_index",
    "_phase_read_entities",
    "_phase_read_entities_from_checkpoint",
    "_pick_variant_survivor",
    "_record_omitted_actors",
    "_remap_edge_targets",
    "_replace_filtered_entities_if_reduced",
    "_representation_target",
    "_select_entities_for_requirement",
    "_strip_leading_article",
    "_union_entity_variants",
    "_union_name_variants",
    "_variant_tokens",
]
