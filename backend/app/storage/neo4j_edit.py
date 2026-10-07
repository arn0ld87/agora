"""
Schreibpfad für Handänderungen am Graphen (Issue #1808, ADR-0022).

``Neo4jEditMixin`` bündelt die Cypher-Statements zum Anlegen, Ändern,
Löschen und Zusammenführen von Entitäten und Beziehungen. Die Fachregeln
(Sperre, Ontologie-Prüfung, Embedding-Text, Migration) liegen im
``GraphEditService``; hier steht nur, was Neo4j ausführt.

Herkunft (ADR-0022 §1): Neu angelegte Elemente tragen ``origin='manual'``,
geänderte extrahierte Elemente ``origin='edited'``; beides mit
``origin_changed_at``. Ein manuelles Element bleibt ``manual``. Extrahierte
Elemente ohne Merkmal werden nicht angefasst, solange niemand sie ändert.

Idempotenz: Jede Schreib-Transaktion läuft unter ``_call_with_retry`` und
kann nach einer verlorenen Commit-Bestätigung erneut ausgeführt werden.
UUIDs und Zeitpunkte entstehen deshalb außerhalb der Transaktion (der
Service leitet sie aus ``client_request_id`` ab); das Anlegen erkennt einen
bereits geschriebenen Datensatz an seiner UUID und liefert ihn zurück,
statt ein zweites Element anzulegen.

Cypher-Identifier: Property-Namen der Einbettung stammen ausschließlich aus
dem ``EmbeddingConfigurationStore``, Labels laufen durch ``sanitize_label``.
Nutzereingaben werden nie in den Query-Text interpoliert.

Mixin-Voraussetzungen am konkreten Storage: ``_get_session``,
``_call_with_retry``, ``_embedding`` und ``_embedding_index_store``
(optional, wie in ``neo4j_write``).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable, ContextManager, Dict, List, Optional, Tuple

from ..services.embedding_configuration_store import EmbeddingConfigurationStore
from .neo4j_mappings import (
    ORIGIN_EDITED,
    ORIGIN_MANUAL,
    edge_to_dict,
    node_to_dict,
    sanitize_label,
)

if TYPE_CHECKING:
    from neo4j import Session

    from .embedding_service import EmbeddingService

logger = logging.getLogger("agora.neo4j_storage")

# Aliase stehen wie bei der Alias-Auflösung (``entity_alias_resolution``) in
# den Attributen der Entität.
ALIASES_KEY = "_agora_aliases"


class GraphEditNotFound(LookupError):
    """Das Element (oder ein Endpunkt der Beziehung) gibt es im Graphen nicht."""


class GraphEditConflict(Exception):
    """Die Änderung kollidiert mit einem bestehenden Element."""


def effective_entity_type(node_props: Dict[str, Any], labels: List[str]) -> Optional[str]:
    """Typ einer Entität: ``entity_type``, bei Altknoten das erste Typ-Label."""
    etype = node_props.get("entity_type")
    if isinstance(etype, str) and etype:
        return etype
    for label in labels or []:
        if label != "Entity":
            return label
    return None


def entity_embedding_text(name: str, entity_type: Optional[str]) -> str:
    """Eingabetext der Entitäts-Einbettung — wie in der Ingestion (``f"{name} ({type})"``)."""
    return f"{name} ({entity_type or ''})"


def default_entity_summary(name: str, entity_type: Optional[str]) -> str:
    """Zusammenfassung, die die Ingestion setzt, wenn es keine bessere gibt."""
    return f"{name} ({entity_type})" if entity_type else name


def _load_attributes(props: Dict[str, Any]) -> Dict[str, Any]:
    raw = props.get("attributes_json") or "{}"
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _merge_aliases(*groups: List[str], exclude_name: str) -> List[str]:
    seen = {exclude_name.casefold()}
    out: List[str] = []
    for group in groups:
        for alias in group:
            if isinstance(alias, str) and alias.strip() and alias.casefold() not in seen:
                seen.add(alias.casefold())
                out.append(alias)
    return out


class Neo4jEditMixin:
    """Handänderungen am Graphen. Siehe Modul-Docstring."""

    if TYPE_CHECKING:
        # Vom konkreten Storage bereitgestellte Mixin-Voraussetzungen.
        _embedding: EmbeddingService

        def _get_session(self, **kwargs: Any) -> ContextManager[Session]: ...

        def _call_with_retry[T](self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T: ...

    # ── Hilfen ─────────────────────────────────────────────────────────────

    def edit_property_keys(self) -> Tuple[str, str]:
        """Aktive Property-Namen für Entitäts- und Fakt-Einbettung."""
        index_store = getattr(self, "_embedding_index_store", None)
        if index_store is None:
            index_store = EmbeddingConfigurationStore()
        _entity_index, entity_key = index_store.resolve_active_entity_index()
        _fact_index, fact_key = index_store.resolve_active_fact_index()
        return entity_key, fact_key

    def edit_embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Einbettung über den Embedding-Dienst des Storage (derselbe wie in der Ingestion)."""
        return self._embedding.embed_batch(texts)

    # ── Lesen ──────────────────────────────────────────────────────────────

    def edit_get_entity(self, graph_id: str, entity_uuid: str) -> Optional[Dict[str, Any]]:
        def _read(tx: Any) -> Optional[Dict[str, Any]]:
            record = tx.run(
                "MATCH (n:Entity {graph_id: $gid, uuid: $uuid}) RETURN n, labels(n) AS labels",
                gid=graph_id,
                uuid=entity_uuid,
            ).single()
            if record is None:
                return None
            return node_to_dict(record["n"], record["labels"])

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def edit_get_relation(self, graph_id: str, relation_uuid: str) -> Optional[Dict[str, Any]]:
        def _read(tx: Any) -> Optional[Dict[str, Any]]:
            record = tx.run(
                "MATCH (src:Entity)-[r:RELATION {graph_id: $gid, uuid: $uuid}]->(tgt:Entity) "
                "RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid",
                gid=graph_id,
                uuid=relation_uuid,
            ).single()
            if record is None:
                return None
            return edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])

        with self._get_session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ── Entitäten ──────────────────────────────────────────────────────────

    def edit_create_entity(
        self,
        *,
        graph_id: str,
        entity_uuid: str,
        name: str,
        entity_type: str,
        summary: str,
        aliases: List[str],
        embedding: List[float],
        property_key: str,
        now: str,
    ) -> Tuple[Dict[str, Any], bool]:
        """Legt eine manuelle Entität an. Rückgabe ``(Knoten, neu_angelegt)``.

        ``entity_uuid`` entsteht außerhalb der Transaktion. Ein Retry (oder
        eine Wiederholung mit derselben ``client_request_id``) findet den
        Knoten über die UUID und liefert ihn mit ``neu_angelegt=False``.
        Ein bestehender Knoten mit gleichem (``graph_id``, ``name_lower``,
        ``entity_type``) aber anderer UUID ist eine Kollision.
        """
        merged_aliases = _merge_aliases(aliases, exclude_name=name) if aliases else []
        if merged_aliases:
            attributes = {ALIASES_KEY: merged_aliases}
        else:
            attributes = {}
        safe_label = sanitize_label(entity_type)

        def _create(tx: Any) -> Tuple[Dict[str, Any], bool]:
            existing = tx.run(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n, labels(n) AS labels",
                uuid=entity_uuid,
            ).single()
            if existing is not None:
                props = dict(existing["n"])
                if (
                    props.get("graph_id") == graph_id
                    and str(props.get("name_lower", "")) == name.lower()
                    and props.get("entity_type") == entity_type
                ):
                    return node_to_dict(existing["n"], existing["labels"]), False
                raise GraphEditConflict(
                    "client_request_id wurde bereits für ein anderes Element verwendet"
                )

            # Property-Name stammt aus dem EmbeddingConfigurationStore, nicht
            # aus Nutzereingaben (siehe Modul-Docstring).
            record = tx.run(
                f"""
                MERGE (n:Entity {{graph_id: $gid, name_lower: $name_lower, entity_type: $entity_type}})
                ON CREATE SET
                    n.uuid = $uuid,
                    n.name = $name,
                    n.summary = $summary,
                    n.attributes_json = $attrs_json,
                    n.{property_key} = $embedding,
                    n.created_at = $now,
                    n.origin = '{ORIGIN_MANUAL}',
                    n.origin_changed_at = $now
                RETURN n.uuid AS uuid
                """,
                gid=graph_id,
                name_lower=name.lower(),
                entity_type=entity_type,
                uuid=entity_uuid,
                name=name,
                summary=summary,
                attrs_json=json.dumps(attributes, ensure_ascii=False),
                embedding=embedding,
                now=now,
            ).single()
            if record is None or record["uuid"] != entity_uuid:
                raise GraphEditConflict("Eine Entität mit diesem Namen und Typ existiert bereits")
            if safe_label:
                tx.run(f"MATCH (n:Entity {{uuid: $uuid}}) SET n:`{safe_label}`", uuid=entity_uuid)
            created = tx.run(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n, labels(n) AS labels",
                uuid=entity_uuid,
            ).single()
            return node_to_dict(created["n"], created["labels"]), True

        with self._get_session() as session:
            return self._call_with_retry(session.execute_write, _create)

    def edit_update_entity(
        self,
        *,
        graph_id: str,
        entity_uuid: str,
        name: Optional[str],
        entity_type: Optional[str],
        summary: Optional[str],
        aliases: Optional[List[str]],
        embedding: Optional[List[float]],
        embedding_text: Optional[str],
        property_key: str,
        now: str,
    ) -> Dict[str, Any]:
        """Ändert eine Entität; extrahiert → ``edited``, manuell bleibt ``manual``.

        ``embedding``/``embedding_text`` sind gesetzt, wenn Name oder Typ
        wechseln. Weicht der Text, den die Transaktion aus dem aktuellen
        Stand ableitet, vom übergebenen ab, hat jemand zwischenzeitlich
        geändert: Konflikt statt einer Einbettung zum falschen Text.
        """

        def _update(tx: Any) -> Dict[str, Any]:
            record = tx.run(
                "MATCH (n:Entity {graph_id: $gid, uuid: $uuid}) RETURN n, labels(n) AS labels",
                gid=graph_id,
                uuid=entity_uuid,
            ).single()
            if record is None:
                raise GraphEditNotFound(entity_uuid)
            props = dict(record["n"])
            labels = list(record["labels"])
            current_name = str(props.get("name", ""))
            current_type = effective_entity_type(props, labels)

            new_name = name if name is not None else current_name
            new_type = entity_type if entity_type is not None else current_type
            identity_changed = (
                new_name.casefold() != current_name.casefold() or new_type != current_type
            )
            if identity_changed and new_type is not None:
                clash = tx.run(
                    "MATCH (o:Entity {graph_id: $gid, name_lower: $name_lower, "
                    "entity_type: $entity_type}) WHERE o.uuid <> $uuid "
                    "RETURN o.uuid AS uuid LIMIT 1",
                    gid=graph_id,
                    name_lower=new_name.lower(),
                    entity_type=new_type,
                    uuid=entity_uuid,
                ).single()
                if clash is not None:
                    raise GraphEditConflict(
                        "Eine Entität mit diesem Namen und Typ existiert bereits"
                    )
            if embedding_text is not None and embedding_text != entity_embedding_text(
                new_name, new_type
            ):
                raise GraphEditConflict(
                    "Die Entität wurde zwischenzeitlich geändert, bitte erneut laden"
                )

            sets = [
                f"n.origin = CASE WHEN n.origin = '{ORIGIN_MANUAL}' "
                f"THEN '{ORIGIN_MANUAL}' ELSE '{ORIGIN_EDITED}' END",
                "n.origin_changed_at = $now",
            ]
            params: Dict[str, Any] = {"gid": graph_id, "uuid": entity_uuid, "now": now}
            if name is not None:
                sets += ["n.name = $name", "n.name_lower = $name_lower"]
                params.update(name=name, name_lower=name.lower())
            if entity_type is not None:
                sets.append("n.entity_type = $entity_type")
                params["entity_type"] = entity_type
            if summary is not None:
                sets.append("n.summary = $summary")
                params["summary"] = summary
            if aliases is not None:
                attributes = _load_attributes(props)
                merged = _merge_aliases(aliases, exclude_name=new_name)
                if merged:
                    attributes[ALIASES_KEY] = merged
                    attributes["aliases"] = merged
                else:
                    attributes.pop(ALIASES_KEY, None)
                    attributes.pop("aliases", None)
                    attributes.pop("alias", None)
                sets.append("n.attributes_json = $attrs_json")
                params["attrs_json"] = json.dumps(attributes, ensure_ascii=False)
            if embedding is not None:
                sets.append(f"n.{property_key} = $embedding")
                params["embedding"] = embedding

            tx.run(
                "MATCH (n:Entity {graph_id: $gid, uuid: $uuid}) SET " + ", ".join(sets),
                **params,
            )

            if entity_type is not None and entity_type != current_type:
                old_label = sanitize_label(current_type)
                new_label = sanitize_label(entity_type)
                if old_label:
                    tx.run(
                        f"MATCH (n:Entity {{uuid: $uuid}}) REMOVE n:`{old_label}`",
                        uuid=entity_uuid,
                    )
                if new_label:
                    tx.run(
                        f"MATCH (n:Entity {{uuid: $uuid}}) SET n:`{new_label}`",
                        uuid=entity_uuid,
                    )

            updated = tx.run(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n, labels(n) AS labels",
                uuid=entity_uuid,
            ).single()
            return node_to_dict(updated["n"], updated["labels"])

        with self._get_session() as session:
            return self._call_with_retry(session.execute_write, _update)

    def edit_delete_entity(self, graph_id: str, entity_uuid: str) -> int:
        """Löscht die Entität hart samt ihrer Beziehungen. Rückgabe: Zahl der Beziehungen."""

        def _delete(tx: Any) -> int:
            record = tx.run(
                "MATCH (n:Entity {graph_id: $gid, uuid: $uuid}) "
                "OPTIONAL MATCH (n)-[r:RELATION]-() "
                "RETURN n.uuid AS uuid, count(DISTINCT r) AS relations",
                gid=graph_id,
                uuid=entity_uuid,
            ).single()
            if record is None or record["uuid"] is None:
                raise GraphEditNotFound(entity_uuid)
            tx.run(
                "MATCH (n:Entity {graph_id: $gid, uuid: $uuid}) DETACH DELETE n",
                gid=graph_id,
                uuid=entity_uuid,
            )
            return int(record["relations"])

        with self._get_session() as session:
            return self._call_with_retry(session.execute_write, _delete)

    def edit_merge_entities(
        self,
        *,
        graph_id: str,
        target_uuid: str,
        source_uuids: List[str],
        now: str,
    ) -> Dict[str, Any]:
        """Führt Quell-Entitäten in die Ziel-Entität zusammen.

        Beziehungen der Quellen hängen danach am Ziel (als ``edited``
        markiert), ohne Selbstschleifen und ohne Dubletten gleicher Kante
        (gleiche Richtung, gleicher Gegenpart, gleicher Name). Die Namen und
        Aliase der Quellen werden Aliase des Ziels, die Quellen werden
        gelöscht, das Ziel gilt als ``edited`` (ADR-0022, offener Punkt 1),
        sofern es nicht ``manual`` ist. Alles in einer Transaktion.

        Rückgabe: ``{"node", "merged_source_uuids", "rewired", "dropped"}``.
        """
        ids = [target_uuid, *source_uuids]

        def _merge(tx: Any) -> Dict[str, Any]:
            fetched = tx.run(
                "MATCH (n:Entity {graph_id: $gid}) WHERE n.uuid IN $ids "
                "RETURN n, labels(n) AS labels",
                gid=graph_id,
                ids=ids,
            )
            nodes = {dict(rec["n"]).get("uuid"): dict(rec["n"]) for rec in fetched}
            if target_uuid not in nodes:
                raise GraphEditNotFound(target_uuid)
            missing = [uid for uid in source_uuids if uid not in nodes]
            if missing:
                raise GraphEditNotFound(missing[0])

            edge_rows = list(
                tx.run(
                    "MATCH (a:Entity {graph_id: $gid})-[r:RELATION]->(b:Entity {graph_id: $gid}) "
                    "WHERE a.uuid IN $ids OR b.uuid IN $ids "
                    "RETURN r.uuid AS uuid, a.uuid AS src, b.uuid AS tgt, r.name AS name",
                    gid=graph_id,
                    ids=ids,
                )
            )

            sources = set(source_uuids)

            def _key(src: str, tgt: str, rname: Any) -> Tuple[str, str, str]:
                return (src, tgt, str(rname or "").casefold())

            # Kanten, die das Ziel schon hat und die unverändert bleiben
            seen = {
                _key(row["src"], row["tgt"], row["name"])
                for row in edge_rows
                if row["src"] not in sources and row["tgt"] not in sources
            }
            rewired = 0
            dropped = 0
            for row in edge_rows:
                if row["src"] not in sources and row["tgt"] not in sources:
                    continue
                new_src = target_uuid if row["src"] in sources else row["src"]
                new_tgt = target_uuid if row["tgt"] in sources else row["tgt"]
                key = _key(new_src, new_tgt, row["name"])
                if new_src == new_tgt or key in seen:
                    dropped += 1  # Selbstschleife oder Dublette; fällt mit der Quelle weg
                    continue
                seen.add(key)
                tx.run(
                    "MATCH (:Entity)-[old:RELATION {graph_id: $gid, uuid: $ruuid}]->(:Entity) "
                    "MATCH (s:Entity {graph_id: $gid, uuid: $new_src}) "
                    "MATCH (t:Entity {graph_id: $gid, uuid: $new_tgt}) "
                    "CREATE (s)-[new:RELATION]->(t) "
                    "SET new = properties(old) "
                    "SET new.origin = CASE WHEN old.origin = '" + ORIGIN_MANUAL + "' "
                    "THEN '" + ORIGIN_MANUAL + "' ELSE '" + ORIGIN_EDITED + "' END, "
                    "new.origin_changed_at = $now "
                    "DELETE old",
                    gid=graph_id,
                    ruuid=row["uuid"],
                    new_src=new_src,
                    new_tgt=new_tgt,
                    now=now,
                )
                rewired += 1

            target_props = nodes[target_uuid]
            target_name = str(target_props.get("name", ""))
            attributes = _load_attributes(target_props)
            source_names = [str(nodes[uid].get("name", "")) for uid in source_uuids]
            source_aliases = [
                alias
                for uid in source_uuids
                for alias in (
                    _load_attributes(nodes[uid]).get(ALIASES_KEY)
                    or _load_attributes(nodes[uid]).get("aliases")
                    or _load_attributes(nodes[uid]).get("alias")
                    or []
                )
                if isinstance(alias, str)
            ]
            merged_aliases = _merge_aliases(
                attributes.get(ALIASES_KEY) or attributes.get("aliases") or attributes.get("alias") or [],
                source_names,
                source_aliases,
                exclude_name=target_name,
            )
            if merged_aliases:
                attributes[ALIASES_KEY] = merged_aliases
                attributes["aliases"] = merged_aliases
            else:
                attributes.pop(ALIASES_KEY, None)
                attributes.pop("aliases", None)
                attributes.pop("alias", None)

            tx.run(
                "MATCH (n:Entity {graph_id: $gid}) WHERE n.uuid IN $sources DETACH DELETE n",
                gid=graph_id,
                sources=list(source_uuids),
            )
            tx.run(
                "MATCH (n:Entity {graph_id: $gid, uuid: $uuid}) "
                "SET n.attributes_json = $attrs_json, "
                "n.origin = CASE WHEN n.origin = '" + ORIGIN_MANUAL + "' "
                "THEN '" + ORIGIN_MANUAL + "' ELSE '" + ORIGIN_EDITED + "' END, "
                "n.origin_changed_at = $now",
                gid=graph_id,
                uuid=target_uuid,
                attrs_json=json.dumps(attributes, ensure_ascii=False),
                now=now,
            )
            result = tx.run(
                "MATCH (n:Entity {graph_id: $gid, uuid: $uuid}) RETURN n, labels(n) AS labels",
                gid=graph_id,
                uuid=target_uuid,
            ).single()
            return {
                "node": node_to_dict(result["n"], result["labels"]),
                "merged_source_uuids": list(source_uuids),
                "rewired": rewired,
                "dropped": dropped,
            }

        with self._get_session() as session:
            return self._call_with_retry(session.execute_write, _merge)

    # ── Beziehungen ────────────────────────────────────────────────────────

    def edit_create_relation(
        self,
        *,
        graph_id: str,
        relation_uuid: str,
        source_uuid: str,
        target_uuid: str,
        name: str,
        fact: str,
        embedding: List[float],
        property_key: str,
        now: str,
    ) -> Tuple[Dict[str, Any], bool]:
        """Legt eine manuelle Beziehung an (ohne Episoden). Rückgabe ``(Kante, neu_angelegt)``."""

        def _create(tx: Any) -> Tuple[Dict[str, Any], bool]:
            existing = tx.run(
                "MATCH (src:Entity)-[r:RELATION {uuid: $uuid}]->(tgt:Entity) "
                "RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid",
                uuid=relation_uuid,
            ).single()
            if existing is not None:
                props = dict(existing["r"])
                if (
                    props.get("graph_id") == graph_id
                    and existing["src_uuid"] == source_uuid
                    and existing["tgt_uuid"] == target_uuid
                ):
                    return edge_to_dict(existing["r"], source_uuid, target_uuid), False
                raise GraphEditConflict(
                    "client_request_id wurde bereits für ein anderes Element verwendet"
                )

            record = tx.run(
                f"""
                MATCH (src:Entity {{graph_id: $gid, uuid: $src_uuid}})
                MATCH (tgt:Entity {{graph_id: $gid, uuid: $tgt_uuid}})
                MERGE (src)-[r:RELATION {{uuid: $uuid}}]->(tgt)
                ON CREATE SET
                    r.graph_id = $gid,
                    r.name = $name,
                    r.fact = $fact,
                    r.{property_key} = $embedding,
                    r.attributes_json = '{{}}',
                    r.episode_ids = [],
                    r.created_at = $now,
                    r.valid_at = null,
                    r.invalid_at = null,
                    r.expired_at = null,
                    r.valid_to_round = null,
                    r.reinforced_count = 1,
                    r.origin = '{ORIGIN_MANUAL}',
                    r.origin_changed_at = $now
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid
                """,
                gid=graph_id,
                src_uuid=source_uuid,
                tgt_uuid=target_uuid,
                uuid=relation_uuid,
                name=name,
                fact=fact,
                embedding=embedding,
                now=now,
            ).single()
            if record is None:
                raise GraphEditNotFound("Quelle oder Ziel der Beziehung nicht gefunden")
            return edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"]), True

        with self._get_session() as session:
            return self._call_with_retry(session.execute_write, _create)

    def edit_update_relation(
        self,
        *,
        graph_id: str,
        relation_uuid: str,
        name: Optional[str],
        fact: Optional[str],
        embedding: Optional[List[float]],
        property_key: str,
        now: str,
    ) -> Dict[str, Any]:
        """Ändert Name und/oder Fakt; ``episode_ids`` bleiben unverändert erhalten.

        Extrahiert → ``edited``, manuell bleibt ``manual``. ``embedding`` ist
        gesetzt, wenn sich der Fakt ändert.
        """

        def _update(tx: Any) -> Dict[str, Any]:
            found = tx.run(
                "MATCH (:Entity)-[r:RELATION {graph_id: $gid, uuid: $uuid}]->(:Entity) "
                "RETURN r.uuid AS uuid",
                gid=graph_id,
                uuid=relation_uuid,
            ).single()
            if found is None:
                raise GraphEditNotFound(relation_uuid)

            sets = [
                f"r.origin = CASE WHEN r.origin = '{ORIGIN_MANUAL}' "
                f"THEN '{ORIGIN_MANUAL}' ELSE '{ORIGIN_EDITED}' END",
                "r.origin_changed_at = $now",
            ]
            params: Dict[str, Any] = {"gid": graph_id, "uuid": relation_uuid, "now": now}
            if name is not None:
                sets.append("r.name = $name")
                params["name"] = name
            if fact is not None:
                sets.append("r.fact = $fact")
                params["fact"] = fact
            if embedding is not None:
                sets.append(f"r.{property_key} = $embedding")
                params["embedding"] = embedding

            record = tx.run(
                "MATCH (src:Entity)-[r:RELATION {graph_id: $gid, uuid: $uuid}]->(tgt:Entity) "
                "SET " + ", ".join(sets) + " "
                "RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid",
                **params,
            ).single()
            return edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])

        with self._get_session() as session:
            return self._call_with_retry(session.execute_write, _update)

    def edit_delete_relation(self, graph_id: str, relation_uuid: str) -> None:
        """Löscht eine Beziehung hart (siehe ``GraphEditService`` zur Abweichung vom Tombstone)."""

        def _delete(tx: Any) -> None:
            record = tx.run(
                "MATCH (:Entity)-[r:RELATION {graph_id: $gid, uuid: $uuid}]->(:Entity) "
                "DELETE r RETURN count(r) AS hit",
                gid=graph_id,
                uuid=relation_uuid,
            ).single()
            if record is None or not record["hit"]:
                raise GraphEditNotFound(relation_uuid)

        with self._get_session() as session:
            self._call_with_retry(session.execute_write, _delete)


__all__ = [
    "ALIASES_KEY",
    "GraphEditConflict",
    "GraphEditNotFound",
    "Neo4jEditMixin",
    "default_entity_summary",
    "effective_entity_type",
    "entity_embedding_text",
]
