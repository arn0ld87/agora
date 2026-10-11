"""Fragebezogene Hybrid-Auswahl der Persona-Entitaeten (#1759, A5).

``_cap_entities_across_types`` verteilt beim ``max_agents``-Cap die Plaetze
reihum ueber die Typen — ohne Bezug zur Simulationsfrage. Im Referenzlauf
(``sim_3d3d8b2d8342``) bekam jeder Typ fast exakt zwei Sitze, die in der
Frage genannten Schwangeren waren mit einer einzigen Persona unter 30
vertreten.

Die Hybrid-Auswahl (Maintainer-Entscheidung, #1759):

1. **Harte Mindestsitze** fuer Entitaeten, die die Simulationsfrage nennt
   (Namens- oder Typ-Treffer). Gruppen-Entitaeten bekommen bis zu
   ``_GROUP_SEATS`` Sitze — dieselbe Entitaet wird dann mehrfach in die
   Generierungsliste gestellt, jede Wiederholung wird eine eigene
   Einzelpersona (eigener Slot, siehe ``_expand_entities_for_quota``).
2. **Garantierte Entscheider-Sitze** (Leitung, Vorstand, Landrat, ...), damit
   sie nicht hinter Randakteuren zurueckfallen.
3. **Restplaetze** vergibt ein Auswahl-LLM ueber ``LLMClient.chat_json`` mit
   der Frage im Prompt und einer Pflichtbegruendung je Kandidat
   (``EntityRelevanceResponse``).

Beides zusammen darf hoechstens drei Viertel der Plaetze binden, damit das
LLM immer mitentscheidet. Reicht das Budget nicht, gewinnen zuerst die in der
Frage genannten Entitaeten (staerkster Treffer zuerst), dann Entscheider,
dann die zweiten Sitze der Gruppen.

Dieses Modul kennt weder ``prepare_entities`` noch Degradation-Sammler: der
Aufrufer protokolliert, was ohne Platz bleibt. ``BudgetExceededError``
verlaesst jede Funktion hier unveraendert.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, NamedTuple, Optional

from ..contracts.entity_selection_contract import (
    EntityRelevanceResponse,
    EntitySelectionDecision,
    SelectionBasis,
)
from .degradation_collector import describe_exception
from .persona_domain_coherence import _type_words, is_collective_entity_type
from .persona_identity_binding import synthetic_supplement_copy
from .run_budget import BudgetExceededError

if TYPE_CHECKING:
    from .entity_reader import EntityNode

_logger = logging.getLogger("agora.prepare_requirement_selection")

#: Sitze einer in der Frage genannten Gruppen-Entitaet (Wiederholung derselben
#: Entitaet, je Wiederholung eine eigene Einzelpersona).
_GROUP_SEATS = 2
#: Obergrenze der Kandidaten im Auswahl-Prompt; der Rest bleibt ohne Platz.
_MAX_LLM_CANDIDATES = 120
_MIN_EXTRA_CANDIDATES = 40
_SUMMARY_PROMPT_LIMIT = 160
_MIN_STEM_LENGTH = 5
_MIN_PREFIX_LENGTH = 6

_TOKEN_SPLIT_RE = re.compile(r"[^\wäöüßÄÖÜ]+")
# Laengere Endungen zuerst; es wird hoechstens eine gestrichen.
_INFLECTION_SUFFIXES = ("innen", "ern", "en", "er", "es", "in", "e", "n", "s")

#: Typ-Grundwoerter ohne Aussagekraft fuer "die Frage nennt diese Gruppe".
_GENERIC_TYPE_WORDS = frozenset(
    {
        "entity", "person", "persons", "people", "stakeholder", "organization",
        "organisation", "group", "gruppe", "institution", "company", "unternehmen",
        "actor", "akteur", "member", "mitglied", "official", "representative",
        "vertreter", "individual",
    }
)

#: Wortanfaenge, die Entscheider kennzeichnen (Token-Praefix, casefold).
_DECISION_MARKERS = (
    "entscheid", "decision", "leitung", "geschäftsführ", "geschaeftsführ",
    "geschaeftsfuehr", "vorstand", "direktor", "director", "manager",
    "minister", "landrat", "bürgermeister", "buergermeister", "mayor", "ceo",
    "vorsitz", "chief", "executive", "management", "chefarzt", "chefärzt",
    "präsident", "praesident", "president",
)


class SelectionResult(NamedTuple):
    """Ergebnis der Hybrid-Auswahl."""

    selected: "List[EntityNode]"
    """Generierungsliste; eine Gruppen-Entitaet kann mehrfach vorkommen."""
    omitted: "List[EntityNode]"
    """Eindeutige Entitaeten ohne Platz — Reserve und Degradationsmeldung."""
    decisions: List[EntitySelectionDecision]
    llm_failure: Optional[str]
    """Beschreibung, falls das Relevanz-Ranking ausgefallen ist (sonst ``None``)."""


class _SeatPlan(NamedTuple):
    entity: "EntityNode"
    seats: int
    basis: SelectionBasis
    reason: str


def _stem(token: str) -> str:
    lowered = token.casefold()
    for suffix in _INFLECTION_SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) - len(suffix) >= _MIN_STEM_LENGTH:
            return lowered[: -len(suffix)]
    return lowered


def _stems(text: str) -> set[str]:
    return {
        _stem(token)
        for token in _TOKEN_SPLIT_RE.split(text or "")
        if len(token) >= _MIN_STEM_LENGTH
    }


def _stems_match(left: str, right: str) -> bool:
    if left == right:
        return True
    short, long_ = (left, right) if len(left) <= len(right) else (right, left)
    return len(short) >= _MIN_PREFIX_LENGTH and long_.startswith(short)


def _matched_stems(candidates: set[str], question: set[str]) -> int:
    return sum(
        1 for stem in candidates if any(_stems_match(stem, other) for other in question)
    )


def _entity_type(entity: "EntityNode") -> str:
    return entity.get_entity_type() or "Entity"


def _type_stems(entity: "EntityNode") -> set[str]:
    words = [w for w in _type_words(_entity_type(entity)) if w not in _GENERIC_TYPE_WORDS]
    return {_stem(w) for w in words if len(w) >= _MIN_STEM_LENGTH}


def _name_matches(entity: "EntityNode", question: set[str]) -> int:
    return _matched_stems(_stems(entity.name or ""), question)


def _is_decision_maker(entity: "EntityNode") -> bool:
    tokens = [t.casefold() for t in _TOKEN_SPLIT_RE.split(entity.name or "") if t]
    tokens += _type_words(_entity_type(entity))
    return any(token.startswith(marker) for token in tokens for marker in _DECISION_MARKERS)


def _named_plans(entities: "List[EntityNode]", requirement: str) -> List[_SeatPlan]:
    """Von der Frage genannte Entitaeten, staerkster Treffer zuerst."""
    question = _stems(requirement)
    scored: list[tuple[int, int, _SeatPlan]] = []
    for index, entity in enumerate(entities):
        name_hits = _name_matches(entity, question)
        type_hits = _matched_stems(_type_stems(entity), question)
        if not name_hits and not type_hits:
            continue
        group = bool(type_hits) or is_collective_entity_type(_entity_type(entity))
        via = "Typ" if type_hits else "Name"
        plan = _SeatPlan(
            entity,
            _GROUP_SEATS if group else 1,
            "named_group",
            f"In der Simulationsfrage genannt ({via}-Treffer): {entity.name}",
        )
        scored.append((-(name_hits + type_hits), index, plan))
    return [plan for _, _, plan in sorted(scored, key=lambda item: item[:2])]


def _decision_plans(
    entities: "List[EntityNode]", already: set[str]
) -> List[_SeatPlan]:
    return [
        _SeatPlan(
            entity,
            1,
            "decision_maker",
            f"Entscheider mit garantiertem Sitz: {entity.name}",
        )
        for entity in entities
        if entity.uuid not in already and _is_decision_maker(entity)
    ]


def hard_seat_budget(max_agents: int) -> int:
    """Hoechstens drei Viertel der Plaetze, mindestens ein Platz bleibt dem LLM."""
    return max(1, min(max_agents - 1, (max_agents * 3) // 4))


def plan_hard_seats(
    entities: "List[EntityNode]", requirement: str, max_agents: int
) -> List[_SeatPlan]:
    """Verteilt Mindest- und Entscheidersitze unter ``hard_seat_budget``.

    Vergabe in drei Stufen: je ein Sitz fuer genannte Entitaeten, je ein Sitz
    fuer Entscheider (hoechstens ``max_agents // 4``), danach die zweiten
    Sitze der genannten Gruppen. Was nicht mehr passt, bleibt LLM-Kandidat.
    """
    budget = hard_seat_budget(max_agents)
    named = _named_plans(entities, requirement)
    named_ids = {plan.entity.uuid for plan in named}
    decision = _decision_plans(entities, named_ids)[: max(1, max_agents // 4)]

    seats: Dict[str, int] = {}
    ordered: List[_SeatPlan] = []
    used = 0
    for plan in [*named, *decision]:
        if used >= budget:
            break
        seats[plan.entity.uuid] = 1
        ordered.append(plan)
        used += 1
    for plan in ordered:
        if used >= budget:
            break
        extra = min(plan.seats - 1, budget - used)
        seats[plan.entity.uuid] += extra
        used += extra
    return [plan._replace(seats=seats[plan.entity.uuid]) for plan in ordered]


def _candidate_line(index: int, entity: "EntityNode") -> str:
    summary = " ".join((entity.summary or "").split())[:_SUMMARY_PROMPT_LIMIT]
    return f"{index}. {entity.name} [Typ: {_entity_type(entity)}] {summary}".rstrip()


def _build_messages(requirement: str, candidates: "List[EntityNode]") -> List[Dict[str, str]]:
    lines = "\n".join(_candidate_line(i, e) for i, e in enumerate(candidates, start=1))
    system = (
        "Du waehlst Stakeholder fuer eine Multi-Agent-Simulation aus. Bewerte "
        "jeden Kandidaten danach, wie wichtig seine Stimme fuer die "
        "Simulationsfrage ist. Antworte ausschliesslich mit JSON im "
        "vorgegebenen Schema."
    )
    user = (
        f"Simulationsfrage:\n{requirement}\n\n"
        f"Kandidaten ({len(candidates)}):\n{lines}\n\n"
        "Gib fuer JEDEN Kandidaten eine Bewertung: candidate_index (Nummer "
        "aus der Liste), relevance (0 = irrelevant bis 10 = unverzichtbar) und "
        "reason (ein Satz, warum diese Relevanz fuer die Frage). Die "
        "Begruendung ist Pflicht."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _rate_candidates(
    client: Any, requirement: str, candidates: "List[EntityNode]"
) -> Dict[int, tuple[int, str]]:
    """Fragt das Auswahl-LLM; Rueckgabe: 0-basierter Kandidatenindex -> (Relevanz, Grund)."""
    raw = client.chat_json(
        messages=_build_messages(requirement, candidates),
        temperature=0.2,
        max_tokens=min(8000, 300 + 80 * len(candidates)),
        schema=EntityRelevanceResponse,
        schema_name="entity_relevance",
        context="persona",
        force_no_thinking=True,
    )
    response = EntityRelevanceResponse.model_validate(raw)
    ratings: Dict[int, tuple[int, str]] = {}
    for item in response.items:
        position = item.candidate_index - 1
        if 0 <= position < len(candidates) and position not in ratings:
            ratings[position] = (item.relevance, item.reason)
    return ratings


def _pick_by_relevance(
    candidates: "List[EntityNode]",
    ratings: Dict[int, tuple[int, str]],
    slots: int,
    seeded_types: Dict[str, int],
) -> List[int]:
    """Greedy nach Relevanz; bei Gleichstand der Typ mit weniger Sitzen zuerst."""
    taken = dict(seeded_types)
    remaining = list(range(len(candidates)))
    picked: List[int] = []
    while remaining and len(picked) < slots:
        best = max(
            remaining,
            key=lambda i: (
                ratings.get(i, (0, ""))[0],
                -taken.get(_entity_type(candidates[i]), 0),
                -i,
            ),
        )
        remaining.remove(best)
        picked.append(best)
        type_key = _entity_type(candidates[best])
        taken[type_key] = taken.get(type_key, 0) + 1
    return picked


def _relevance_reason(ratings: Dict[int, tuple[int, str]], index: int) -> str:
    if index in ratings:
        relevance, reason = ratings[index]
        return f"Relevanz {relevance}/10: {reason}"
    return "Vom Auswahl-LLM nicht bewertet; Restplatz nach Typ-Streuung"


def _rank_remaining(
    *,
    client_factory: Callable[[], Any],
    requirement: str,
    candidates: "List[EntityNode]",
    slots: int,
    seeded_types: Dict[str, int],
    fill_fallback: "Callable[[List[EntityNode], int], List[EntityNode]]",
) -> "tuple[List[EntityNode], List[EntitySelectionDecision], Optional[str]]":
    """Vergibt die Restplaetze per LLM-Relevanz; faellt bei Ausfall auf Round-Robin zurueck."""
    if slots <= 0 or not candidates:
        return [], [], None
    # Das Ranking sieht nie weniger Kandidaten, als Plaetze zu vergeben sind.
    pool_limit = max(_MAX_LLM_CANDIDATES, slots + _MIN_EXTRA_CANDIDATES)
    pool = (
        fill_fallback(candidates, pool_limit)
        if len(candidates) > pool_limit
        else list(candidates)
    )
    try:
        ratings = _rate_candidates(client_factory(), requirement, pool)
    except BudgetExceededError:
        raise
    except Exception as exc:  # noqa: BLE001 — sichtbar ueber llm_failure, nie still
        failure = describe_exception(exc)
        _logger.warning("Relevanz-Ranking fehlgeschlagen (#1759 A5): %s", failure)
        picked_entities = fill_fallback(pool, slots)
        decisions = [
            EntitySelectionDecision(
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                basis="fallback_round_robin",
                reason="Restplatz ohne Relevanz-Ranking (Auswahl-LLM ausgefallen)",
            )
            for entity in picked_entities
        ]
        return picked_entities, decisions, failure

    indices = _pick_by_relevance(pool, ratings, slots, seeded_types)
    entities = [pool[i] for i in indices]
    decisions = [
        EntitySelectionDecision(
            entity_uuid=pool[i].uuid,
            entity_name=pool[i].name,
            basis="llm_relevance",
            reason=_relevance_reason(ratings, i),
        )
        for i in indices
    ]
    return entities, decisions, None


def select_entities_with_requirement(
    entities: "List[EntityNode]",
    *,
    max_agents: int,
    requirement: str,
    client_factory: Callable[[], Any],
    fill_fallback: "Callable[[List[EntityNode], int], List[EntityNode]]",
) -> SelectionResult:
    """Hybrid-Auswahl fuer ``len(entities) > max_agents`` (siehe Moduldocstring)."""
    plans = plan_hard_seats(entities, requirement, max_agents)
    hard_ids = {plan.entity.uuid for plan in plans}
    selected: "List[EntityNode]" = []
    decisions: List[EntitySelectionDecision] = []
    seeded_types: Dict[str, int] = {}
    for plan in plans:
        # Der erste Sitz bleibt die quellengebundene Entitaet, jeder weitere
        # ist eine ausdruecklich synthetische Zusatzstimme (#1833).
        selected.append(plan.entity)
        selected.extend(synthetic_supplement_copy(plan.entity) for _ in range(plan.seats - 1))
        seeded_types[_entity_type(plan.entity)] = (
            seeded_types.get(_entity_type(plan.entity), 0) + plan.seats
        )
        decisions.append(
            EntitySelectionDecision(
                entity_uuid=plan.entity.uuid,
                entity_name=plan.entity.name,
                basis=plan.basis,
                reason=plan.reason,
                seats=plan.seats,
            )
        )

    candidates = [e for e in entities if e.uuid not in hard_ids]
    slots = max_agents - len(selected)
    ranked, ranked_decisions, failure = _rank_remaining(
        client_factory=client_factory,
        requirement=requirement,
        candidates=candidates,
        slots=slots,
        seeded_types=seeded_types,
        fill_fallback=fill_fallback,
    )
    selected.extend(ranked)
    decisions.extend(ranked_decisions)

    seated = {e.uuid for e in selected}
    omitted = [e for e in entities if e.uuid not in seated]
    return SelectionResult(selected, omitted, decisions, failure)


def requirement_hash(requirement: Optional[str]) -> Optional[str]:
    """Stabiler Kurz-Hash der Simulationsfrage (Whitespace-normalisiert), ``None`` bei leerer Frage."""
    normalized = " ".join((requirement or "").split())
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "SelectionResult",
    "hard_seat_budget",
    "plan_hard_seats",
    "requirement_hash",
    "select_entities_with_requirement",
]
