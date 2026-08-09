"""
Write-Pfad für ``Neo4jStorage``.

Issue #50 (EPIC-08-ST-01), Sub-Slice 2/3: ``Neo4jWriteMixin`` bündelt
alle mutierenden Methoden (``create_graph``, ``delete_graph``,
``set_ontology``, ``add_text`` Orchestrator, ``_persist_episode``
Phase 3, ``add_text_batch``, ``wait_for_processing``,
``reinforce_relation``, ``tombstone_relation``,
``backfill_temporal_defaults``) plus den Best-Effort-Helfer
``_evaluate_ontology_mutations``.

Mixin-Voraussetzungen am konkreten Storage:

- ``self._driver`` — Neo4j-Driver mit ``.session()``
- ``self._call_with_retry`` — Retry-Wrapper
- ``self._ner`` — NER-Service (für ``add_text``)
- ``self._embedding`` — Embedding-Service (für ``add_text``)
- ``self._ontology_mutation_service`` — kann ``None`` sein
- ``self.get_ontology`` — vom ``Neo4jReadMixin``
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..services.ingestion_pipeline import (
    embed_entities_and_relations,
    extract_entities_and_relations,
)
from .neo4j_mappings import edge_to_dict, sanitize_label

if TYPE_CHECKING:
    from ..services.degradation_collector import (
        ChunkExtractionTally,
        DegradationCollector,
    )
    from .ner_extractor import NERExtractor

logger = logging.getLogger("agora.neo4j_storage")


def _canonical_entity_type(entity_dict: dict) -> str:
    """Return the canonical entity-type string for use in the MERGE identity key.

    Probes ``entity_type``, then ``type``, then ``label`` — takes the first
    non-empty value.  Falls back to ``"unknown"`` so that the MERGE key is
    always fully populated even when NER output omits the type field.
    """
    for field in ("entity_type", "type", "label"):
        val = entity_dict.get(field)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return "unknown"


class Neo4jWriteMixin:
    """Write-Pfad für ``Neo4jStorage``. Siehe Modul-Docstring."""

    # ── Ontology mutation helper ────────────────────────────────────

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

    # ── Graph lifecycle ─────────────────────────────────────────────

    def create_graph(self, name: str, description: str = "") -> str:
        graph_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        def _create(tx):
            tx.run(
                """
                MERGE (g:Graph {graph_id: $graph_id})
                ON CREATE SET
                    g.name = $name,
                    g.description = $description,
                    g.ontology_json = '{}',
                    g.created_at = $created_at,
                    g.status = 'building'
                """,
                graph_id=graph_id,
                name=name,
                description=description,
                created_at=now,
            )

        with self._get_session() as session:
            self._call_with_retry(session.execute_write, _create)

        logger.info(f"Created graph '{name}' with id {graph_id}")
        return graph_id

    def mark_graph_completed(self, graph_id: str) -> None:
        """Set graph status to 'completed' after a successful build."""

        def _mark(tx):
            tx.run(
                "MATCH (g:Graph {graph_id: $gid}) SET g.status = 'completed'",
                gid=graph_id,
            )

        with self._get_session() as session:
            self._call_with_retry(session.execute_write, _mark)
        logger.info("Graph %s marked as completed", graph_id)

    def mark_graph_failed(self, graph_id: str, reason: Optional[str] = None) -> None:
        """Set graph status to 'failed'.  Optionally records a failure_reason."""

        def _mark(tx):
            tx.run(
                """
                MATCH (g:Graph {graph_id: $gid})
                SET g.status = 'failed',
                    g.failure_reason = $reason
                """,
                gid=graph_id,
                reason=reason,
            )

        with self._get_session() as session:
            self._call_with_retry(session.execute_write, _mark)
        logger.info("Graph %s marked as failed: %s", graph_id, reason)

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

        with self._get_session() as session:
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

        with self._get_session() as session:
            self._call_with_retry(session.execute_write, _set)

    # ── Add data (NER → nodes/edges) ────────────────────────────────

    def add_text(
        self,
        graph_id: str,
        text: str,
        round_num: Optional[int] = None,
        ner_extractor: Optional["NERExtractor"] = None,
        degradations: Optional["DegradationCollector"] = None,
        extraction_tally: Optional["ChunkExtractionTally"] = None,
        document_id: Optional[str] = None,
        chunk_id: Optional[int] = None,
    ) -> str:
        """Process text in three phases — NER, embed, persist.

        Phase 1 (``extract_entities_and_relations``) + Phase 2
        (``embed_entities_and_relations``) leben in
        ``services/ingestion_pipeline.py``; Phase 3 (``_persist_episode``)
        ist storage-nah, weil sie Driver, Cypher und Retry-Logik nutzt.

        ``round_num`` (Issue #10) stamps new RELATION edges with
        ``valid_from_round``. ``None`` keeps the legacy behaviour (property
        absent); ``0`` means "present since the initial ingest"; any positive
        value means the edge was learned during that OASIS round.

        ``ner_extractor`` (Sub-Slice „build-respects-frontend-model"): wenn
        gesetzt, wird **dieser** Extractor statt der Storage-Default-Instanz
        (``self._ner``) für Phase 1 verwendet. Damit kann der Build-Pfad
        einen pro-Request gebauten Extractor mit Frontend-LLM-Override
        durchreichen, ohne den Storage-Singleton anzufassen.

        ``degradations`` (Issue #1029): Sammler für stille Teilausfälle.
        Phase 2 fängt Embedding-Fehler ab und arbeitet mit Leer-Vektoren
        weiter; ohne diesen Sammler bliebe das außerhalb des Logs
        unsichtbar. Wird von ``GraphBuilderService.add_text_batches``
        durchgereicht und ist thread-safe — die Chunks laufen parallel.

        ``extraction_tally`` (Issue #1029): zählt mit, ob dieser Chunk dem
        NER überhaupt etwas entnommen hat. Erst der Anteil über den ganzen
        Build macht daraus einen Befund.

        ``document_id``/``chunk_id`` (Issue #1152 Slice 1, Teil B): optionale
        Dokument-Provenance, wird unverändert an ``_persist_episode``
        durchgereicht und dort — falls gesetzt — als Property auf den
        Episode-Knoten geschrieben. ``None`` (Default) ändert nichts am
        bisherigen Verhalten (ADR-0013 §3).
        """
        episode_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Phase 1 — NER + Relation-Extraction
        ontology = self.get_ontology(graph_id)
        ner = ner_extractor if ner_extractor is not None else self._ner
        extraction = extract_entities_and_relations(
            ner, text, ontology, tally=extraction_tally
        )
        entities = extraction.get("entities", [])
        relations = extraction.get("relations", [])

        # Issue #11 Phase 2 — propose ontology mutations for any entity types
        # the LLM emitted that the current ontology does not cover. The
        # service decides per-mode whether to log, queue or auto-apply.
        self._evaluate_ontology_mutations(graph_id, ontology, entities, text)

        # Phase 2 — Batch-Embedding
        entity_embeddings, relation_embeddings = embed_entities_and_relations(
            self._embedding, entities, relations, degradations=degradations
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
            document_id=document_id,
            chunk_id=chunk_id,
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
        document_id: Optional[str] = None,
        chunk_id: Optional[int] = None,
    ) -> None:
        """Phase 3 — Persistiert Episode-Node, Entities und Relations in Neo4j.

        Storage-intern (Cypher + Driver + Retry); separat von Phase 1/2,
        weil reine Funktionen kein Neo4j-Coupling haben sollen.

        ``document_id``/``chunk_id`` (Issue #1152 Slice 1, Teil B): optionale
        Dokument-Provenance des Chunks. Neo4j legt für ``null``-wertige
        Map-Properties in ``CREATE`` keine Property an — bei Altprojekten
        ohne Manifest (beide Parameter ``None``) trägt der Episode-Knoten
        also unverändert weder ``document_id`` noch ``chunk_id``. Kein
        Schema-Zwang, keine Migration, kein Backfill (ADR-0013 §3).
        """
        with self._get_session() as session:
            # Create episode node
            def _create_episode(tx):
                tx.run(
                    """
                    CREATE (ep:Episode {
                        uuid: $uuid,
                        graph_id: $graph_id,
                        data: $data,
                        processed: true,
                        created_at: $created_at,
                        document_id: $document_id,
                        chunk_id: $chunk_id
                    })
                    """,
                    uuid=episode_id,
                    graph_id=graph_id,
                    data=text,
                    created_at=now,
                    document_id=document_id,
                    chunk_id=chunk_id,
                )

            self._call_with_retry(session.execute_write, _create_episode)

            # MERGE entities (upsert by graph_id + name_lower + entity_type).
            #
            # Canonical entity type used als Teil des MERGE-Identitätsschlüssels:
            # "Apple" (ORG) und "Apple" (FRUIT) sind zwei verschiedene Knoten.
            # `_canonical_entity_type` probt `entity_type | type | label`, daher
            # nutzen Summary, Label und MERGE-Key ALLE denselben Wert — sonst
            # entstehen Knoten, deren Label/Summary einen anderen Typ behauptet
            # als der MERGE-Key (Gemini-Review zu PR #523, Finding §1.5).
            #
            # Migration note für Bestandsgraphen:
            # Knoten ohne entity_type-Property bleiben lesbar; der neue Key
            # greift nur für neue Episoden. Manueller Migrationspfad ist im
            # PR-Body von #523 dokumentiert; hier wird KEIN Auto-Skript
            # ausgeführt.
            entity_uuid_map: Dict[str, str] = {}  # name_lower -> uuid
            for idx, entity in enumerate(entities):
                ename = entity["name"]
                etype = _canonical_entity_type(entity)
                attrs = entity.get("attributes", {})
                summary_text = f"{ename} ({etype})"
                embedding = entity_embeddings[idx] if idx < len(entity_embeddings) else []

                e_uuid = str(uuid.uuid4())
                entity_uuid_map[ename.lower()] = e_uuid

                def _merge_entity(tx, _uuid=e_uuid, _name=ename, _type=etype,
                                  _attrs=attrs, _embedding=embedding,
                                  _summary=summary_text, _now=now):
                    # MERGE by (graph_id, name_lower, entity_type) — typed deduplication.
                    # Same name with different entity_type yields two distinct nodes,
                    # e.g. "Apple" (ORG) vs "Apple" (FRUIT).
                    result = tx.run(
                        """
                        MERGE (n:Entity {graph_id: $gid, name_lower: $name_lower, entity_type: $entity_type})
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
                        entity_type=_type,
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

                # Add entity type label. Labels werden durch sanitize_label
                # auf einen sicheren Identifier beschränkt — LLM-Output kann
                # sonst aus dem Backtick-Quoting ausbrechen.
                safe_label = sanitize_label(etype)
                if safe_label:
                    try:
                        # MATCH muss denselben Identitätsschlüssel verwenden wie
                        # der MERGE oben (graph_id + name_lower + entity_type),
                        # sonst landen Labels auf gleichnamigen Knoten anderer
                        # Typen — Apple/ORG würde ein FRUIT-Label tragen.
                        def _add_label(
                            tx,
                            _name_lower=ename.lower(),
                            _entity_type=etype,
                            _label=safe_label,
                        ):
                            tx.run(
                                f"MATCH (n:Entity {{graph_id: $gid, name_lower: $nl, entity_type: $etype}}) SET n:`{_label}`",
                                gid=graph_id,
                                nl=_name_lower,
                                etype=_entity_type,
                            )
                        self._call_with_retry(session.execute_write, _add_label)
                    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
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
        ner_extractor: Optional["NERExtractor"] = None,
    ) -> List[str]:
        """Batch-add text chunks with progress reporting.

        ``ner_extractor`` wird an jedes ``add_text`` durchgereicht — damit
        kann der Build-Pfad einen LLM-Override-NER pro Run verwenden, ohne
        die globale ``Neo4jStorage._ner``-Instanz zu mutieren.
        """
        episode_ids = []
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            if not chunk or not chunk.strip():
                continue
            episode_id = self.add_text(
                graph_id, chunk, round_num=round_num, ner_extractor=ner_extractor
            )
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

    # ── Temporal edges (Issue #10) ──────────────────────────────────

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
            return edge_to_dict(
                record["r"], record["src_uuid"], record["tgt_uuid"]
            )

        with self._get_session() as session:
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

        with self._get_session() as session:
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

        with self._get_session() as session:
            return self._call_with_retry(session.execute_write, _write)


__all__ = ["Neo4jWriteMixin"]
