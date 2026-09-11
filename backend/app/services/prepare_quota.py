"""Persona quota, floor and target calculations for simulation preparation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..contracts import PersonaQuotaActual, PersonaQuotaPlan, PersonaTargetContract
from ..utils.logger import get_logger
from .oasis_profile_generator import OasisAgentProfile
from .report_agent import MIN_PERSONA_TABLE_ROWS

logger = get_logger("agora.prepare")

def _expand_entities_for_quota(
    entities: List[Any],
    plan: Optional[PersonaQuotaPlan],
) -> List[Any]:
    """Sub-Slice 20b — Generator-Erzwingung.

    Mappt einen Entity-Pool auf den Soll-Plan: pro ``plan.targets[seg]``
    werden so viele Entities zurückgegeben, wie die Quote vorgibt.
    Round-Robin durch den Segment-Pool, wenn der Pool kleiner ist als
    die Quote — keine Synth-Entities (würde semantische KG-Verankerung
    aufgeben). Wenn ein Plan-Segment im Pool nicht existiert, wird ein
    klarer ``ValueError`` geworfen, statt heimlich zu reduzieren.

    Backwards-Compat: ``plan=None`` → Pool wird durchgereicht.

    Hinweis zur Persona-Identität: Bei Replikation derselben Entity
    bekommt jede Persona einen eigenen ``user_id`` (durch Position in
    der Generator-Loop) und nutzt die bestehende Display-Name-/User-Name-
    Dedup-Logik im Generator (s. ``oasis_profile_generator.py`` Z. 1269+),
    die LLM-Name-Kollisionen abfängt.
    """
    if plan is None:
        return entities

    by_segment: Dict[str, List[Any]] = {}
    for e in entities:
        seg = e.get_entity_type() or "Entity"
        by_segment.setdefault(seg, []).append(e)

    expanded: List[Any] = []
    for segment, target in plan.targets.items():
        pool = by_segment.get(segment, [])
        if not pool:
            available = sorted(by_segment.keys())
            raise ValueError(
                f"PersonaQuotaPlan verlangt {target} Personas im Segment "
                f"'{segment}', aber der Entity-Pool enthält keine Entity "
                f"mit entity_type='{segment}'. Verfügbare Segmente: "
                f"{available or '(leer)'}. Entweder Plan anpassen oder "
                f"Ontologie um den fehlenden Type erweitern."
            )
        for i in range(target):
            expanded.append(pool[i % len(pool)])

    return expanded


def _apply_persona_floor_to_entities(
    entities: List[Any],
    *,
    minimum: int = MIN_PERSONA_TABLE_ROWS,
) -> List[Any]:
    """Ensure the generation pool can yield the report persona-table floor.

    The generator creates a distinct profile per input position. When the graph
    has fewer entities than the output contract requires, repeat the existing
    entity pool in deterministic round-robin order instead of inventing
    synthetic entities.
    """
    if not entities or len(entities) >= minimum:
        return entities

    logger.info(
        "persona-floor angewendet: generation_pool=%s floor=%s",
        len(entities),
        minimum,
    )
    return [entities[i % len(entities)] for i in range(minimum)]


def _apply_persona_floor_to_quota_plan(
    plan: Optional[PersonaQuotaPlan],
    *,
    minimum: int = MIN_PERSONA_TABLE_ROWS,
) -> Optional[PersonaQuotaPlan]:
    """Raise an explicit quota plan to the report persona floor.

    Segment proportions are preserved via largest-remainder allocation. The
    adjusted plan is used consistently for generation, validation and persisted
    config, so downstream quota checks stay exact.
    """
    if plan is None or plan.total >= minimum:
        return plan

    raw_targets = {
        segment: (target / plan.total) * minimum
        for segment, target in plan.targets.items()
    }
    targets = {
        segment: max(1, int(raw_value))
        for segment, raw_value in raw_targets.items()
    }
    remaining = minimum - sum(targets.values())
    if remaining > 0:
        ranked_segments = sorted(
            raw_targets,
            key=lambda segment: (
                raw_targets[segment] - int(raw_targets[segment]),
                plan.targets[segment],
                segment,
            ),
            reverse=True,
        )
        for segment in ranked_segments[:remaining]:
            targets[segment] += 1

    logger.info(
        "persona-floor angewendet: quota_total=%s floor=%s targets=%s",
        plan.total,
        minimum,
        targets,
    )
    return PersonaQuotaPlan(targets=targets, total=minimum)


def compute_persona_target(
    entity_count: int,
    *,
    max_agents: Optional[int] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    floor: Optional[int] = None,
) -> PersonaTargetContract:
    """Bestimmt das Persona-Generierungsziel — eine Quelle für beide Pfade.

    ``entity_count`` ist die Entitätenzahl nach Eignungsfilter und
    ``max_agents``-Cap. Der wirksame Floor ist ``MIN_PERSONA_TABLE_ROWS``,
    gedeckelt durch ein gesetztes ``max_agents > 0`` (Nutzer-Wunsch schlägt
    Contract). Wer den Floor bereits aufgelöst hat — der Orchestrator tut
    das für die Generierung —, reicht ihn als ``floor`` herein, statt ihn
    hier ein zweites Mal berechnen zu lassen.

    Mit ``quota_plan`` ist das Ziel dessen ``total`` nach
    ``_apply_persona_floor_to_quota_plan``; ohne Plan ist es
    ``max(entity_count, floor)`` — dasselbe, was
    ``_apply_persona_floor_to_entities`` auf den Entity-Pool anwendet.

    Ein leerer Pool bleibt leer: ``_apply_persona_floor_to_entities``
    skaliert nichts hoch, wenn es nichts zu wiederholen gibt. Ein Ziel von
    50 bei null Entitäten wäre genau die Divergenz zwischen Zähler und
    Nenner, die dieser Contract beseitigen soll.

    ``api/simulation_prepare.py`` (Preview) und ``_phase_generate_profiles``
    (Laufpfad) rufen exakt diese Funktion.
    """
    effective_floor = MIN_PERSONA_TABLE_ROWS if floor is None else floor
    if floor is None and max_agents is not None and max_agents > 0:
        effective_floor = min(effective_floor, max_agents)

    if entity_count == 0:
        # Vor dem Quota-Zweig, nicht dahinter: auch mit Plan gibt es nichts
        # zu wiederholen. `_expand_entities_for_quota` wirft hier ohnehin,
        # und der Orchestrator bricht bei `filtered_count == 0` ab — ein
        # Nenner von 50 wäre eine Zahl, die nie erreicht werden kann.
        target = 0
        floor_applied = False
    elif quota_plan is not None:
        adjusted_plan = _apply_persona_floor_to_quota_plan(
            quota_plan, minimum=effective_floor
        )
        target = adjusted_plan.total if adjusted_plan is not None else quota_plan.total
        # Mit Plan sagt ein Vergleich gegen `entity_count` nichts über den
        # Floor aus: 80 Entitäten mit einer Quota von 6 werden angehoben,
        # lägen aber unter der Entitätenzahl. Maßgeblich ist allein, ob der
        # Plan unter dem Floor lag.
        floor_applied = quota_plan.total < effective_floor
    else:
        target = max(entity_count, effective_floor)
        floor_applied = entity_count < effective_floor

    return PersonaTargetContract(
        entity_count=entity_count,
        persona_target_count=target,
        floor_applied=floor_applied,
        floor=effective_floor,
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
