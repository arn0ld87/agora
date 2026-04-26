"""
Neo4jStorage — Neo4j Community Edition implementation of GraphStorage.

Replaces all Zep Cloud API calls with local Neo4j Cypher queries.
Includes: CRUD, NER/RE-based text ingestion, hybrid search, retry logic.
"""

import json
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from neo4j import GraphDatabase
from neo4j.exceptions import (
    TransientError,
    ServiceUnavailable,
    SessionExpired,
)

from ..config import Config
from ..utils.retry import neo4j_call_with_retry
from .graph_storage import GraphStorage
from .embedding_service import EmbeddingService
from .ner_extractor import NERExtractor
from .search_service import SearchService
from . import neo4j_schema

logger = logging.getLogger('agora.neo4j_storage')

# Cypher erlaubt Labels nur als Identifier, nicht als Parameter. Labels kommen
# hier aus LLM-Output (Entity-Type aus NER) — ohne Filter liefert das einen
# f-string-Injection-Vektor (Backticks im Namen brechen aus dem Quoting aus).
# Whitelist-Regex: Buchstabe/Underscore-Start, dann A-Za-z0-9_, max 50 Zeichen.
_LABEL_SAFE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,49}$')


def _sanitize_label(value: Any) -> Optional[str]:
    """Return a Cypher-safe label or ``None`` when the input is unusable."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped == 'Entity':
        return None
    # Häufige LLM-Verwüstungen aufräumen: Leerzeichen zu Underscore,
    # Umlaute weg (Neo4j-Labels sind ASCII-praktisch nur dann lesbar).
    normalized = re.sub(r'\s+', '_', stripped)
    normalized = re.sub(r'[^A-Za-z0-9_]', '', normalized)
    if not _LABEL_SAFE_RE.match(normalized):
        return None
    return normalized


class Neo4jStorage(GraphStorage):
    """Neo4j CE implementation of the GraphStorage interface."""

    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0  # seconds (initial backoff)

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
        ner_extractor: Optional[NERExtractor] = None,
    ):
        self._uri = uri or Config.NEO4J_URI
        self._user = user or Config.NEO4J_USER
        self._password = password or Config.NEO4J_PASSWORD

        self._driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )
        self._embedding = embedding_service or EmbeddingService()
        self._ner = ner_extractor or NERExtractor()
        self._search = SearchService(
            self._embedding,
            vector_weight=Config.HYBRID_SEARCH_VECTOR_WEIGHT,
            keyword_weight=Config.HYBRID_SEARCH_KEYWORD_WEIGHT,
        )

        # Issue #11 Phase 2 — late-bound to avoid the
        # OntologyManager → Neo4jStorage circular dependency.
        # Container injects via :meth:`set_ontology_mutation_service` after
        # the manager is built. ``None`` means the hook is a no-op.
        self._ontology_mutation_service = None

        # Health-state tracking (exposed via properties for /api/status)
        self._is_connected: bool = True
        self._last_error: Optional[Exception] = None
        self._last_success_ts: Optional[datetime] = None

        # Fail fast when Neo4j is not reachable so Flask can expose a clean
        # "storage unavailable" state instead of spamming one warning per schema query.
        self._verify_connectivity()

        # Initialize schema (indexes, constraints)
        self._ensure_schema()

    def close(self):
        """Close the Neo4j driver connection."""
        self._driver.close()

    def set_ontology_mutation_service(self, service) -> None:
        """Late-bind the Issue #11 ``OntologyMutationService``.

        The container wires this *after* construction because the service
        depends on ``OntologyManager``, which itself holds a reference to
        this storage — direct constructor injection would deadlock the DI
        graph. Pass ``None`` to disable the hook again.
        """
        self._ontology_mutation_service = service

    def _evaluate_ontology_mutations(
        self,
        graph_id: str,
        ontology: Dict[str, Any],
        entities: List[Dict[str, Any]],
        text: str,
    ) -> None:
        """Forward novel entity types to the OntologyMutationService.

        Filters NER output against the graph's current ``entity_types`` and
        passes anything unknown through to the service. Failures are logged
        and swallowed — ontology mutation is best-effort and must never
        block ingestion.
        """
        service = self._ontology_mutation_service
        if service is None or not entities:
            return
        # Don't even build the candidate list if the service is disabled.
        if getattr(service, "mode", None) == "disabled":
            return

        known_types = {
            (t.get("name") if isinstance(t, dict) else t)
            for t in (ontology.get("entity_types") or [])
        }
        known_types.discard(None)

        novel: List[Dict[str, str]] = []
        seen_types: set = set()
        for ent in entities:
            etype = (ent.get("type") or "").strip()
            if not etype or etype in known_types or etype in seen_types:
                continue
            seen_types.add(etype)
            novel.append({
                "type": etype,
                "name": ent.get("name", ""),
                "context": text[:200],
            })

        if not novel:
            return

        try:
            service.evaluate_batch(graph_id, novel)
        except Exception as exc:  # noqa: BLE001 — best-effort hook
            logger.warning(
                "Ontology mutation evaluation failed (graph=%s, novel=%d): %s",
                graph_id, len(novel), exc,
            )

    def _verify_connectivity(self):
        """Ensure the driver can actually reach Neo4j."""
        try:
            self._driver.verify_connectivity()
        except Exception:
            try:
                self._driver.close()
            except Exception:
                pass
            raise

    def _ensure_schema(self):
        """Create indexes and constraints if they don't exist."""
        with self._driver.session() as session:
            for query in neo4j_schema.ALL_SCHEMA_QUERIES:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"Schema query warning: {e}")

    # ----------------------------------------------------------------
    # Health-status properties
    # ----------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True when the last DB operation succeeded; False after a permanent failure."""
        return self._is_connected

    @property
    def last_error(self) -> Optional[Exception]:
        """The exception that caused the most recent permanent failure, or None."""
        return self._last_error

    @property
    def last_success_ts(self) -> Optional[datetime]:
        """Timestamp (UTC) of the most recent successful DB call, or None."""
        return self._last_success_ts

    # ----------------------------------------------------------------
    # Retry wrapper
    # ----------------------------------------------------------------

    def _call_with_retry(self, func, *args, **kwargs):
        """
        Execute *func* with exponential-backoff retry on Neo4j transient errors.

        Delegates to ``neo4j_call_with_retry`` from ``utils.retry`` (shared
        mechanism — no parallel retry implementations).  Updates the health
        state (``is_connected``, ``last_error``, ``last_success_ts``) so
        callers and the future /api/status endpoint can inspect it.
        """
        try:
            result = neo4j_call_with_retry(
                func,
                *args,
                max_retries=self.MAX_RETRIES,
                initial_delay=self.RETRY_DELAY_BASE,
                **kwargs,
            )
            # Success — record health state
            self._is_connected = True
            self._last_error = None
            self._last_success_ts = datetime.now(timezone.utc)
            return result
        except (TransientError, ServiceUnavailable, SessionExpired) as exc:
            # Retries exhausted — record failure state and re-raise
            self._is_connected = False
            self._last_error = exc
            raise

    # ----------------------------------------------------------------
    # Graph lifecycle
    # ----------------------------------------------------------------

    def create_graph(self, name: str, description: str = "") -> str:
        graph_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        def _create(tx):
            tx.run(
                """
                CREATE (g:Graph {
                    graph_id: $graph_id,
                    name: $name,
                    description: $description,
                    ontology_json: '{}',
                    created_at: $created_at
                })
                """,
                graph_id=graph_id,
                name=name,
                description=description,
                created_at=now,
            )

        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _create)

        logger.info(f"Created graph '{name}' with id {graph_id}")
        return graph_id

    def delete_graph(self, graph_id: str) -> None:
        def _delete(tx):
            # Delete all entities and their relationships
            tx.run(
                "MATCH (n {graph_id: $gid}) DETACH DELETE n",
                gid=graph_id,
            )
            # Delete graph node
            tx.run(
                "MATCH (g:Graph {graph_id: $gid}) DELETE g",
                gid=graph_id,
            )

        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _delete)
        logger.info(f"Deleted graph {graph_id}")

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        def _set(tx):
            tx.run(
                """
                MATCH (g:Graph {graph_id: $gid})
                SET g.ontology_json = $ontology_json
                """,
                gid=graph_id,
                ontology_json=json.dumps(ontology, ensure_ascii=False),
            )

        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _set)

    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        def _read(tx):
            result = tx.run(
                "MATCH (g:Graph {graph_id: $gid}) RETURN g.ontology_json AS oj",
                gid=graph_id,
            )
            record = result.single()
            if record and record["oj"]:
                return json.loads(record["oj"])
            return {}

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ----------------------------------------------------------------
    # Add data (NER → nodes/edges)
    # ----------------------------------------------------------------

    def add_text(self, graph_id: str, text: str, round_num: Optional[int] = None) -> str:
        """Process text: NER/RE → batch embed → create nodes/edges → return episode_id.

        ``round_num`` (Issue #10) stamps new RELATION edges with
        ``valid_from_round``. ``None`` keeps the legacy behaviour (property
        absent); ``0`` means "present since the initial ingest"; any positive
        value means the edge was learned during that OASIS round.
        """
        episode_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Get ontology for NER guidance
        ontology = self.get_ontology(graph_id)

        # Extract entities and relations
        logger.info(f"[add_text] Starting NER extraction for chunk ({len(text)} chars)...")
        extraction = self._ner.extract(text, ontology)
        entities = extraction.get("entities", [])
        relations = extraction.get("relations", [])

        logger.info(
            f"[add_text] NER done: {len(entities)} entities, {len(relations)} relations"
        )

        # Issue #11 Phase 2 — propose ontology mutations for any entity types
        # the LLM emitted that the current ontology does not cover. The
        # service decides per-mode whether to log, queue or auto-apply.
        self._evaluate_ontology_mutations(graph_id, ontology, entities, text)

        # --- Batch embed all texts at once ---
        entity_summaries = [f"{e['name']} ({e['type']})" for e in entities]
        fact_texts = [r.get("fact", f"{r['source']} {r['type']} {r['target']}") for r in relations]
        all_texts_to_embed = entity_summaries + fact_texts

        all_embeddings: list = []
        if all_texts_to_embed:
            logger.info(f"[add_text] Batch-embedding {len(all_texts_to_embed)} texts...")
            try:
                all_embeddings = self._embedding.embed_batch(all_texts_to_embed)
            except Exception as e:
                logger.warning(f"[add_text] Batch embedding failed, falling back to empty: {e}")
                all_embeddings = [[] for _ in all_texts_to_embed]

        entity_embeddings = all_embeddings[:len(entities)]
        relation_embeddings = all_embeddings[len(entities):]
        logger.info("[add_text] Embedding done, writing to Neo4j...")

        with self._driver.session() as session:
            # Create episode node
            def _create_episode(tx):
                tx.run(
                    """
                    CREATE (ep:Episode {
                        uuid: $uuid,
                        graph_id: $graph_id,
                        data: $data,
                        processed: true,
                        created_at: $created_at
                    })
                    """,
                    uuid=episode_id,
                    graph_id=graph_id,
                    data=text,
                    created_at=now,
                )

            self._call_with_retry(session.execute_write, _create_episode)

            # MERGE entities (upsert by graph_id + name + primary label)
            entity_uuid_map: Dict[str, str] = {}  # name_lower -> uuid
            for idx, entity in enumerate(entities):
                ename = entity["name"]
                etype = entity["type"]
                attrs = entity.get("attributes", {})
                summary_text = entity_summaries[idx]
                embedding = entity_embeddings[idx] if idx < len(entity_embeddings) else []

                e_uuid = str(uuid.uuid4())
                entity_uuid_map[ename.lower()] = e_uuid

                def _merge_entity(tx, _uuid=e_uuid, _name=ename, _type=etype,
                                  _attrs=attrs, _embedding=embedding,
                                  _summary=summary_text, _now=now):
                    # MERGE by graph_id + lowercase name to deduplicate
                    result = tx.run(
                        """
                        MERGE (n:Entity {graph_id: $gid, name_lower: $name_lower})
                        ON CREATE SET
                            n.uuid = $uuid,
                            n.name = $name,
                            n.summary = $summary,
                            n.attributes_json = $attrs_json,
                            n.embedding = $embedding,
                            n.created_at = $now
                        ON MATCH SET
                            n.summary = CASE WHEN n.summary = '' OR n.summary IS NULL
                                THEN $summary ELSE n.summary END,
                            n.attributes_json = $attrs_json,
                            n.embedding = $embedding
                        RETURN n.uuid AS uuid
                        """,
                        gid=graph_id,
                        name_lower=_name.lower(),
                        uuid=_uuid,
                        name=_name,
                        summary=_summary,
                        attrs_json=json.dumps(_attrs, ensure_ascii=False),
                        embedding=_embedding,
                        now=_now,
                    )
                    record = result.single()
                    return record["uuid"] if record else _uuid

                actual_uuid = self._call_with_retry(session.execute_write, _merge_entity)
                entity_uuid_map[ename.lower()] = actual_uuid

                # Add entity type label. Labels werden durch _sanitize_label
                # auf einen sicheren Identifier beschränkt — LLM-Output kann
                # sonst aus dem Backtick-Quoting ausbrechen.
                safe_label = _sanitize_label(etype)
                if safe_label:
                    try:
                        def _add_label(tx, _name_lower=ename.lower(), _label=safe_label):
                            tx.run(
                                f"MATCH (n:Entity {{graph_id: $gid, name_lower: $nl}}) SET n:`{_label}`",
                                gid=graph_id,
                                nl=_name_lower,
                            )
                        self._call_with_retry(session.execute_write, _add_label)
                    except Exception as e:
                        logger.warning(f"Failed to add label '{safe_label}' to '{ename}': {e}")
                elif etype and etype != "Entity":
                    logger.debug(f"Discarded unsafe entity label {etype!r} for '{ename}'")

            # Create relations
            for idx, relation in enumerate(relations):
                source_name = relation["source"]
                target_name = relation["target"]
                rtype = relation["type"]
                fact = relation["fact"]

                source_uuid = entity_uuid_map.get(source_name.lower())
                target_uuid = entity_uuid_map.get(target_name.lower())

                if not source_uuid or not target_uuid:
                    logger.warning(
                        f"Skipping relation {source_name}->{target_name}: "
                        f"entity not found in extraction results"
                    )
                    continue

                fact_embedding = relation_embeddings[idx] if idx < len(relation_embeddings) else []
                r_uuid = str(uuid.uuid4())

                def _create_relation(tx, _r_uuid=r_uuid, _source_uuid=source_uuid,
                                     _target_uuid=target_uuid, _rtype=rtype,
                                     _fact=fact, _fact_emb=fact_embedding,
                                     _episode_id=episode_id, _now=now,
                                     _round=round_num):
                    tx.run(
                        """
                        MATCH (src:Entity {uuid: $src_uuid})
                        MATCH (tgt:Entity {uuid: $tgt_uuid})
                        CREATE (src)-[r:RELATION {
                            uuid: $uuid,
                            graph_id: $gid,
                            name: $name,
                            fact: $fact,
                            fact_embedding: $fact_embedding,
                            attributes_json: '{}',
                            episode_ids: [$episode_id],
                            created_at: $now,
                            valid_at: null,
                            invalid_at: null,
                            expired_at: null,
                            valid_from_round: $round,
                            valid_to_round: null,
                            reinforced_count: 1
                        }]->(tgt)
                        """,
                        src_uuid=_source_uuid,
                        tgt_uuid=_target_uuid,
                        uuid=_r_uuid,
                        gid=graph_id,
                        name=_rtype,
                        fact=_fact,
                        fact_embedding=_fact_emb,
                        episode_id=_episode_id,
                        now=_now,
                        round=_round,
                    )

                self._call_with_retry(session.execute_write, _create_relation)

        logger.info(f"[add_text] Chunk done: episode={episode_id}")
        return episode_id

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
        round_num: Optional[int] = None,
    ) -> List[str]:
        """Batch-add text chunks with progress reporting."""
        episode_ids = []
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            if not chunk or not chunk.strip():
                continue
            episode_id = self.add_text(graph_id, chunk, round_num=round_num)
            episode_ids.append(episode_id)

            if progress_callback:
                progress = (i + 1) / total
                progress_callback(progress)

            logger.info(f"Processed chunk {i + 1}/{total}")

        return episode_ids

    def wait_for_processing(
        self,
        episode_ids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600,
    ) -> None:
        """No-op — processing is synchronous in Neo4j."""
        if progress_callback:
            progress_callback(1.0)

    # ----------------------------------------------------------------
    # Read nodes
    # ----------------------------------------------------------------

    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                RETURN n, labels(n) AS labels
                ORDER BY n.created_at DESC
                LIMIT $limit
                """,
                gid=graph_id,
                limit=limit,
            )
            return [self._node_to_dict(record["n"], record["labels"]) for record in result]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_node(self, uuid: str) -> Optional[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n, labels(n) AS labels",
                uuid=uuid,
            )
            record = result.single()
            if record:
                return self._node_to_dict(record["n"], record["labels"])
            return None

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """O(1) Cypher — NOT full scan + filter like the old Zep code."""
        def _read(tx):
            result = tx.run(
                """
                MATCH (n:Entity {uuid: $uuid})-[r:RELATION]-(m:Entity)
                RETURN r, startNode(r).uuid AS src_uuid, endNode(r).uuid AS tgt_uuid
                """,
                uuid=node_uuid,
            )
            return [
                self._edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_nodes_by_label(self, graph_id: str, label: str) -> List[Dict[str, Any]]:
        # Sanitize label to prevent Cypher injection
        safe_label = _sanitize_label(label)

        if not safe_label:
            return []

        def _read(tx):
            # Dynamic label in query (now sanitized)
            query = f"""
                MATCH (n:Entity:`{safe_label}` {{graph_id: $gid}})
                RETURN n, labels(n) AS labels
            """
            result = tx.run(query, gid=graph_id)
            return [self._node_to_dict(record["n"], record["labels"]) for record in result]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_filtered_entities_with_edges(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> Dict[str, Any]:
        # Normalise the type whitelist: empty list → no filter (consistent with
        # the old in-memory version, which treated ``None`` and ``[]`` the same).
        types_param: Optional[List[str]] = (
            list(defined_entity_types) if defined_entity_types else None
        )

        def _read(tx):
            # Baseline count: every Entity node, including ones that only carry
            # the default label. Needed for the ``total_count`` accounting that
            # callers expose as filter ratio.
            total_result = tx.run(
                "MATCH (n:Entity {graph_id: $gid}) RETURN count(n) AS cnt",
                gid=graph_id,
            )
            total_count = total_result.single()["cnt"]

            if enrich_with_edges:
                query = """
                    MATCH (n:Entity {graph_id: $gid})
                    WITH n, [l IN labels(n) WHERE l <> 'Entity' AND l <> 'Node']
                             AS custom_labels
                    WHERE size(custom_labels) > 0
                      AND ($types IS NULL
                           OR any(l IN custom_labels WHERE l IN $types))
                    OPTIONAL MATCH (n)-[r:RELATION {graph_id: $gid}]-(m:Entity)
                    WITH n, labels(n) AS node_labels,
                         collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
                             edge_name: coalesce(r.name, ''),
                             fact: coalesce(r.fact, ''),
                             source_node_uuid: startNode(r).uuid,
                             target_node_uuid: endNode(r).uuid
                         } END) AS raw_edges,
                         collect(DISTINCT CASE WHEN m IS NOT NULL THEN {
                             uuid: m.uuid,
                             name: coalesce(m.name, ''),
                             labels: [l IN labels(m) WHERE l <> 'Entity'],
                             summary: coalesce(m.summary, '')
                         } END) AS raw_related
                    RETURN n, node_labels, raw_edges, raw_related
                """
                records = tx.run(query, gid=graph_id, types=types_param)
                return total_count, [
                    (
                        record["n"],
                        record["node_labels"],
                        list(record["raw_edges"] or []),
                        list(record["raw_related"] or []),
                    )
                    for record in records
                ]

            query = """
                MATCH (n:Entity {graph_id: $gid})
                WITH n, [l IN labels(n) WHERE l <> 'Entity' AND l <> 'Node']
                         AS custom_labels
                WHERE size(custom_labels) > 0
                  AND ($types IS NULL
                       OR any(l IN custom_labels WHERE l IN $types))
                RETURN n, labels(n) AS node_labels
            """
            records = tx.run(query, gid=graph_id, types=types_param)
            return total_count, [
                (record["n"], record["node_labels"], [], [])
                for record in records
            ]

        with self._driver.session() as session:
            total_count, rows = self._call_with_retry(session.execute_read, _read)

        entities: List[Dict[str, Any]] = []
        for node, node_labels, raw_edges, raw_related in rows:
            node_dict = self._node_to_dict(node, node_labels)
            entity_uuid = node_dict["uuid"]

            related_edges: List[Dict[str, Any]] = []
            for edge in raw_edges:
                # ``collect(DISTINCT CASE ... END)`` drops NULL entries in
                # Cypher but can still yield empty maps on some driver
                # versions — defensive check.
                if not edge:
                    continue
                source_uuid = edge.get("source_node_uuid")
                target_uuid = edge.get("target_node_uuid")
                if source_uuid == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge.get("edge_name", ""),
                        "fact": edge.get("fact", ""),
                        "target_node_uuid": target_uuid,
                    })
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge.get("edge_name", ""),
                        "fact": edge.get("fact", ""),
                        "source_node_uuid": source_uuid,
                    })

            related_nodes: List[Dict[str, Any]] = []
            seen_related: set = set()
            for rel in raw_related:
                if not rel:
                    continue
                rel_uuid = rel.get("uuid")
                if not rel_uuid or rel_uuid in seen_related:
                    continue
                seen_related.add(rel_uuid)
                related_nodes.append({
                    "uuid": rel_uuid,
                    "name": rel.get("name", ""),
                    "labels": list(rel.get("labels") or []),
                    "summary": rel.get("summary", ""),
                })

            node_dict["related_edges"] = related_edges
            node_dict["related_nodes"] = related_nodes
            entities.append(node_dict)

        return {
            "entities": entities,
            "total_count": total_count,
        }

    # ----------------------------------------------------------------
    # Read edges
    # ----------------------------------------------------------------

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid
                ORDER BY r.created_at DESC
                """,
                gid=graph_id,
            )
            return [
                self._edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ----------------------------------------------------------------
    # Temporal edges (Issue #10)
    # ----------------------------------------------------------------

    def get_edges_at_round(
        self, graph_id: str, round_num: int
    ) -> List[Dict[str, Any]]:
        """Return edges that were valid at the given OASIS round.

        An edge is "valid" at round R if:
          (valid_from_round IS NULL OR valid_from_round <= R)
          AND (valid_to_round IS NULL OR valid_to_round > R)

        Missing ``valid_from_round`` is treated as 0 (present since ingest).
        Missing ``valid_to_round`` is treated as open-ended.
        """

        def _read(tx):
            result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                WHERE coalesce(r.valid_from_round, 0) <= $round
                  AND (r.valid_to_round IS NULL OR r.valid_to_round > $round)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid
                ORDER BY r.created_at DESC
                """,
                gid=graph_id,
                round=round_num,
            )
            return [
                self._edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def reinforce_relation(
        self,
        graph_id: str,
        source_uuid: str,
        target_uuid: str,
        rtype: str,
        round_num: int,
    ) -> Optional[Dict[str, Any]]:
        """Bump ``reinforced_count`` on an existing RELATION.

        Looks up an edge matching (graph_id, src, tgt, name=rtype). Returns
        the updated edge dict, or ``None`` when no matching edge exists.
        Callers should fall back to ``add_text`` when ``None`` is returned.
        """

        def _write(tx):
            result = tx.run(
                """
                MATCH (src:Entity {uuid: $src})-[r:RELATION {graph_id: $gid, name: $name}]->(tgt:Entity {uuid: $tgt})
                WITH r, src, tgt
                ORDER BY coalesce(r.reinforced_count, 1) DESC
                LIMIT 1
                SET r.reinforced_count = coalesce(r.reinforced_count, 1) + 1
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid
                """,
                gid=graph_id,
                src=source_uuid,
                tgt=target_uuid,
                name=rtype,
            )
            record = result.single()
            if not record:
                return None
            return self._edge_to_dict(
                record["r"], record["src_uuid"], record["tgt_uuid"]
            )

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_write, _write)

    def tombstone_relation(
        self,
        graph_id: str,
        relation_uuid: str,
        round_num: int,
    ) -> bool:
        """Mark a RELATION as no longer valid at round ``round_num``.

        Sets ``valid_to_round`` to the given round. Returns True if a
        matching edge was found.
        """

        def _write(tx):
            result = tx.run(
                """
                MATCH ()-[r:RELATION {graph_id: $gid, uuid: $uuid}]->()
                SET r.valid_to_round = $round
                RETURN count(r) AS hit
                """,
                gid=graph_id,
                uuid=relation_uuid,
                round=round_num,
            )
            record = result.single()
            return bool(record and record["hit"])

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_write, _write)

    def backfill_temporal_defaults(self, graph_id: Optional[str] = None) -> int:
        """One-shot migration: stamp pre-#10 edges with ``valid_from_round=0``.

        Called from the temporal service on first use per graph; idempotent
        — sets properties only where they are missing. Returns the number
        of edges touched.
        """

        def _write(tx):
            if graph_id:
                result = tx.run(
                    """
                    MATCH ()-[r:RELATION {graph_id: $gid}]->()
                    WHERE r.valid_from_round IS NULL
                    SET r.valid_from_round = 0,
                        r.reinforced_count = coalesce(r.reinforced_count, 1)
                    RETURN count(r) AS touched
                    """,
                    gid=graph_id,
                )
            else:
                result = tx.run(
                    """
                    MATCH ()-[r:RELATION]->()
                    WHERE r.valid_from_round IS NULL
                    SET r.valid_from_round = 0,
                        r.reinforced_count = coalesce(r.reinforced_count, 1)
                    RETURN count(r) AS touched
                    """
                )
            record = result.single()
            return int(record["touched"]) if record else 0

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_write, _write)

    # ----------------------------------------------------------------
    # Search
    # ----------------------------------------------------------------

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ):
        """
        Hybrid search — returns results matching the scope.

        Returns a dict with 'edges' and/or 'nodes' lists
        (callers like zep_tools will wrap into SearchResult).

        The entire session block is wrapped in ``_call_with_retry`` so a
        transient connection error mid-search causes a clean retry rather
        than a half-filled result being returned.
        """
        result: Dict[str, Any] = {"edges": [], "nodes": [], "query": query}

        def _do_search():
            with self._driver.session() as session:
                if scope in ("edges", "both"):
                    result["edges"] = self._search.search_edges(
                        session, graph_id, query, limit
                    )
                if scope in ("nodes", "both"):
                    result["nodes"] = self._search.search_nodes(
                        session, graph_id, query, limit
                    )

        self._call_with_retry(_do_search)
        return result

    # ----------------------------------------------------------------
    # Graph info
    # ----------------------------------------------------------------

    def get_graph_info(self, graph_id: str) -> Dict[str, Any]:
        def _read(tx):
            # Count nodes
            node_result = tx.run(
                "MATCH (n:Entity {graph_id: $gid}) RETURN count(n) AS cnt",
                gid=graph_id,
            )
            node_count = node_result.single()["cnt"]

            # Count edges
            edge_result = tx.run(
                "MATCH ()-[r:RELATION {graph_id: $gid}]->() RETURN count(r) AS cnt",
                gid=graph_id,
            )
            edge_count = edge_result.single()["cnt"]

            # Distinct entity types
            label_result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                UNWIND labels(n) AS lbl
                WITH lbl WHERE lbl <> 'Entity'
                RETURN DISTINCT lbl
                """,
                gid=graph_id,
            )
            entity_types = [record["lbl"] for record in label_result]

            return {
                "graph_id": graph_id,
                "node_count": node_count,
                "edge_count": edge_count,
                "entity_types": entity_types,
            }

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Full graph dump with enriched edge format (for frontend).
        Includes derived fields: fact_type, source_node_name, target_node_name.
        """
        def _read(tx):
            # Get all nodes
            node_result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                RETURN n, labels(n) AS labels
                """,
                gid=graph_id,
            )
            nodes = []
            node_map: Dict[str, str] = {}  # uuid -> name
            for record in node_result:
                nd = self._node_to_dict(record["n"], record["labels"])
                nodes.append(nd)
                node_map[nd["uuid"]] = nd["name"]

            # Get all edges with source/target node names (JOIN)
            edge_result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid,
                       src.name AS src_name, tgt.name AS tgt_name
                """,
                gid=graph_id,
            )
            edges = []
            for record in edge_result:
                ed = self._edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                # Enriched fields for frontend
                ed["fact_type"] = ed["name"]
                ed["source_node_name"] = record["src_name"] or ""
                ed["target_node_name"] = record["tgt_name"] or ""
                # Legacy alias
                ed["episodes"] = ed.get("episode_ids", [])
                edges.append(ed)

            return {
                "graph_id": graph_id,
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ----------------------------------------------------------------
    # Dict conversion helpers
    # ----------------------------------------------------------------

    @staticmethod
    def _node_to_dict(node, labels: List[str]) -> Dict[str, Any]:
        """Convert Neo4j node to the standard node dict format."""
        props = dict(node)
        attrs_json = props.pop("attributes_json", "{}")
        try:
            attributes = json.loads(attrs_json) if attrs_json else {}
        except (json.JSONDecodeError, TypeError):
            attributes = {}

        # Remove internal fields from dict
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

    @staticmethod
    def _edge_to_dict(rel, source_uuid: str, target_uuid: str) -> Dict[str, Any]:
        """Convert Neo4j relationship to the standard edge dict format."""
        props = dict(rel)
        attrs_json = props.pop("attributes_json", "{}")
        try:
            attributes = json.loads(attrs_json) if attrs_json else {}
        except (json.JSONDecodeError, TypeError):
            attributes = {}

        # Remove internal fields
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
