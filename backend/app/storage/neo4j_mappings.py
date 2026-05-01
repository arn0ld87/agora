"""
Zentrale Storage-Helfer: Record-Mapping und Cypher-Identifier-Sanitization.

Issue #50 (EPIC-08-ST-01), Sub-Slice 1: Wiederverwendbare, statelose
Helfer für Read- und Search-Pfade. Keine Driver-/Session-Bindung,
keine Zustandszugriffe — alles unit-testbar.

Inhalt:

- ``node_to_dict(node, labels)`` baut das Standard-Node-Dict (uuid, name,
  labels ohne ``Entity``, summary, attributes, created_at).
- ``edge_to_dict(rel, source_uuid, target_uuid)`` baut das Standard-
  Edge-Dict inkl. der Issue-#10-Temporalfelder
  (``valid_from_round``/``valid_to_round``/``reinforced_count``).
- ``sanitize_label(value)`` validiert LLM-erzeugte Labels gegen eine
  ASCII-Identifier-Whitelist; Cypher erlaubt Labels nur als Identifier
  (nicht als Parameter), und ungefiltert wären sie ein Backtick-
  Quoting-Injektionsvektor.

Internfelder (``embedding``, ``name_lower``, ``fact_embedding``) werden
beim Mapping verworfen — sie gehören nicht ins Wire-Format.
"""

import json
import re
from typing import Any, Dict, List, Optional


# Cypher erlaubt Labels nur als Identifier, nicht als Parameter. Labels kommen
# aus LLM-Output (Entity-Type aus NER) — ohne Filter liefert das einen
# f-string-Injection-Vektor (Backticks im Namen brechen aus dem Quoting aus).
# Whitelist-Regex: Buchstabe/Underscore-Start, dann A-Za-z0-9_, max 50 Zeichen.
_LABEL_SAFE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,49}$")


def sanitize_label(value: Any) -> Optional[str]:
    """Return a Cypher-safe label or ``None`` when the input is unusable.

    Akzeptiert nur Strings, normalisiert Whitespace zu ``_``, entfernt
    Nicht-ASCII (Umlaute etc., damit Neo4j-Labels lesbar bleiben), und
    matcht abschließend gegen ``_LABEL_SAFE_RE``. ``"Entity"`` wird
    explizit verworfen, weil das die Default-Label ist.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped == "Entity":
        return None
    normalized = re.sub(r"\s+", "_", stripped)
    normalized = re.sub(r"[^A-Za-z0-9_]", "", normalized)
    if not _LABEL_SAFE_RE.match(normalized):
        return None
    return normalized


def _safe_attributes(props: Dict[str, Any]) -> Dict[str, Any]:
    """Robuster JSON-Parser für ``attributes_json`` (verworfen aus props)."""
    attrs_json = props.pop("attributes_json", "{}")
    try:
        return json.loads(attrs_json) if attrs_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def node_to_dict(node: Any, labels: List[str]) -> Dict[str, Any]:
    """Convert a Neo4j node record into the standard node dict format."""
    props = dict(node)
    attributes = _safe_attributes(props)

    # Internal fields never travel via the wire.
    props.pop("embedding", None)
    props.pop("name_lower", None)

    return {
        "uuid": props.get("uuid", ""),
        "name": props.get("name", ""),
        "labels": [lbl for lbl in labels if lbl != "Entity"] if labels else [],
        "summary": props.get("summary", ""),
        "attributes": attributes,
        "created_at": props.get("created_at"),
    }


def edge_to_dict(rel: Any, source_uuid: str, target_uuid: str) -> Dict[str, Any]:
    """Convert a Neo4j relationship record into the standard edge dict format."""
    props = dict(rel)
    attributes = _safe_attributes(props)

    # Internal field — embedding never travels via the wire.
    props.pop("fact_embedding", None)

    episode_ids = props.get("episode_ids", [])
    if episode_ids and not isinstance(episode_ids, list):
        episode_ids = [str(episode_ids)]

    return {
        "uuid": props.get("uuid", ""),
        "name": props.get("name", ""),
        "fact": props.get("fact", ""),
        "source_node_uuid": source_uuid,
        "target_node_uuid": target_uuid,
        "attributes": attributes,
        "created_at": props.get("created_at"),
        "valid_at": props.get("valid_at"),
        "invalid_at": props.get("invalid_at"),
        "expired_at": props.get("expired_at"),
        "valid_from_round": props.get("valid_from_round"),
        "valid_to_round": props.get("valid_to_round"),
        "reinforced_count": props.get("reinforced_count", 1),
        "episode_ids": episode_ids,
    }


__all__ = [
    "node_to_dict",
    "edge_to_dict",
    "sanitize_label",
]
