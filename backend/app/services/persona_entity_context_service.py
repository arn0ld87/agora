"""Laedt den Entity-Kontext aus dem Knowledge Graph fuer eine einzelne Persona.

Issue #69 EPIC-13-ST-02: Persona-Diff gegen Entity-Kontext.

Verbraucht source_entity_uuid aus dem reddit_profiles.json-Eintrag (geschrieben
von OasisAgentProfile.to_reddit_format) und liest die zugehoerige Entity aus
Neo4j via GraphStorage.get_node() + EntityReader.get_node_edges().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..contracts import EntityRelationship, PersonaEntityContext
from ..storage import GraphStorage
from ..utils.logger import get_logger
from .entity_reader import EntityReader

logger = get_logger("agora.persona_entity_context")

# Maximale Anzahl Relationships in der Response (verhindert ueberlange Payloads)
_MAX_RELATIONSHIPS = 50


class PersonaEntityContextService:
    """Read-only Service: Persona -> source_entity_uuid -> Entity-Properties + Relationships."""

    def __init__(self, storage: GraphStorage) -> None:
        self._storage = storage
        self._reader = EntityReader(storage)

    def build_context(
        self,
        *,
        simulation_id: str,
        username: str,
        profile: Dict[str, Any],
    ) -> PersonaEntityContext:
        """Build PersonaEntityContext from a persona profile dict.

        Looks up source_entity_uuid in profile, loads matching node from
        graph storage, and returns typed PersonaEntityContext.

        If source_entity_uuid is missing (legacy persona), returns a fallback
        context using only fields that ARE in the profile.

        If uuid is set but graph lookup fails, also returns fallback (logger
        warning).
        """
        source_uuid = profile.get("source_entity_uuid")
        source_type = str(profile.get("source_entity_type") or "Entity")
        now = datetime.now(timezone.utc)

        if not source_uuid:
            # Legacy persona without entity link
            return PersonaEntityContext(
                username=username,
                simulation_id=simulation_id,
                entity_uuid="",
                entity_label=str(profile.get("name") or username),
                entity_type=source_type,
                entity_summary=None,
                entity_properties={},
                relationships=[],
                generated_at=now,
                source="fallback",
            )

        # Try graph lookup via storage.get_node (Strategy 1 — abstract API)
        node = self._lookup_node(source_uuid)
        if node is None:
            logger.info(
                "PersonaEntityContextService: entity uuid=%s not found in graph "
                "(stale profile?), returning fallback context",
                source_uuid,
            )
            return PersonaEntityContext(
                username=username,
                simulation_id=simulation_id,
                entity_uuid=source_uuid,
                entity_label=str(profile.get("name") or username),
                entity_type=source_type,
                entity_summary=None,
                entity_properties={},
                relationships=[],
                generated_at=now,
                source="fallback",
            )

        # Coerce node properties to scalar types for extra="forbid" compat
        raw_attributes: Dict[str, Any] = node.get("attributes") or {}
        coerced_props = _coerce_properties(raw_attributes)

        relationships = self._build_relationships(source_uuid)

        return PersonaEntityContext(
            username=username,
            simulation_id=simulation_id,
            entity_uuid=source_uuid,
            entity_label=str(node.get("name") or profile.get("name") or username),
            entity_type=source_type,
            entity_summary=node.get("summary") or None,
            entity_properties=coerced_props,
            relationships=relationships,
            generated_at=now,
            source="graph",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_node(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Lookup a single node by uuid via GraphStorage.get_node()."""
        try:
            node = self._storage.get_node(uuid)
            if node:
                return node
        except Exception as exc:
            logger.warning(
                "PersonaEntityContextService: get_node(%s) failed: %s", uuid, exc
            )
        return None

    def _build_relationships(self, source_uuid: str) -> List[EntityRelationship]:
        """Return up to _MAX_RELATIONSHIPS relationships from source_uuid.

        Edge dict schema from neo4j_mappings.edge_to_dict:
            source_node_uuid, target_node_uuid, name (= relation type), fact, ...
        """
        try:
            edges = self._reader.get_node_edges(source_uuid)
        except Exception as exc:
            logger.warning(
                "PersonaEntityContextService: get_node_edges(%s) failed: %s",
                source_uuid,
                exc,
            )
            return []

        result: List[EntityRelationship] = []
        for edge in (edges or [])[:_MAX_RELATIONSHIPS]:
            # Determine relation type from the edge "name" field (standard edge-to-dict key)
            relation_type = str(edge.get("name") or "RELATED")

            # Determine the remote end of the relationship
            src = str(edge.get("source_node_uuid") or "")
            tgt = str(edge.get("target_node_uuid") or "")

            # The "other" node is not source_uuid
            if src == source_uuid:
                target_uuid = tgt
            elif tgt == source_uuid:
                target_uuid = src
            else:
                # Both differ — edge dict uses standard pair, skip if empty
                target_uuid = tgt

            if not target_uuid or target_uuid == source_uuid:
                continue

            # Best-effort: fetch the target node name for a human-readable label
            target_label = target_uuid
            target_type: Optional[str] = None
            try:
                target_node = self._storage.get_node(target_uuid)
                if target_node:
                    name_val = target_node.get("name")
                    if name_val:
                        target_label = str(name_val)
                    labels: List[str] = target_node.get("labels") or []
                    custom = [lb for lb in labels if lb not in ("Entity", "Node")]
                    if custom:
                        target_type = custom[0]
            except Exception as exc:
                logger.warning(
                    "PersonaEntityContextService: get_node(%s) for target failed: %s",
                    target_uuid,
                    exc,
                )

            result.append(
                EntityRelationship(
                    relation_type=relation_type,
                    target_uuid=target_uuid,
                    target_label=target_label,
                    target_type=target_type,
                )
            )
        return result


def _coerce_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    """Drop non-scalar values (lists, dicts, None) for extra='forbid' compat.

    Lists of strings become "a, b, c". Other complex types are JSON-stringified.
    None values are dropped (not sent to the client).
    """
    result: Dict[str, Any] = {}
    for key, val in props.items():
        if val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            result[key] = val
        elif isinstance(val, list) and all(isinstance(x, str) for x in val):
            result[key] = ", ".join(val)
        else:
            try:
                result[key] = json.dumps(val, ensure_ascii=False)
            except Exception:
                result[key] = str(val)
    return result


__all__ = ["PersonaEntityContextService"]
