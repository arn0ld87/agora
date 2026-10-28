"""Entity normalization, deduplication, and capping helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from .entity_reader import EntityNode


def _strip_leading_article(tokens: list[str]) -> list[str]:
    """Entfernt fuehrende Artikel, falls danach noch ein Namensrest bleibt."""
    from . import prepare_service as _legacy

    while len(tokens) > 1 and tokens[0].casefold() in _legacy._LEADING_ARTICLES:
        tokens = tokens[1:]
    return tokens


def _normalize_adjective_endings(tokens: list[str]) -> list[str]:
    """Gleicht einfache Adjektivflexion an ("digitaler"/"digitale"/"digitalen" -> "digital")."""
    from . import prepare_service as _legacy

    if len(tokens) < 2:
        return tokens
    normalized = list(tokens)
    index = len(normalized) - 2
    lower = normalized[index].casefold()
    for suffix in _legacy._ADJECTIVE_SUFFIXES:
        stem_length = len(lower) - len(suffix)
        if lower.endswith(suffix) and stem_length >= _legacy._MIN_ADJECTIVE_STEM_LENGTH:
            normalized[index] = lower[:-len(suffix)]
            break
    return normalized


def _entity_identity_key(entity: EntityNode) -> tuple[str, str]:
    """Vergleichsschluessel fuer Persona-Kandidaten (Issue #1177, #1177-Folge)."""
    from . import prepare_entities as _pe

    tokens = (entity.name or "").split()
    tokens = _pe._strip_leading_article(tokens)
    tokens = _pe._normalize_adjective_endings(tokens)
    name = " ".join(tokens).casefold()
    entity_type = " ".join((entity.get_entity_type() or "Entity").split()).casefold()
    return name, entity_type


def _dedupe_entities(
    entities: List[EntityNode],
) -> tuple[List[EntityNode], int]:
    """Entfernt Mehrfachnennungen; erste Nennung gewinnt.

    Gibt die bereinigte Liste und die Zahl entfernter Dubletten zurueck.
    """
    from . import prepare_entities as _pe

    seen: set[tuple[str, str]] = set()
    unique: List[EntityNode] = []
    for entity in entities:
        key = _pe._entity_identity_key(entity)
        if key in seen:
            continue
        seen.add(key)
        unique.append(entity)
    return unique, len(entities) - len(unique)


def _cap_entities_across_types(
    entities: List[EntityNode], max_agents: int
) -> List[EntityNode]:
    """Kappt auf ``max_agents`` und sichert dabei jedem Typ einen Platz."""
    if max_agents <= 0 or len(entities) <= max_agents:
        return list(entities)

    by_type: Dict[str, List[EntityNode]] = {}
    for entity in entities:
        by_type.setdefault(entity.get_entity_type() or "Entity", []).append(entity)

    selected: List[EntityNode] = []
    round_index = 0
    while len(selected) < max_agents:
        added_this_round = False
        for bucket in by_type.values():
            if round_index >= len(bucket):
                continue
            selected.append(bucket[round_index])
            added_this_round = True
            if len(selected) >= max_agents:
                break
        if not added_this_round:
            break
        round_index += 1

    return selected
