"""
Neo4jStorage — Neo4j Community Edition implementation of GraphStorage.

Replaces all Zep Cloud API calls with local Neo4j Cypher queries.
Includes: CRUD, NER/RE-based text ingestion, hybrid search, retry logic.
"""

import json
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
from ..services.ingestion_pipeline import (
    embed_entities_and_relations,
    extract_entities_and_relations,
)
from ..utils.retry import neo4j_call_with_retry
from .graph_storage import GraphStorage
from .embedding_service import EmbeddingService
from .ner_extractor import NERExtractor
from .neo4j_mappings import (
    edge_to_dict as _edge_to_dict_func,
    node_to_dict as _node_to_dict_func,
    sanitize_label as _sanitize_label,
)
from .neo4j_read import Neo4jReadMixin
from .search_service import SearchService
from . import neo4j_schema

logger = logging.getLogger('agora.neo4j_storage')


class Neo4jStorage(Neo4jReadMixin, GraphStorage):
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

    # get_ontology lebt jetzt im Neo4jReadMixin (Issue #50, Sub-Slice 1).

    # ----------------------------------------------------------------
    # Add data (NER → nodes/edges)
    # ----------------------------------------------------------------

    def add_text(self, graph_id: str, text: str, round_num: Optional[int] = None) -> str:
        """Process text in three phases — NER, embed, persist.

        Phase 1 (``extract_entities_and_relations``) + Phase 2
        (``embed_entities_and_relations``) leben in
        ``services/ingestion_pipeline.py``; Phase 3 (``_persist_episode``)
        ist storage-nah, weil sie Driver, Cypher und Retry-Logik nutzt.

        ``round_num`` (Issue #10) stamps new RELATION edges with
        ``valid_from_round``. ``None`` keeps the legacy behaviour (property
        absent); ``0`` means "present since the initial ingest"; any positive
        value means the edge was learned during that OASIS round.
        """
        episode_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Phase 1 — NER + Relation-Extraction
        ontology = self.get_ontology(graph_id)
        extraction = extract_entities_and_relations(self._ner, text, ontology)
        entities = extraction.get("entities", [])
        relations = extraction.get("relations", [])

        # Issue #11 Phase 2 — propose ontology mutations for any entity types
        # the LLM emitted that the current ontology does not cover. The
        # service decides per-mode whether to log, queue or auto-apply.
        self._evaluate_ontology_mutations(graph_id, ontology, entities, text)

        # Phase 2 — Batch-Embedding
        entity_embeddings, relation_embeddings = embed_entities_and_relations(
            self._embedding, entities, relations
        )

        # Phase 3 — Persist (Episode-Node, Entities, Relations)
        logger.info("[add_text] Embedding done, writing to Neo4j...")
        self._persist_episode(
            graph_id=graph_id,
            episode_id=episode_id,
            text=text,
            now=now,
            entities=entities,
            relations=relations,
            entity_embeddings=entity_embeddings,
            relation_embeddings=relation_embeddings,
            round_num=round_num,
        )

        logger.info(f"[add_text] Chunk done: episode={episode_id}")
        return episode_id

    def _persist_episode(
        self,
        *,
        graph_id: str,
        episode_id: str,
        text: str,
        now: str,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
        entity_embeddings: List[List[float]],
        relation_embeddings: List[List[float]],
        round_num: Optional[int],
    ) -> None:
        """Phase 3 — Persistiert Episode-Node, Entities und Relations in Neo4j.

        Storage-intern (Cypher + Driver + Retry); separat von Phase 1/2,
        weil reine Funktionen kein Neo4j-Coupling haben sollen.
        """
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
                summary_text = f"{ename} ({etype})"
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
    # Read-Pfad (get_all_nodes, get_node, get_node_edges, get_nodes_by_label,
    # get_filtered_entities_with_edges, get_all_edges, get_edges_at_round)
    # lebt jetzt im Neo4jReadMixin (Issue #50, Sub-Slice 1).
    # ----------------------------------------------------------------

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
    # get_graph_info, get_graph_data + Dict-Konversion (_node_to_dict /
    # _edge_to_dict) leben jetzt im Neo4jReadMixin bzw. in
    # storage/neo4j_mappings.py (Issue #50, Sub-Slice 1).
    # ----------------------------------------------------------------

    # Re-Export der Mapping-Funktionen als statische Methoden, falls
    # Subklassen oder externer Code historisch über die Klasse zugriff
    # (laut grep keine Caller, aber die Wire-Identity bleibt damit billig).
    _node_to_dict = staticmethod(_node_to_dict_func)
    _edge_to_dict = staticmethod(_edge_to_dict_func)
