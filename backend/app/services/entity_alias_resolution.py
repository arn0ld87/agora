"""Alias-Auflösung für Persona-Kandidaten vor dem Cap (Issue #1470, Slice 4.2).

Fasst Entitäten, die dieselbe reale Person oder Organisation benennen, zu
einem Cluster zusammen.  Arbeitet rein deterministisch — kein LLM-Aufruf.

Aufgerufen in ``_phase_read_entities`` zwischen Eligibility-Filter und
Dedupe/Cap.  Kein Merge über semantische Klassen hinweg.

Cluster-Regeln (innerhalb derselben semantischen Klasse):

A  Normalisierung
   Casefold, Titel strippen (Dr., Prof., Dipl.-Ing., Herr, Frau …),
   Whitespace kollabieren, Bindestrich-Varianten ignorieren.

B  Klammer-Expansion
   „Berufsförderungswerk Leipzig (BFW Leipzig)" liefert Aliase
   {„berufsförderungswerk leipzig", „bfw leipzig"}.  Zwei Entitäten mit
   einem gemeinsamen normalisierten Alias werden geclustert.

C  Token-Teilmenge (Organisationen)
   „BFW" ⊂ „BFW Leipzig" → Alias, wenn genau EIN anderer Kandidat
   im primären (geklammer-bereinigten) Tokensatz ein Superset enthält.
   Mehrdeutige Kurzformen (zwei oder mehr Kandidaten) bleiben getrennt.
   Transitiv durch Klammer-Aliase: BFW → BFW Leipzig →
   Berufsförderungswerk Leipzig (BFW Leipzig) ⇒ ein Cluster.

D  Personen-Nachnamen
   „Vogt" (einzelner Token) → Alias zu „Dr. Miriam Vogt", wenn genau EINE
   Person-Klassen-Entität diesen Nachnamen als letzten Token trägt.  Bei
   zwei Personen mit gleichem Nachnamen bleibt die Kurzform getrennt.

E  Kanonischer Repräsentant
   Die informativste Nennung (längster Name, bei Gleichstand erste
   Nennung in der Originalliste).  Aliase werden als
   ``attributes["_agora_aliases"]`` am kanonischen Entity gespeichert und
   geloggt.  Summaries/Kontexte der gemergten Aliase bleiben erhalten
   (``attributes["_agora_alias_summaries"]``).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import replace
from typing import Any, Dict, List

from ..contracts.entity_semantic_class_contract import SemanticEntityClass
from ..utils.logger import get_logger
from .entity_reader import EntityNode
from .entity_semantic_class import classify_entity

logger = get_logger("agora.entity_alias_resolution")

# ---------------------------------------------------------------------------
# Titelwörter, die aus Personennamen herausgefiltert werden.
# Geprüft nach casefold() + strip('.').
# ---------------------------------------------------------------------------
_STRIP_TITLES: frozenset[str] = frozenset(
    {
        "dr",
        "prof",
        "dipl",
        "herr",
        "frau",
        "mag",
        "ing",
        "doz",
        "rev",
        "sir",
        "mr",
        "mrs",
        "ms",
        "mx",
        "dr.-ing",
        "dipl.-ing",
        "dipl.-kfm",
        "dipl.-kaufm",
        "dipl.-inform",
        "dipl.-wirt",
    }
)

_BRACKET_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")
_BRACKET_STRIP_RE = re.compile(r"\s*\([^)]*\)\s*")


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _strip_titles(name: str) -> str:
    """Entfernt führende Titel aus einem Personennamen."""
    tokens = name.strip().split()
    while tokens:
        lower = tokens[0].casefold().rstrip(".")
        if lower in _STRIP_TITLES:
            tokens = tokens[1:]
        else:
            break
    return " ".join(tokens)


def _normalize_name(name: str) -> str:
    """Casefold + Titel strippen + Whitespace kollabieren."""
    return " ".join(_strip_titles(name).split()).casefold()


def _bracket_aliases(name: str) -> frozenset[str]:
    """Normalisierte Klammer-Aliase eines Namens (inkl. des Namens selbst)."""
    aliases: set[str] = {_normalize_name(name)}
    m = _BRACKET_RE.match(name.strip())
    if m:
        main = m.group(1).strip()
        bracket = m.group(2).strip()
        if main:
            aliases.add(_normalize_name(main))
        if bracket:
            aliases.add(_normalize_name(bracket))
    return frozenset(aliases)


def _primary_tokens(name: str) -> frozenset[str]:
    """Token-Menge des Primärnamens (Klammer-Inhalt entfernt)."""
    stripped = _BRACKET_STRIP_RE.sub(" ", _normalize_name(name)).strip()
    return frozenset(t for t in stripped.split() if t)


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def clusters(self, n: int) -> Dict[int, List[int]]:
        result: Dict[int, List[int]] = defaultdict(list)
        for i in range(n):
            result[self.find(i)].append(i)
        return result


# ---------------------------------------------------------------------------
# Clustering pro semantische Klasse
# ---------------------------------------------------------------------------


def _cluster_persons(entities: List[EntityNode]) -> List[List[EntityNode]]:
    """Clustert Person-Entitäten via Nachname und identischen normierten Namen."""
    n = len(entities)
    uf = _UnionFind(n)
    normalized = [_normalize_name(e.name) for e in entities]

    # Phase A: Gleicher normierter Name → gleicher Cluster
    # (z. B. "Vogt" (Person) und "Vogt" (Executive) → identisch)
    name_to_idx: Dict[str, List[int]] = defaultdict(list)
    for i, norm in enumerate(normalized):
        name_to_idx[norm].append(i)
    for indices in name_to_idx.values():
        for i in range(1, len(indices)):
            uf.union(indices[0], indices[i])

    # Phase B: Eintokeniger Nachname → Vollname-Match
    for i, norm in enumerate(normalized):
        tokens = norm.split()
        if len(tokens) != 1:
            continue
        last = tokens[0]
        # Entitäten mit Mehrtokenname, deren letzter Token mit `last` übereinstimmt
        candidates = [
            j
            for j, norm_j in enumerate(normalized)
            if len(norm_j.split()) > 1 and norm_j.split()[-1] == last
        ]
        if len(candidates) == 1:
            uf.union(i, candidates[0])
        # ≥ 2 Kandidaten → mehrdeutig → getrennt lassen

    return [[entities[i] for i in idxs] for idxs in uf.clusters(n).values()]


def _cluster_organizations(entities: List[EntityNode]) -> List[List[EntityNode]]:
    """Clustert Organisation-Entitäten via Klammer-Aliase und Token-Teilmenge."""
    n = len(entities)
    uf = _UnionFind(n)

    alias_sets = [_bracket_aliases(e.name) for e in entities]
    primary_tok = [_primary_tokens(e.name) for e in entities]

    # Phase B: Gemeinsamer normierter Alias → gleicher Cluster
    for i in range(n):
        for j in range(i + 1, n):
            if alias_sets[i] & alias_sets[j]:
                uf.union(i, j)

    # Phase C: Token-Teilmenge (nur primäre Tokens, nicht Klammer-Aliase)
    for i in range(n):
        tok_i = primary_tok[i]
        if not tok_i:
            continue
        # Kandidaten j, deren primäre Token-Menge tok_i als ECHTE Teilmenge enthält
        candidates = [
            j for j in range(n) if j != i and tok_i < primary_tok[j]
        ]
        if len(candidates) == 1:
            uf.union(i, candidates[0])
        # ≥ 2 Kandidaten: mehrdeutig → getrennt

    return [[entities[i] for i in idxs] for idxs in uf.clusters(n).values()]


# ---------------------------------------------------------------------------
# Kanonischen Repräsentanten wählen und Aliase anhängen
# ---------------------------------------------------------------------------


def _pick_canonical(cluster: List[EntityNode], order: Dict[str, int]) -> EntityNode:
    """Informativster Name (länger = besser), Gleichstand: erste Nennung."""

    def _score(e: EntityNode) -> tuple:
        norm = _normalize_name(e.name)
        toks = norm.split()
        return (
            len(toks) >= 2,        # Vor- + Nachname hat Vorrang
            len(e.name),           # Längerer Name ist informativer
            -(order.get(e.uuid, 0)),  # Frühere Nennung bei Gleichstand
        )

    return max(cluster, key=_score)


def _attach_aliases(
    entity: EntityNode,
    aliases: List[EntityNode],
) -> EntityNode:
    """Hängt Alias-Namen und -Summaries an das kanonische Entity-Attribut-Dict."""
    new_attrs = dict(entity.attributes)

    existing_aliases: list[str] = list(new_attrs.get("_agora_aliases", []))
    alias_names = [a.name for a in aliases]
    new_attrs["_agora_aliases"] = existing_aliases + alias_names

    # Summaries der Aliase optional erhalten, damit Kontext nicht verloren geht
    alias_summaries = [a.summary for a in aliases if a.summary]
    if alias_summaries:
        existing_summaries: list[str] = list(
            new_attrs.get("_agora_alias_summaries", [])
        )
        new_attrs["_agora_alias_summaries"] = existing_summaries + alias_summaries

    # Codex-Review PR #1606 (P1): Der Persona-Kontext wird direkt aus
    # ``related_edges``/``related_nodes`` gebaut
    # (``oasis_profile_context._build_entity_context``). Fakten, die nur an
    # einem Alias hingen, gingen sonst beim Merge verloren.
    cluster_uuids = {entity.uuid, *(a.uuid for a in aliases)}
    related_edges = _merge_unique(
        [entity.related_edges, *(a.related_edges for a in aliases)]
    )
    related_nodes = [
        node
        for node in _merge_unique([entity.related_nodes, *(a.related_nodes for a in aliases)])
        if not (isinstance(node, dict) and node.get("uuid") in cluster_uuids)
    ]
    return replace(
        entity,
        attributes=new_attrs,
        related_edges=related_edges,
        related_nodes=related_nodes,
    )


def _merge_unique(groups: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Listen zusammenführen, Dubletten (inhaltsgleiche Dicts) entfernen."""
    seen: set[str] = set()
    merged: List[Dict[str, Any]] = []
    for group in groups:
        for item in group or []:
            key = json.dumps(item, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                merged.append(item)
    return merged


# ---------------------------------------------------------------------------
# Öffentliche Funktion
# ---------------------------------------------------------------------------


def resolve_aliases(entities: List[EntityNode]) -> List[EntityNode]:
    """Fasst Alias-Entitäten zusammen und gibt die bereinigte Liste zurück.

    Kein Merge über semantische Klassen hinweg.  Jede gemergete Gruppe wird
    durch ihren kanonischen Repräsentanten vertreten; die Originalnamen der
    Aliase sind unter ``attributes["_agora_aliases"]`` abrufbar.

    Args:
        entities: Eligibility-gefilterte Entitäten (vor Dedupe/Cap).

    Returns:
        Bereinigte Liste; kann kürzer als ``entities`` sein.
    """
    if not entities:
        return []

    # Originalreihenfolge für Gleichstand-Auflösung
    original_order: Dict[str, int] = {e.uuid: i for i, e in enumerate(entities)}

    # Klassifikation und Gruppierung nach semantischer Klasse
    by_class: Dict[SemanticEntityClass, List[EntityNode]] = defaultdict(list)
    for entity in entities:
        cls = classify_entity(entity.name, entity.get_entity_type() or "")
        by_class[cls].append(entity)

    # Codex-Review PR #1606 (P2): Der Cap vergibt Plätze nach erster Nennung.
    # Ausgegeben wird deshalb in der Reihenfolge der frühesten Nennung je
    # Cluster, nicht gruppiert nach Klasse.
    positioned: List[tuple[int, EntityNode]] = []

    for cls, class_entities in by_class.items():
        if cls == SemanticEntityClass.PERSON:
            clusters = _cluster_persons(class_entities)
        elif cls == SemanticEntityClass.ORGANIZATION:
            clusters = _cluster_organizations(class_entities)
        else:
            # Andere Klassen: kein Merging (population, technology, …)
            clusters = [[e] for e in class_entities]

        for cluster in clusters:
            first_position = min(original_order[e.uuid] for e in cluster)
            if len(cluster) == 1:
                positioned.append((first_position, cluster[0]))
                continue
            canonical = _pick_canonical(cluster, original_order)
            aliases = [e for e in cluster if e.uuid != canonical.uuid]
            canonical = _attach_aliases(canonical, aliases)
            alias_names = [a.name for a in aliases]
            logger.info(
                "Alias-Aufloesung: %d Entitaeten zu '%s' zusammengefasst "
                "(Klasse=%s, Aliase=%s)",
                len(cluster),
                canonical.name,
                cls.value,
                alias_names,
            )
            positioned.append((first_position, canonical))

    positioned.sort(key=lambda entry: entry[0])
    return [entity for _position, entity in positioned]


__all__ = ["resolve_aliases"]
