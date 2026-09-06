"""
Graph building service.
Uses GraphStorage (Neo4j) to replace Zep Cloud API.
"""

import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..config import Config
from ..contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from ..models.task import TaskManager, TaskStatus
from ..storage import GraphStorage
from .degradation_collector import ChunkExtractionTally, DegradationCollector
from .text_processor import TextProcessor

# Forward-import nur fürs Type-Hint — der konkrete Extractor wird vom
# Aufrufer (api/graph.py::build_graph) gebaut und durchgereicht, damit
# der Storage-Singleton-NER unangetastet bleibt.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..storage.ner_extractor import NERExtractor

logger = logging.getLogger('agora.graph_builder')


class GraphBuildCancelled(Exception):
    """Signalisiert kooperativen Abbruch während ``add_text_batches()``.

    Issue B2 (PLAN.md „Abbrechen & Pause“). Trägt die bereits fertig
    geschriebenen Episode-UUIDs (dieselbe Liste, die die Funktion im
    Erfolgsfall zurückgäbe) — ``services/graph_build.py::build_task`` nutzt
    sie, um den Graphen als unvollständig statt als abgeschlossen zu
    markieren. Bewusst keine Reparatur/kein Rollback: einzeln committete
    Episode-/Entity-/Relation-Transaktionen (``storage/neo4j_write.py``)
    bleiben stehen, wie sie sind.

    ``episode_uuids`` schließt (Review-Finding PR #1371, Befund 5) auch
    Chunks ein, die zum Abbruchzeitpunkt bereits liefen, aber noch nicht
    über ``as_completed`` konsumiert waren — die Nachsammel-Schleife in
    ``add_text_batches`` wartet auf sie, statt ihr Ergebnis zu verwerfen.
    Chunks, die zu diesem Zeitpunkt noch unbearbeitet in der Warteschlange
    standen, sind weiterhin nicht enthalten (echt storniert). Die Zahl ist
    damit exakt, nicht nur eine Untergrenze — außer ein nachgesammelter
    Chunk wirft selbst eine Exception; dann fehlt er (geloggt, nicht
    erneut geworfen).
    """

    def __init__(self, episode_uuids: List[str]) -> None:
        super().__init__(
            f"add_text_batches cancelled after {len(episode_uuids)} chunk(s)"
        )
        self.episode_uuids = episode_uuids


