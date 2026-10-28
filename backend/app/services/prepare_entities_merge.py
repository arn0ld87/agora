"""Entity variant merging, person-organization representation merging,
and checkpoint entity lookup helpers for simulation preparation.

Extracted from ``prepare_entities`` to keep module sizes below the 700 LOC gate.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..contracts.pipeline_degradation_contract import DegradationKind, DegradationSeverity
from . import prepare_service as _legacy
from .degradation_collector import DegradationCollector
from .entity_alias_resolution import _attach_aliases, _UnionFind
from .entity_reader import FilteredEntities
from .persona_domain_coherence import is_collective_entity_type

if TYPE_CHECKING:
    from .entity_reader import EntityNode, EntityReader
    from .prepare_checkpoint import PreparePersonaCheckpoint
    from .simulation_manager import SimulationState


_REPRESENTATION_RELATION_TYPES = frozenset({"REPRESENTS", "LEADS"})
_logger = logging.getLogger("agora.prepare_entities")
_VARIANT_FUNCTION_WORDS = frozenset(
    {"der", "die", "das", "des", "dem", "den", "von", "vom", "fuer", "für",
     "im", "in", "am", "und", "zu", "zur", "zum"}
)
_VARIANT_LEGAL_FORMS = frozenset(
    {"gmbh", "ggmbh", "mbh", "ag", "kg", "ug", "gbr", "ohg", "se", "ev", "e.v"}
)
_ORGAN_WORDS = frozenset(
    {"geschäftsführung", "geschäftsleitung", "vorstand", "leitung",
     "direktion", "präsidium"}
)
_ORGAN_RELATION_TYPES = frozenset(
    {"PART_OF", "ORGAN_OF", "BELONGS_TO", "LEADS", "MANAGES"}
)


def _is_organization_entity(entity: "EntityNode") -> bool:
    """Grundwort-Klassifikation (#1246) — dieselbe wie beim Kollektiv-Persona-Pfad."""
    return is_collective_entity_type(entity.get_entity_type() or "Entity")


def _is_representation_edge(edge: Dict[str, Any]) -> bool:
    """Zeigt diese ausgehende Kante auf eine belegte 'vertritt'-Relation?"""
    if edge.get("direction") != "outgoing":
        return False
    edge_name = str(edge.get("edge_name") or "").strip().upper()
    return edge_name in _REPRESENTATION_RELATION_TYPES


def _representation_target(
    person: "EntityNode", edge: Dict[str, Any], by_uuid: Dict[str, "EntityNode"]
) -> Optional["EntityNode"]:
    """Liefert die Ziel-Organisation der Kante, falls sie eine ist."""
    target_uuid = edge.get("target_node_uuid")
    if not isinstance(target_uuid, str):
        return None
    target = by_uuid.get(target_uuid)
    if target is None or target.uuid == person.uuid:
        return None
    return target if _is_organization_entity(target) else None


def _find_representatives(
    persons: "List[EntityNode]", by_uuid: Dict[str, "EntityNode"]
) -> Dict[str, "List[EntityNode]"]:
    """Organisation-UUID -> Liste der sie laut Graph-Relation vertretenden Personen."""
    representatives: Dict[str, List["EntityNode"]] = {}
    for person in persons:
        for edge in person.related_edges or []:
            if not _is_representation_edge(edge):
                continue
            target = _representation_target(person, edge, by_uuid)
            if target is None:
                continue
            representatives.setdefault(target.uuid, []).append(person)
    return representatives


def _apply_single_representative_merge(
    person: "EntityNode",
    org: "EntityNode",
    degradations: Optional[DegradationCollector],
) -> None:
    """Regelfall (Issue #1713): genau eine Person vertritt die Organisation."""
    person.affiliation = org.name
    _legacy.logger.info(
        "Person-Organisation-Zusammenlegung (#1713): person=%s organisation=%s "
        "— ein Agent statt zwei",
        person.name,
        org.name,
    )
    if degradations is not None:
        degradations.record(
            DegradationKind.PERSON_REPRESENTS_ORGANIZATION_MERGED,
            DegradationSeverity.WARNING,
            f"{person.name} vertritt {org.name} laut Graph-Relation; "
            "Organisation wird nicht zusaetzlich als eigener Agent gefuehrt.",
            context={"person_uuid": person.uuid, "organization_uuid": org.uuid},
        )


def _apply_collective_affiliation(persons: "List[EntityNode]", org: "EntityNode") -> None:
    """Kollektiver Akteur (Issue #1713): Organisation bleibt eigener Agent."""
    for person in persons:
        person.affiliation = org.name
    _legacy.logger.info(
        "Organisation bleibt eigener Agent (#1713): organisation=%s wird von "
        "%d Personen vertreten (kollektiver Akteur)",
        org.name,
        len(persons),
    )


def _genitive_stem(token: str) -> str:
    """Streicht ein Genitiv-s/-es ("landkreises" -> "landkreis"), konservativ."""
    if token.endswith("es") and len(token) >= 7:
        return token[:-2]
    if len(token) >= 6 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _variant_tokens(name: str) -> tuple[str, ...]:
    """Vergleichstokens eines Organisationsnamens (#1759 A4)."""
    cleaned = re.sub(r"\([^)]*\)", " ", name or "")
    tokens: list[str] = []
    for raw in re.split(r"[\s,;/]+", cleaned):
        token = raw.strip(".:\"'()[]").casefold()
        if not token or token in _VARIANT_FUNCTION_WORDS or token in _VARIANT_LEGAL_FORMS:
            continue
        tokens.append(_genitive_stem(token))
    return tuple(tokens)


def _organ_split(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Trennt fuehrende Organ-Woerter ("Geschaeftsfuehrung ...") vom Rest."""
    organ_end = 0
    while organ_end < len(tokens) and tokens[organ_end] in _ORGAN_WORDS:
        organ_end += 1
    return tokens[:organ_end], tokens[organ_end:]


def _organ_target_index(
    organ: "EntityNode", org_indices: List[int], entities: "List[EntityNode]", self_index: int
) -> Optional[int]:
    """Index der einen Organisation, an die eine Belegkante das Organ bindet."""
    uuid_to_index = {entities[i].uuid: i for i in org_indices if i != self_index}
    targets: set[int] = set()
    for edge in organ.related_edges or []:
        if edge.get("direction") != "outgoing":
            continue
        if str(edge.get("edge_name") or "").strip().upper() not in _ORGAN_RELATION_TYPES:
            continue
        target_uuid = edge.get("target_node_uuid")
        if isinstance(target_uuid, str) and target_uuid in uuid_to_index:
            targets.add(uuid_to_index[target_uuid])
    return next(iter(targets)) if len(targets) == 1 else None


def _union_name_variants(
    uf: "_UnionFind", org_indices: List[int], tokens: Dict[int, tuple[str, ...]]
) -> None:
    """Verbindet Organisationen mit gleicher Tokenmenge oder eindeutiger Obermenge."""
    for pos, i in enumerate(org_indices):
        if not tokens[i]:
            continue
        for j in org_indices[pos + 1 :]:
            if tokens[j] and set(tokens[i]) == set(tokens[j]):
                uf.union(i, j)
        supersets = [
            j
            for j in org_indices
            if j != i
            and tokens[j]
            and tokens[j][0] == tokens[i][0]
            and set(tokens[i]) < set(tokens[j])
        ]
        if len(supersets) == 1:
            uf.union(i, supersets[0])


def _organ_base_index(
    i: int, rest: tuple[str, ...], org_indices: List[int], tokens: Dict[int, tuple[str, ...]]
) -> Optional[int]:
    """Index der einen Organisation, die der Organ-Name eindeutig enthaelt."""
    bases = [
        j
        for j in org_indices
        if j != i and tokens[j] and set(tokens[j]) == set(rest) and not _organ_split(tokens[j])[0]
    ]
    return bases[0] if len(bases) == 1 else None


def _union_entity_variants(
    entities: "List[EntityNode]", org_indices: List[int]
) -> "tuple[_UnionFind, set[int]]":
    """Verbindet Organisations-Varianten; liefert Union-Find und aufgehende Organe."""
    tokens = {i: _variant_tokens(entities[i].name) for i in org_indices}
    uf = _UnionFind(len(entities))
    absorbed: set[int] = set()
    _union_name_variants(uf, org_indices, tokens)

    for i in org_indices:
        organ_words, rest = _organ_split(tokens[i])
        if not organ_words:
            continue
        if rest:
            target = _organ_base_index(i, rest, org_indices, tokens)
        else:
            target = _organ_target_index(entities[i], org_indices, entities, i)
        if target is not None:
            uf.union(i, target)
            absorbed.add(i)
    return uf, absorbed


def _absorb_variants(survivor: "EntityNode", aliases: "List[EntityNode]") -> None:
    """Uebernimmt Aliase und Attribute in ``survivor`` (in place)."""
    merged = _attach_aliases(survivor, aliases)
    attrs = merged.attributes
    carried = list(attrs.get("_agora_aliases", []))
    for alias in aliases:
        for earlier in alias.attributes.get("_agora_aliases", []):
            if earlier not in carried:
                carried.append(earlier)
        for key, value in alias.attributes.items():
            if key.startswith("_agora_"):
                continue
            if key not in attrs or attrs[key] in (None, "", [], {}):
                attrs[key] = value
            elif attrs[key] != value and value not in (None, "", [], {}):
                _logger.info(
                    "Entity-Merge-Attributkonflikt (#1759): survivor=%s verworfen_aus=%s "
                    "attribut=%s survivor_wert=%r verworfener_wert=%r",
                    survivor.name,
                    alias.name,
                    key,
                    attrs[key],
                    value,
                )
    attrs["_agora_aliases"] = carried
    if not survivor.summary:
        for alias in aliases:
            if alias.summary:
                survivor.summary = alias.summary
                summaries = attrs.get("_agora_alias_summaries", [])
                if alias.summary in summaries:
                    summaries.remove(alias.summary)
                if not summaries:
                    attrs.pop("_agora_alias_summaries", None)
                break
    survivor.attributes = attrs
    survivor.related_edges = merged.related_edges
    survivor.related_nodes = merged.related_nodes


def _pick_variant_survivor(
    cluster: List[int], absorbed: set[int], entities: "List[EntityNode]"
) -> int:
    """Informativster Name (meiste Tokens, dann laengster), Organe gehen auf."""
    candidates = [i for i in cluster if i not in absorbed] or cluster
    return max(
        candidates,
        key=lambda i: (len(_variant_tokens(entities[i].name)), len(entities[i].name), -i),
    )


def _remap_edge_targets(
    entities: "List[EntityNode]", remap: Dict[str, str]
) -> None:
    """Zeigt Kanten auf zusammengefuehrte UUIDs auf den Survivor um."""
    for entity in entities:
        edges = []
        for edge in entity.related_edges or []:
            target = edge.get("target_node_uuid")
            if isinstance(target, str) and target in remap:
                edge = {**edge, "target_node_uuid": remap[target]}
            if edge.get("target_node_uuid") == entity.uuid:
                continue
            edges.append(edge)
        entity.related_edges = edges


def _merge_entity_variants(entities: "List[EntityNode]") -> "List[EntityNode]":
    """Fuehrt Namensvarianten derselben Organisation vor der Persona-Auswahl zusammen."""
    org_indices = [i for i, e in enumerate(entities) if _is_organization_entity(e)]
    if len(org_indices) < 2:
        return entities

    uf, absorbed = _union_entity_variants(entities, org_indices)
    clusters = [c for c in uf.clusters(len(entities)).values() if len(c) > 1]
    if not clusters:
        return entities

    replacements: Dict[int, Optional["EntityNode"]] = {}
    remap: Dict[str, str] = {}
    for cluster in clusters:
        cluster = sorted(cluster)
        survivor_index = _pick_variant_survivor(cluster, absorbed, entities)
        survivor = entities[survivor_index]
        aliases = [entities[i] for i in cluster if i != survivor_index]
        _absorb_variants(survivor, aliases)
        _logger.info(
            "Entity-Varianten-Merge (#1759): %d Entitaeten zu '%s' zusammengefasst "
            "(Aliase=%s)",
            len(cluster),
            survivor.name,
            [a.name for a in aliases],
        )
        for alias in aliases:
            remap[alias.uuid] = survivor.uuid
        for i in cluster:
            replacements[i] = None
        replacements[cluster[0]] = survivor

    merged: "List[EntityNode]" = []
    for i, entity in enumerate(entities):
        kept = replacements.get(i, entity)
        if kept is not None:
            merged.append(kept)
    _remap_edge_targets(merged, remap)
    return merged


def _merge_persons_with_organizations(
    entities: "List[EntityNode]",
    degradations: Optional[DegradationCollector] = None,
) -> "List[EntityNode]":
    """Legt eine Person mit der Organisation zusammen, die sie laut Graph vertritt."""
    by_uuid = {entity.uuid: entity for entity in entities}
    if len(by_uuid) < 2:
        return entities

    persons = [entity for entity in entities if not _is_organization_entity(entity)]
    if not persons:
        return entities

    representatives = _find_representatives(persons, by_uuid)
    if not representatives:
        return entities

    merged_org_uuids: set[str] = set()
    for org_uuid, reps in representatives.items():
        org = by_uuid[org_uuid]
        unique_reps = list({person.uuid: person for person in reps}.values())

        if len(unique_reps) == 1:
            _apply_single_representative_merge(unique_reps[0], org, degradations)
            merged_org_uuids.add(org_uuid)
        else:
            _apply_collective_affiliation(unique_reps, org)

    if not merged_org_uuids:
        return entities

    return [entity for entity in entities if entity.uuid not in merged_org_uuids]


def _build_eligible_uuid_pool(
    reader: "EntityReader",
    graph_id: str,
    defined_entity_types: Optional[List[str]],
) -> Dict[str, "EntityNode"]:
    """Liest den aktuellen eignungsgefilterten Entity-Pool, geschlüsselt per UUID."""
    filtered = reader.filter_defined_entities(
        graph_id=graph_id,
        defined_entity_types=defined_entity_types,
        enrich_with_edges=True,
    )
    eligibility = _legacy.filter_eligible_entities(filtered.entities, degradations=None)
    pool = eligibility.eligible if eligibility.exclusions else filtered.entities
    return {entity.uuid: entity for entity in pool}


def _lookup_entities_by_uuid(
    by_uuid: Dict[str, "EntityNode"], uuids: List[str]
) -> List[Optional["EntityNode"]]:
    """Bildet eine UUID-Liste (Reihenfolge und Wiederholungen erhalten) auf Entities ab."""
    return [by_uuid.get(uuid) for uuid in uuids]


def _phase_read_entities_from_checkpoint(
    state: "SimulationState",
    storage: Any,
    checkpoint: "PreparePersonaCheckpoint",
    progress_callback: Optional[Callable] = None,
) -> Optional[FilteredEntities]:
    """Resume-Variante von Phase 1 (Issue #1472c)."""
    if progress_callback:
        progress_callback("reading", 0, "Resuming entity selection from checkpoint...")

    if not storage:
        raise ValueError("storage (GraphStorage) is required for prepare_simulation")
    reader = _legacy.EntityReader(storage)

    by_uuid = _build_eligible_uuid_pool(
        reader, checkpoint.graph_id, checkpoint.defined_entity_types
    )
    primary_raw = _lookup_entities_by_uuid(by_uuid, checkpoint.primary_entity_uuids)
    if any(entity is None for entity in primary_raw):
        _legacy.logger.warning(
            "Prepare-Resume: mindestens eine im Checkpoint fixierte "
            "Entitaet wurde im Graphen nicht mehr gefunden — Checkpoint "
            "gilt als entwertet, Auswahl wird neu berechnet."
        )
        return None
    primary: List["EntityNode"] = [entity for entity in primary_raw if entity is not None]
    reserve = [
        entity
        for entity in _lookup_entities_by_uuid(by_uuid, checkpoint.reserve_entity_uuids)
        if entity is not None
    ]

    filtered = FilteredEntities(
        entities=list(primary),
        entity_types=set(checkpoint.entity_types),
        total_count=len(primary),
        filtered_count=len(primary),
        reserve_entities=reserve,
        selection_decisions=list(checkpoint.selection_reasons),
    )

    state.entities_count = checkpoint.entities_count
    state.entity_types = list(checkpoint.entity_types)

    if progress_callback:
        progress_callback(
            "reading",
            100,
            f"Resumed, total {filtered.filtered_count} entities",
            current=filtered.filtered_count,
            total=filtered.filtered_count,
        )

    return filtered


def _lookup_expanded_entities_from_checkpoint(
    storage: Any, checkpoint: "PreparePersonaCheckpoint"
) -> Optional[List["EntityNode"]]:
    """Rekonstruiert die eingefrorene, quota-expandierte Generierungsliste."""
    reader = _legacy.EntityReader(storage)
    by_uuid = _build_eligible_uuid_pool(
        reader, checkpoint.graph_id, checkpoint.defined_entity_types
    )
    expanded_raw = _lookup_entities_by_uuid(by_uuid, checkpoint.expanded_entity_uuids)
    if any(entity is None for entity in expanded_raw):
        _legacy.logger.warning(
            "Prepare-Resume: mindestens eine im Checkpoint fixierte "
            "Generierungs-Entitaet wurde im Graphen nicht mehr gefunden — "
            "Checkpoint gilt als entwertet, Auswahl wird neu berechnet."
        )
        return None
    return [entity for entity in expanded_raw if entity is not None]