@dataclass
class GraphInfo:
    """Graph information"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Graph building service
    Build knowledge graph through GraphStorage interface
    """

    def __init__(self, storage: GraphStorage):
        self.storage = storage
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "Agora Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,
        ner_extractor: Optional["NERExtractor"] = None,
    ) -> str:
        """
        Build graph asynchronously

        Args:
            text: Input text to process
            ontology: Ontology definition (from ontology generator output)
            graph_name: Name for the graph
            chunk_size: Text chunk size
            chunk_overlap: Chunk overlap size
            batch_size: Number of chunks to send per batch
            ner_extractor: optionaler NER-Override pro Build-Run (Sub-Slice
                „build-respects-frontend-model“). Wenn gesetzt, wird er an
                ``storage.add_text`` durchgereicht — der Storage-Singleton-NER
                bleibt unverändert für andere Pfade.

        Returns:
            Task ID
        """
        # Create task
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )

        # Execute build in background thread
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, ner_extractor)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        ner_extractor: Optional["NERExtractor"] = None,
    ):
        """Graph build worker thread"""
        # Issue #1029: sammelt stille Teilausfälle aus allen Phasen dieses
        # Builds. Wird bis in ``embed_entities_and_relations`` durchgereicht
        # und landet am Ende im Task-Ergebnis, damit die Oberfläche einen
        # Qualitätsverlust nicht länger für einen sauberen Lauf hält.
        degradations = DegradationCollector()
        # Issue #1029: zählt, wie viele Chunks dem NER überhaupt etwas
        # entnommen haben. Die Gesamtzahlen verraten das nicht — bei
        # Befund B-24 lieferten zwei von vier Chunks nichts, während
        # node_count noch nach einem brauchbaren Graphen aussah.
        extraction_tally = ChunkExtractionTally()
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Starting graph building..."
            )

            # 1. Create graph
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Graph created: {graph_id}"
            )

            # 2. Set ontology
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="Ontology set"
            )

            # 3. Text chunking
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Text split into {total_chunks} chunks"
            )

            # 4. Send data in batches (NER + embedding + Neo4j insert — synchronous)
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog, _completed, _total: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.6),  # 20-80%
                    message=msg
                ),
                ner_extractor=ner_extractor,
                degradations=degradations,
                extraction_tally=extraction_tally,
            )

            # 5. Wait for processing (no-op for Neo4j — already synchronous)
            self.storage.wait_for_processing(episode_uuids)

            self.task_manager.update_task(
                task_id,
                progress=85,
                message="Data processing completed, getting graph information..."
            )

            # 6. Get graph information
            graph_info = self._get_graph_info(graph_id)

            # 7. Qualitätsgate (Issue #1029). Die Zahlen lagen hier schon
            # immer vor — sie wurden nur nie bewertet. Ein Graph unter der
            # Schwelle meldete "Graph fertig" und ließ den Report Schritte
            # später an fehlender Evidenz scheitern.
            self._assess_graph_quality(graph_info, extraction_tally, degradations)

            # Completed
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
                # Issue #1029: leere Liste ist der Normalfall und heißt
                # „nichts ist still ausgefallen“.
                "degradations": degradations.report().model_dump(mode="json"),
            })

        except Exception as e:  # noqa: BLE001 — exc logged via traceback or propagated
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def _assess_graph_quality(
        self,
        graph_info: GraphInfo,
        extraction_tally: ChunkExtractionTally,
        degradations: DegradationCollector,
    ) -> None:
        """``assess_graph_quality_from_counts`` für ein ``GraphInfo``-Objekt."""
        self.assess_graph_quality_from_counts(
            node_count=graph_info.node_count,
            edge_count=graph_info.edge_count,
            extraction_tally=extraction_tally,
            degradations=degradations,
        )

    def assess_graph_quality_from_counts(
        self,
        *,
        node_count: int,
        edge_count: int,
        extraction_tally: ChunkExtractionTally,
        degradations: DegradationCollector,
    ) -> None:
        """Bewertet den fertigen Graphen gegen die Qualitätsschwellen (Issue #1029).

        Nimmt die Zahlen statt eines ``GraphInfo``, weil der produktive
        Build-Pfad in ``services/graph_build.py`` mit dem rohen
        ``get_graph_data()``-Dict arbeitet und kein ``GraphInfo`` baut.
        Beide Pfade müssen dieses Gate durchlaufen — sonst ist es genau
        dort blind, wo es zählt.

        Bis dahin rief ``_build_graph_worker`` ``complete_task``
        unbedingt, sobald alle Chunks durch waren — ohne ``node_count``,
        ``edge_count`` oder die Chunk-Erfolgsquote auch nur anzusehen. Ein
        Graph mit 3 Entitäten und 0 Beziehungen meldete „Graph fertig“,
        und der Report scheiterte Minuten später an fehlender Evidenz.

        Fehlende Beziehungen blockieren: Ein Graph ohne eine einzige Kante
        ist keine Wissensbasis, sondern eine Stichwortliste, und jeder
        weitere Schritt darauf ist verlorene Zeit. Zu wenige Entitäten und
        eine schwache Chunk-Quote bleiben Warnungen — dort ist das
        Ergebnis dünn, aber nicht wertlos.

        Schwellen über ``Config``: ``GRAPH_MIN_ENTITIES``,
        ``GRAPH_MIN_RELATIONS``, ``GRAPH_MIN_CHUNK_SUCCESS_RATIO``.
        """
        if edge_count < Config.GRAPH_MIN_RELATIONS:
            degradations.record(
                kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
                severity=DegradationSeverity.BLOCKING,
                detail=(
                    f"Der Graph enthält {node_count} Entitäten, aber nur "
                    f"{edge_count} Beziehungen (erwartet: mindestens "
                    f"{Config.GRAPH_MIN_RELATIONS}). Ohne Beziehungen ist "
                    "der Graph nicht auswertbar."
                ),
                context={
                    "node_count": node_count,
                    "edge_count": edge_count,
                    "min_relations": Config.GRAPH_MIN_RELATIONS,
                },
            )
        elif node_count < Config.GRAPH_MIN_ENTITIES:
            degradations.record(
                kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
                severity=DegradationSeverity.WARNING,
                detail=(
                    f"Der Graph enthält nur {node_count} Entitäten "
                    f"(erwartet: mindestens {Config.GRAPH_MIN_ENTITIES}). "
                    "Die Auswertung wird entsprechend dünn."
                ),
                context={
                    "node_count": node_count,
                    "edge_count": edge_count,
                    "min_entities": Config.GRAPH_MIN_ENTITIES,
                },
            )

        # Die Chunk-Quote ist unabhängig von den Gesamtzahlen: Ein Graph
        # kann genug Entitäten tragen und trotzdem aus der Hälfte des
        # Dokuments nichts gezogen haben.
        ratio = extraction_tally.success_ratio
        if (
            Config.GRAPH_MIN_CHUNK_SUCCESS_RATIO > 0
            and extraction_tally.total > 0
            and ratio < Config.GRAPH_MIN_CHUNK_SUCCESS_RATIO
        ):
            degradations.record(
                kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
                severity=DegradationSeverity.WARNING,
                detail=(
                    f"Nur {extraction_tally.productive} von "
                    f"{extraction_tally.total} Textabschnitten haben "
                    "Entitäten oder Beziehungen geliefert. Ein großer Teil "
                    "des Dokuments ist nicht im Graphen abgebildet."
                ),
                context={
                    "productive_chunks": extraction_tally.productive,
                    "total_chunks": extraction_tally.total,
                    "success_ratio": round(ratio, 3),
                    "min_success_ratio": Config.GRAPH_MIN_CHUNK_SUCCESS_RATIO,
                },
            )

    def create_graph(self, name: str) -> str:
        """Create graph — sets status='building' atomically on first creation."""
        return self.storage.create_graph(
            name=name,
            description="Agora Social Simulation Graph"
        )

    def mark_graph_completed(self, graph_id: str) -> None:
        """Delegate to storage: set graph status to 'completed'."""
        self.storage.mark_graph_completed(graph_id)

    def mark_graph_failed(self, graph_id: str, reason: Optional[str] = None) -> None:
        """Delegate to storage: set graph status to 'failed' with optional reason."""
        self.storage.mark_graph_failed(graph_id, reason=reason)

    def mark_graph_incomplete(self, graph_id: str, reason: Optional[str] = None) -> None:
        """Delegate to storage: set graph status to 'incomplete' with optional reason.

        Issue B2 — kooperativer Abbruch eines ``graph_build``. Anders als
        :meth:`mark_graph_failed` ist das kein Fehler: der Graph trägt
        bereits committete Episoden/Entities/Relations und bleibt nutzbar,
        nur unvollständig gegenüber dem Ursprungsdokument. Kein Rollback,
        kein ``delete_graph`` — die einzeln committeten Neo4j-Transaktionen
        (``storage/neo4j_write.py::_persist_episode``) bleiben stehen.
        """
        self.storage.mark_graph_incomplete(graph_id, reason=reason)

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """
        SetGraphOntology

        Simply stores ontology as JSON in the Graph node.
        No more dynamic Pydantic class creation (was Zep-specific).
        The NER extractor reads this ontology to guide extraction.
        """
        self.storage.set_ontology(graph_id, ontology)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable[[str, float, int, int], None]] = None,
        ner_extractor: Optional["NERExtractor"] = None,
        degradations: Optional[DegradationCollector] = None,
        extraction_tally: Optional[ChunkExtractionTally] = None,
        document_ids: Optional[List[Optional[str]]] = None,
        chunk_ids: Optional[List[Optional[int]]] = None,
        run_id: Optional[str] = None,
    ) -> List[str]:
        """Add text chunks to graph in parallel, return uuid list of all episodes.

        Parallelism is controlled via Config.GRAPH_PARALLEL_CHUNKS (env GRAPH_PARALLEL_CHUNKS).
        Neo4j driver sessions and the OpenAI SDK are thread-safe, so NER/embed/write
        runs concurrently per chunk. batch_size is kept for API compatibility but unused.

        The progress_callback receives four positional arguments:
          - msg (str): human-readable progress message
          - progress_ratio (float): 0.0–1.0 completion ratio
          - completed (int): number of chunks committed so far (monotonically increasing)
          - total (int): total number of chunks in this build

        ``ner_extractor`` wird an jedes ``storage.add_text`` durchgereicht
        (Override pro Run). Ohne Override greift der Storage-Singleton-NER.

        ``degradations`` (Issue #1029) sammelt stille Teilausfälle aus den
        parallel laufenden Chunks — vor allem einen Embedding-Ausfall, der
        sonst nur als Logzeile existierte. Der Sammler ist thread-safe und
        fasst gleichartige Meldungen zusammen, statt sie pro Chunk zu
        wiederholen.

        ``extraction_tally`` (Issue #1029) zählt, wie viele Chunks der NER
        überhaupt etwas entnommen hat. Ein technisch erfolgreicher Chunk
        mit null Extraktionen passierte bislang ungeprüft — auffällig wird
        er erst im Verhältnis zur Gesamtzahl.

        ``document_ids``/``chunk_ids`` (Issue #1152 Slice 1, Teil B):
        optionale, zu ``chunks`` parallele Listen gleicher Länge mit der
        Dokument-Provenance je Chunk (``None`` je Eintrag bei Altprojekten
        ohne Manifest-Sidecar). Wird an ``storage.add_text`` durchgereicht
        und dort optional auf den Episode-Knoten geschrieben. Bleiben beide
        Parameter ``None`` (Default), ändert sich nichts am bisherigen
        Verhalten.

        ``run_id`` (Issue B2): wenn gesetzt, wird das Cancel-Flag
        (``services/sim/cancel_flag.py``) in der ``as_completed``-Schleife
        nach jedem fertigen Chunk geprüft. Bei einem Abbruch werden
        ausstehende, noch nicht gestartete Chunks verworfen
        (``pool.shutdown(wait=False, cancel_futures=True)``); bereits
        laufende Chunks dürfen fertig committen — das ist akzeptiert, nicht
        repariert. Die Funktion wirft dann :class:`GraphBuildCancelled` mit
        den bis dahin fertigen Episode-UUIDs statt normal zurückzukehren.
        Bleibt ``run_id`` ``None`` (Default), ändert sich nichts am
        bisherigen Verhalten.
        """
        total_chunks = len(chunks)
        if total_chunks == 0:
            return []

        if document_ids is not None and len(document_ids) != total_chunks:
            raise ValueError("document_ids must have the same length as chunks")
        if chunk_ids is not None and len(chunk_ids) != total_chunks:
            raise ValueError("chunk_ids must have the same length as chunks")

        max_workers = max(1, min(Config.GRAPH_PARALLEL_CHUNKS, total_chunks))
        logger.info(
            f"[graph_build] Starting: {total_chunks} chunks, parallel workers={max_workers}"
        )

        episode_uuids: List[Optional[str]] = [None] * total_chunks

        def _process(idx: int, chunk: str) -> str:
            chunk_preview = chunk[:80].replace('\n', ' ')
            logger.info(
                f"[graph_build] Chunk {idx + 1}/{total_chunks} "
                f"({len(chunk)} chars): \"{chunk_preview}...\""
            )
            t0 = time.time()
            try:
                # Issue #10 — initial document ingest stamps round 0 so later
                # time-travel diffs can distinguish document knowledge from
                # edges learned during simulation.
                episode_id = self.storage.add_text(
                    graph_id,
                    chunk,
                    round_num=0,
                    ner_extractor=ner_extractor,
                    degradations=degradations,
                    extraction_tally=extraction_tally,
                    document_id=document_ids[idx] if document_ids is not None else None,
                    chunk_id=chunk_ids[idx] if chunk_ids is not None else None,
                )
                elapsed = time.time() - t0
                logger.info(
                    f"[graph_build] Chunk {idx + 1}/{total_chunks} done in {elapsed:.1f}s"
                )
                return episode_id
            except Exception as e:
                elapsed = time.time() - t0
                logger.error(
                    f"[graph_build] Chunk {idx + 1}/{total_chunks} FAILED "
                    f"after {elapsed:.1f}s: {e}"
                )
                raise

        completed = 0

        # Issue: backend/wsgi.py ruft gevent.monkey.patch_all() auf — jeder
        # Socket im Prozess ist damit ein kooperativer gevent-Socket,
        # gebunden an den Hub des Threads, der ihn erzeugt hat.
        # ThreadPoolExecutor verteilt die Chunks unten aber auf echte
        # OS-Threads, jeder mit eigenem gevent-Hub, während die Neo4j-
        # Connections aus dem prozessweiten Driver-Pool stammen und damit
        # potenziell einem fremden Hub gehören. Produktionsfolge: "Failed to
        # write data to connection" / "defunct connection", 1–2s
        # Retry-Backoff pro Chunk. ``oasis_profile_generator.py`` löst
        # dasselbe Problem für die Persona-Generierung bereits über
        # ``gevent.pool.Pool`` statt ``ThreadPoolExecutor`` — hier dasselbe
        # Muster. ``monkey.is_patched()`` (ohne Argument) liefert seit
        # gevent 23.x keinen "socket"-Status mehr; die öffentliche API ist
        # ``monkey.is_module_patched(name)``.
        try:
            from gevent import monkey
        except ImportError:
            is_gevent = False
        else:
            is_gevent = monkey.is_module_patched("socket")

        if is_gevent:
            logger.info(
                "[graph_build] Gevent detected: using native cooperative "
                "Pool for parallel graph build"
            )
            from gevent.pool import Pool

            pool = Pool(max_workers)

            def _process_indexed(item):
                idx, chunk = item
                return idx, _process(idx, chunk)

            try:
                for idx, episode_id in pool.imap_unordered(
                    _process_indexed, enumerate(chunks)
                ):
                    episode_uuids[idx] = episode_id  # raises on first failed chunk
                    completed += 1
                    if progress_callback:
                        progress_callback(
                            f"Processed {completed}/{total_chunks} chunks...",
                            completed / total_chunks,
                            completed,
                            total_chunks,
                        )
                    if run_id:
                        from .sim.cancel_flag import is_cancel_requested

                        if is_cancel_requested(run_id):
                            # Gevent kennt keine Trennung "nur Wartende
                            # abbrechen" wie ThreadPoolExecutor.shutdown(
                            # cancel_futures=True) — pool.kill() beendet
                            # auch bereits laufende Greenlets. Gröberer
                            # Schnitt als im Thread-Pfad unten (s. auch
                            # oasis_profile_generator.py::
                            # _consume_gevent_results), aber der einzige
                            # verfügbare Weg, neue Neo4j-Writes sofort zu
                            # stoppen.
                            logger.info(
                                "[graph_build] Abgebrochen (run_id=%s): "
                                "%d/%d Chunks fertig committet",
                                run_id, completed, total_chunks,
                            )
                            pool.kill()
                            raise GraphBuildCancelled(
                                [uuid for uuid in episode_uuids if uuid is not None]
                            )
            finally:
                pool.join()
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_process, idx, chunk): idx for idx, chunk in enumerate(chunks)}
                for future in as_completed(futures):
                    idx = futures[future]
                    episode_uuids[idx] = future.result()  # raises on first failed chunk
                    completed += 1
                    if progress_callback:
                        progress_callback(
                            f"Processed {completed}/{total_chunks} chunks...",
                            completed / total_chunks,
                            completed,
                            total_chunks,
                        )
                    if run_id:
                        from .sim.cancel_flag import is_cancel_requested

                        if is_cancel_requested(run_id):
                            # Issue B2: nur ausstehende, noch nicht gestartete
                            # Chunks werden verworfen. Bereits laufende Worker
                            # committen ihre Neo4j-Transaktion (Episode + Entities
                            # + Relations, jeweils einzeln — s. neo4j_write.py)
                            # noch fertig; der `with`-Block wartet beim Verlassen
                            # darauf (ThreadPoolExecutor.__exit__ →
                            # shutdown(wait=True)). Das ist akzeptiert, nicht
                            # repariert — kein Rollback, kein delete_graph.
                            logger.info(
                                "[graph_build] Abgebrochen (run_id=%s): "
                                "%d/%d Chunks fertig committet",
                                run_id, completed, total_chunks,
                            )
                            pool.shutdown(wait=False, cancel_futures=True)

                            # Review-Finding (PR #1371, Befund 5): Chunks, die
                            # zum Zeitpunkt des Abbruchs schon aus der Queue
                            # geholt waren (also bereits laufen), werden von
                            # ``cancel_futures=True`` NICHT erfasst — das
                            # storniert nur, was noch in der Warteschlange steht.
                            # Diese laufenden Worker committen ihre Neo4j-
                            # Transaktion trotzdem fertig, und der `with`-Block
                            # wartet beim Verlassen ohnehin auf sie
                            # (``ThreadPoolExecutor.__exit__`` →
                            # ``shutdown(wait=True)``). Ohne dieses Nachsammeln
                            # wären ihre Episode-UUIDs im Graphen vorhanden, aber
                            # weder in der zurückgegebenen Liste noch im
                            # ``episode_count`` des Cancel-Ergebnisses gezählt —
                            # bei mehreren parallelen Workern eine stille
                            # Untererfassung. ``future.cancelled()`` ist nach
                            # ``shutdown(cancel_futures=True)`` deterministisch:
                            # True nur für Futures, die noch in der Queue
                            # standen; bereits laufende bleiben False und werden
                            # hier eingesammelt (kein zusätzliches Warten — der
                            # `with`-Block würde ohnehin auf sie warten, wir
                            # lesen nur zusätzlich ihr Ergebnis).
                            for other_future, other_idx in futures.items():
                                if other_future is future or episode_uuids[other_idx] is not None:
                                    continue
                                if other_future.cancelled():
                                    continue
                                try:
                                    episode_uuids[other_idx] = other_future.result()
                                except Exception as exc:  # noqa: BLE001 — best effort; Abbruch-Meldung geht vor
                                    logger.warning(
                                        "[graph_build] Chunk %d konnte nach dem Abbruch "
                                        "nicht nachträglich eingesammelt werden: %r",
                                        other_idx + 1, exc,
                                    )

                            raise GraphBuildCancelled(
                                [uuid for uuid in episode_uuids if uuid is not None]
                            )

        logger.info(f"[graph_build] All {total_chunks} chunks processed successfully")
        return [uuid for uuid in episode_uuids if uuid is not None]

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Get graph information"""
        info = self.storage.get_graph_info(graph_id)
        return GraphInfo(
            graph_id=info["graph_id"],
            node_count=info["node_count"],
            edge_count=info["edge_count"],
            entity_types=info.get("entity_types", []),
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Get complete graph data (including details)"""
        return self.storage.get_graph_data(graph_id)

    def delete_graph(self, graph_id: str):
        """Delete graph"""
        self.storage.delete_graph(graph_id)
