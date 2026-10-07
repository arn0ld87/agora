"""Graphen duplizieren (Issue #1808, Etappe 8, ADR-0022 §6).

Eine Kopie ist ein **neues Projekt** mit neuer ``graph_id``, eigenem Namen,
der Ontologie, dem Dokumentmanifest samt Dateien und extrahiertem Text des
Quellprojekts sowie allen Entitäten, Beziehungen und Episoden des Graphen.
Herkunftsmerkmale (``origin``, ``origin_changed_at``) und Episoden bleiben
erhalten; Embedding-Vektoren werden unverändert übernommen, es gibt keinen
LLM- und keinen Embedding-Aufruf.

Die Kopie ist der Ausweg aus der Sperre: Duplizieren ist deshalb auch aus
einem **gesperrten** Graphen erlaubt (ein Lesezugriff auf die Quelle), die
Kopie selbst ist nicht gesperrt, weil keine Simulation sie verwendet.

Ablauf:

1. ``start`` (synchron, im Request): Quelle prüfen (existiert, nicht im Bau),
   Embedding-Migration ablehnen, Zielprojekt anlegen, Job in der
   ``RunRegistry`` anlegen (``run_type='graph_duplicate'``), Hintergrundjob
   starten. Zielgraph und Zielprojekt stehen ab diesem Moment fest.
2. ``run`` (Hintergrundjob): Projektartefakte kopieren, dann Episoden,
   Entitäten und Beziehungen seitenweise schreiben, zuletzt zählen und den
   Zielgraphen abschließen.

Wiederholbarkeit: Die Kennungen des Jobs und des Zielgraphen sind
deterministisch aus ``(Quellgraph, client_request_id)`` abgeleitet (UUIDv5).
Derselbe Aufruf findet den bestehenden Job und gibt ihn zurück, es entsteht
nie ein zweiter Graph. Auch die UUIDs der kopierten Elemente sind
deterministisch aus dem Zielgraphen und der Quell-UUID abgeleitet; die
``MERGE``-Statements des Speicher-Mixins machen eine wiederholte
Schreib-Transaktion deshalb folgenlos.

Fehler: Schlägt irgendein Schritt fehl, werden Zielgraph (Neo4j) und
Zielprojekt (Metadaten und Dateien) wieder entfernt und der Job endet als
``failed``. Gelingt das Aufräumen nicht vollständig, steht das im Fehlertext
des Jobs, statt still zu bleiben. Storage-Fehler werden nie verschluckt.
Ein Prozess-Neustart während des Jobs wird von der Startup-Reconciliation als
``failed/process_restart`` sichtbar gemacht; eine dabei entstandene
Teilkopie räumt der Dienst nicht selbst auf (siehe ``docs/runbooks/upgrade.md``).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..contracts.graph_edit_contract import GraphDuplicateJob, GraphDuplicateRequest
from ..contracts.project_contract import Project, ProjectStatus
from ..models.project import ProjectManager
from ..storage.neo4j_duplicate import GraphDuplicateWriteError
from ..utils.logger import get_logger
from .graph_edit_service import EmbeddingMigrationRunningError, embedding_migration_active

if TYPE_CHECKING:
    from ..storage.neo4j_storage import Neo4jStorage
    from .run_registry import RunRegistry

logger = get_logger("agora.graph_duplicate")

RUN_TYPE = "graph_duplicate"

# Seitengröße beim Lesen und Schreiben. Klein gehalten, weil jede Zeile einen
# Embedding-Vektor trägt (bis zu einigen tausend Gleitkommazahlen): 100 Zeilen
# sind je Transaktion einige MB.
PAGE_SIZE = 100

_PROJECT_SCAN_LIMIT = 100_000
_COPYABLE_STATUSES = frozenset({"completed", "incomplete"})

# Eine Anfrage legt Projekt und Job an. Zwei gleichzeitige Anfragen mit
# derselben ``client_request_id`` dürfen nicht beide ein Projekt anlegen.
# Der Webprozess ist ein einzelner Worker, ein Prozess-Lock genügt.
_START_LOCK = threading.Lock()


class GraphDuplicateError(Exception):
    """Basis der Fachfehler beim Duplizieren (Meldung ist für Nutzer bestimmt)."""


class GraphDuplicateSourceNotFound(GraphDuplicateError):
    """Der Quellgraph existiert nicht."""


class GraphDuplicateSourceStateError(GraphDuplicateError):
    """Der Quellgraph ist in einem Zustand, in dem er nicht kopiert werden kann."""

    def __init__(self, status: str) -> None:
        super().__init__(f"Graph im Zustand '{status}' lässt sich nicht kopieren")
        self.status = status


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_ids(source_graph_id: str, client_request_id: str) -> Dict[str, str]:
    """Deterministische Kennungen von Job und Zielgraph aus Quelle und Aufrufer-Kennung."""
    key = f"agora:graph-duplicate:{source_graph_id}:{client_request_id.lower()}"
    return {
        "run_id": f"run_{uuid.uuid5(uuid.NAMESPACE_URL, key + ':run').hex[:12]}",
        "graph_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key + ":graph")),
    }


def mapped_uuid(target_graph_id: str, kind: str, source_uuid: str) -> str:
    """UUID eines kopierten Elements: stabil für denselben Zielgraphen und dieselbe Quelle."""
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL, f"agora:graph-duplicate:{target_graph_id}:{kind}:{source_uuid}"
        )
    )


def _describe(exc: BaseException) -> str:
    """Fehlertext für den Job. Eigene Fachfehler im Klartext, sonst nur der Typ.

    Fremde Ausnahmen können Pfade, Cypher oder Verbindungsdaten enthalten;
    der Job-Text geht an das Frontend.
    """
    if isinstance(exc, (GraphDuplicateError, GraphDuplicateWriteError)):
        return str(exc)
    return type(exc).__name__


def _write_text_atomic(path: str, text: str) -> None:
    """Schreibt ``text`` über eine Temp-Datei, ``fsync`` und ``os.replace``."""
    tmp = f"{path}.tmp-{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _copy_file_atomic(source: str, target: str) -> None:
    """Kopiert eine Datei über eine Temp-Datei und ``os.replace``."""
    import shutil

    tmp = f"{target}.tmp-{uuid.uuid4().hex[:8]}"
    try:
        shutil.copyfile(source, tmp)
        with open(tmp, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _default_enqueue(job_name: str, target: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    from ..jobs import enqueue

    return enqueue(job_name, target, *args, **kwargs)


def _default_registry() -> "RunRegistry":
    from .run_registry import RunRegistry

    return RunRegistry()


class GraphDuplicateService:
    """Fachregeln und Ablauf des Kopierens. Siehe Modul-Docstring."""

    def __init__(
        self,
        storage: "Neo4jStorage",
        *,
        migration_active: Callable[[], bool] = embedding_migration_active,
        registry: Optional["RunRegistry"] = None,
        enqueue: Callable[..., str] = _default_enqueue,
        clock: Callable[[], str] = _utc_now,
        project_lister: Optional[Callable[[], List[Project]]] = None,
    ) -> None:
        self._storage = storage
        self._last_reported: Optional[tuple[int, str]] = None
        self._migration_active = migration_active
        self._registry = registry or _default_registry()
        self._enqueue = enqueue
        self._clock = clock
        self._project_lister = project_lister or (
            lambda: ProjectManager.list_projects(limit=_PROJECT_SCAN_LIMIT)
        )

    # ── Start (synchron) ────────────────────────────────────────────

    def start(self, source_graph_id: str, request: GraphDuplicateRequest) -> GraphDuplicateJob:
        """Legt Zielprojekt und Job an und startet den Hintergrundjob.

        Wiederholung mit derselben ``client_request_id`` gibt den bestehenden
        Job zurück (auch einen fehlgeschlagenen: für einen neuen Versuch
        braucht der Aufrufer eine neue Kennung).
        """
        ids = _derive_ids(source_graph_id, request.client_request_id)
        with _START_LOCK:
            existing = self._registry.get_run(ids["run_id"])
            if existing is not None:
                return self._job_from_run(existing)

            source_props = self._storage.duplicate_read_graph(source_graph_id)
            if source_props is None:
                raise GraphDuplicateSourceNotFound(source_graph_id)
            status = str(source_props.get("status") or "completed")
            if status not in _COPYABLE_STATUSES:
                raise GraphDuplicateSourceStateError(status)
            if self._migration_active():
                raise EmbeddingMigrationRunningError(source_graph_id)

            source_project = self._find_source_project(source_graph_id)
            project = self._create_target_project(
                name=request.name,
                target_graph_id=ids["graph_id"],
                source_project=source_project,
                source_props=source_props,
            )
            try:
                run = self._registry.create_run(
                    RUN_TYPE,
                    project.project_id,
                    run_id=ids["run_id"],
                    status="pending",
                    progress=0,
                    message="Kopie angelegt",
                    linked_ids={
                        "project_id": project.project_id,
                        "graph_id": ids["graph_id"],
                        "source_graph_id": source_graph_id,
                    },
                    metadata={"graph_name": request.name},
                )
            except Exception:
                self._discard_project(project.project_id)
                raise

            try:
                self._enqueue(
                    "graph_duplicate",
                    self.run,
                    ids["run_id"],
                    source_graph_id,
                    ids["graph_id"],
                    project.project_id,
                    source_project.project_id if source_project else None,
                    run_id=ids["run_id"],
                )
            except Exception as exc:
                self._rollback(ids["graph_id"], project.project_id)
                self._registry.update_run(
                    ids["run_id"],
                    status="failed",
                    error=_describe(exc),
                    termination_reason="error",
                    message="Kopie konnte nicht gestartet werden",
                )
                raise
            logger.info(
                "Graph-Kopie angelegt (quelle=%s, ziel=%s, projekt=%s, run=%s)",
                source_graph_id,
                ids["graph_id"],
                project.project_id,
                ids["run_id"],
            )
            return self._job_from_run(run)

    def _find_source_project(self, source_graph_id: str) -> Optional[Project]:
        for project in self._project_lister():
            if project.graph_id == source_graph_id:
                return project
        return None

    def _create_target_project(
        self,
        *,
        name: str,
        target_graph_id: str,
        source_project: Optional[Project],
        source_props: Dict[str, Any],
    ) -> Project:
        project = ProjectManager.create_project(name)
        try:
            project.status = ProjectStatus.GRAPH_BUILDING
            project.graph_id = target_graph_id
            if source_project is not None:
                project.ontology = source_project.ontology
                project.analysis_summary = source_project.analysis_summary
                project.total_text_length = source_project.total_text_length
                project.simulation_requirement = source_project.simulation_requirement
                project.chunk_size = source_project.chunk_size
                project.chunk_overlap = source_project.chunk_overlap
                project.llm_model = source_project.llm_model
                project.llm_provider = source_project.llm_provider
                project.llm_profile_id = source_project.llm_profile_id
                project.ai_model_ref = source_project.ai_model_ref
                files_dir = ProjectManager._get_project_files_dir(project.project_id)
                project.files = [
                    _rewrite_file_entry(entry, files_dir) for entry in source_project.files
                ]
            else:
                project.ontology = _ontology_from_graph(source_props)
            ProjectManager.save_project(project)
        except Exception:
            self._discard_project(project.project_id)
            raise
        return project

    @staticmethod
    def _discard_project(project_id: str) -> None:
        try:
            ProjectManager.delete_project(project_id)
        except Exception as exc:  # noqa: BLE001 — der eigentliche Fehler wird weitergereicht
            logger.error(
                "Zielprojekt %s ließ sich nicht entfernen: %s", project_id, type(exc).__name__
            )

    @staticmethod
    def _job_from_run(run: Dict[str, Any]) -> GraphDuplicateJob:
        linked = run.get("linked_ids") or {}
        return GraphDuplicateJob(
            run_id=run["run_id"],
            source_graph_id=linked.get("source_graph_id", ""),
            graph_id=linked.get("graph_id", ""),
            project_id=linked.get("project_id", ""),
            status=run.get("status", "pending"),
            progress=int(run.get("progress") or 0),
            message=run.get("message") or "",
            error=run.get("error"),
        )

    # ── Hintergrundjob ──────────────────────────────────────────────

    def run(
        self,
        run_id: str,
        source_graph_id: str,
        target_graph_id: str,
        project_id: str,
        source_project_id: Optional[str],
    ) -> None:
        """Kopiert Artefakte und Graph. Bei Fehler: Teilkopie entfernen, Job ``failed``."""
        try:
            self._progress(run_id, 2, "Quelle wird gelesen")
            source_props = self._storage.duplicate_read_graph(source_graph_id)
            if source_props is None:
                raise GraphDuplicateSourceNotFound(source_graph_id)
            totals = self._storage.duplicate_count(source_graph_id)

            if source_project_id:
                self._progress(run_id, 5, "Dokumente werden kopiert")
                self._copy_project_artifacts(source_project_id, project_id)

            self._storage.duplicate_create_graph(
                graph_id=target_graph_id,
                name=self._target_name(run_id),
                description=str(source_props.get("description") or ""),
                ontology_json=str(source_props.get("ontology_json") or "{}"),
                now=self._clock(),
            )
            written = self._copy_graph(run_id, source_graph_id, target_graph_id, totals)
            self._verify(target_graph_id, written)
            self._finish(run_id, target_graph_id, project_id, source_props)
        except Exception as exc:  # noqa: BLE001 — jeder Fehler beendet den Job sichtbar
            logger.error(
                "Graph-Kopie fehlgeschlagen (quelle=%s, ziel=%s, run=%s): %s",
                source_graph_id,
                target_graph_id,
                run_id,
                type(exc).__name__,
                exc_info=True,
            )
            cleanup_problems = self._rollback(target_graph_id, project_id)
            error = _describe(exc)
            if cleanup_problems:
                error = f"{error}; Aufräumen unvollständig: {', '.join(cleanup_problems)}"
            self._registry.update_run(
                run_id,
                status="failed",
                error=error,
                termination_reason="error",
                message="Kopie fehlgeschlagen",
            )

    def _target_name(self, run_id: str) -> str:
        run = self._registry.get_run(run_id) or {}
        return str((run.get("metadata") or {}).get("graph_name") or "")

    def _progress(self, run_id: str, percent: int, message: str) -> None:
        # Jeder Registry-Write hängt ein Run-Event an: nur melden, wenn sich etwas geändert hat.
        if self._last_reported == (percent, message):
            return
        self._last_reported = (percent, message)
        self._registry.update_run(run_id, status="processing", progress=percent, message=message)

    def _copy_graph(
        self, run_id: str, source_graph_id: str, target_graph_id: str, totals: Dict[str, int]
    ) -> Dict[str, int]:
        storage = self._storage
        written = {"episodes": 0, "entities": 0, "relations": 0}

        after = ""
        while True:
            page = storage.duplicate_read_episodes(source_graph_id, after, PAGE_SIZE)
            if not page:
                break
            rows = []
            for item in page:
                props = dict(item["props"])
                old = _require_uuid(props, "Episode")
                new = mapped_uuid(target_graph_id, "episode", old)
                props["uuid"] = new
                props["graph_id"] = target_graph_id
                rows.append({"uuid": new, "props": props})
            written["episodes"] += storage.duplicate_write_episodes(rows)
            after = page[-1]["props"]["uuid"]
            self._progress(
                run_id,
                _scaled(written["episodes"], totals.get("episodes", 0), 15, 30),
                "Episoden werden kopiert",
            )

        entity_sources: List[str] = []
        after = ""
        while True:
            page = storage.duplicate_read_entities(source_graph_id, after, PAGE_SIZE)
            if not page:
                break
            entity_rows = []
            for item in page:
                props = dict(item["props"])
                old = _require_uuid(props, "Entität")
                new = mapped_uuid(target_graph_id, "entity", old)
                props["uuid"] = new
                props["graph_id"] = target_graph_id
                entity_rows.append({"uuid": new, "props": props, "labels": list(item["labels"])})
                entity_sources.append(old)
            written["entities"] += storage.duplicate_write_entities(entity_rows)
            after = page[-1]["props"]["uuid"]
            self._progress(
                run_id,
                _scaled(written["entities"], totals.get("entities", 0), 30, 60),
                "Entitäten werden kopiert",
            )

        # Beziehungen erst, wenn alle Entitäten stehen: ein Endpunkt auf einer
        # späteren Seite fehlte sonst im ``MATCH`` der Kopie.
        for start in range(0, len(entity_sources), PAGE_SIZE):
            chunk = entity_sources[start : start + PAGE_SIZE]
            relations = storage.duplicate_read_relations(source_graph_id, chunk)
            relation_rows = []
            for item in relations:
                props = dict(item["props"])
                old = _require_uuid(props, "Beziehung")
                new = mapped_uuid(target_graph_id, "relation", old)
                props["uuid"] = new
                props["graph_id"] = target_graph_id
                episode_ids = props.get("episode_ids")
                if isinstance(episode_ids, list):
                    props["episode_ids"] = [
                        mapped_uuid(target_graph_id, "episode", str(item_id))
                        for item_id in episode_ids
                    ]
                relation_rows.append(
                    {
                        "uuid": new,
                        "source": mapped_uuid(target_graph_id, "entity", item["source"]),
                        "target": mapped_uuid(target_graph_id, "entity", item["target"]),
                        "props": props,
                    }
                )
            written["relations"] += storage.duplicate_write_relations(relation_rows)
            self._progress(
                run_id,
                _scaled(start + len(chunk), len(entity_sources), 60, 90),
                "Beziehungen werden kopiert",
            )
        return written

    def _verify(self, target_graph_id: str, written: Dict[str, int]) -> None:
        """Zählt die Kopie nach: geschrieben ist nicht gleich vorhanden."""
        actual = self._storage.duplicate_count(target_graph_id)
        for key, label in (
            ("entities", "Entitäten"),
            ("relations", "Beziehungen"),
            ("episodes", "Episoden"),
        ):
            if actual.get(key, 0) != written[key]:
                raise GraphDuplicateWriteError(
                    f"Kopie unvollständig: {label} {actual.get(key, 0)} von {written[key]}"
                )

    def _finish(
        self,
        run_id: str,
        target_graph_id: str,
        project_id: str,
        source_props: Dict[str, Any],
    ) -> None:
        self._progress(run_id, 95, "Kopie wird abgeschlossen")
        incomplete = str(source_props.get("status") or "completed") == "incomplete"
        if incomplete:
            self._storage.mark_graph_incomplete(
                target_graph_id, source_props.get("incomplete_reason")
            )
        else:
            self._storage.mark_graph_completed(target_graph_id)

        project = ProjectManager.get_project(project_id)
        if project is None:
            raise GraphDuplicateError("Zielprojekt nicht mehr vorhanden")
        project.status = ProjectStatus.GRAPH_INCOMPLETE if incomplete else ProjectStatus.GRAPH_COMPLETED
        ProjectManager.save_project(project)

        self._registry.update_run(
            run_id,
            status="completed",
            progress=100,
            message="Kopie abgeschlossen",
            termination_reason="completed",
        )

    # ── Projektartefakte ────────────────────────────────────────────

    def _copy_project_artifacts(self, source_project_id: str, target_project_id: str) -> None:
        """Dateien, extrahierter Text und Dokumentmanifest, jeweils atomar."""
        target_files_dir = ProjectManager._get_project_files_dir(target_project_id)
        os.makedirs(target_files_dir, exist_ok=True)
        for path in ProjectManager.get_project_files(source_project_id):
            _copy_file_atomic(path, os.path.join(target_files_dir, os.path.basename(path)))

        text = ProjectManager.get_extracted_text(source_project_id)
        if text is not None:
            _write_text_atomic(ProjectManager._get_project_text_path(target_project_id), text)

        manifest = ProjectManager.get_document_manifest(source_project_id)
        if manifest is not None:
            _write_text_atomic(
                ProjectManager._get_project_documents_path(target_project_id),
                manifest.model_dump_json(indent=2),
            )

    # ── Aufräumen ───────────────────────────────────────────────────

    def _rollback(self, target_graph_id: str, project_id: str) -> List[str]:
        """Entfernt Zielgraph und Zielprojekt. Rückgabe: Teile, die sich nicht entfernen ließen."""
        problems: List[str] = []
        try:
            self._storage.delete_graph(target_graph_id)
        except Exception as exc:  # noqa: BLE001 — wird im Jobfehler sichtbar gemacht
            logger.error("Zielgraph %s ließ sich nicht entfernen: %s", target_graph_id, type(exc).__name__)
            problems.append("Zielgraph")
        try:
            ProjectManager.delete_project(project_id)
        except Exception as exc:  # noqa: BLE001 — wird im Jobfehler sichtbar gemacht
            logger.error("Zielprojekt %s ließ sich nicht entfernen: %s", project_id, type(exc).__name__)
            problems.append("Zielprojekt")
        return problems


def _require_uuid(props: Dict[str, Any], kind: str) -> str:
    value = props.get("uuid")
    if not isinstance(value, str) or not value:
        raise GraphDuplicateWriteError(f"{kind} ohne uuid, Kopie abgebrochen")
    return value


def _scaled(done: int, total: int, low: int, high: int) -> int:
    if total <= 0:
        return high
    return min(high, low + (high - low) * done // total)


def _rewrite_file_entry(entry: Dict[str, Any], target_files_dir: str) -> Dict[str, Any]:
    """Dateieintrag des Quellprojekts mit Pfad im Zielprojekt."""
    rewritten = dict(entry)
    name = entry.get("saved_filename") or os.path.basename(str(entry.get("path") or ""))
    if name:
        rewritten["path"] = os.path.join(target_files_dir, str(name))
    return rewritten


def _ontology_from_graph(source_props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ontologie aus dem Graphknoten, wenn kein Quellprojekt sie führt."""
    raw = source_props.get("ontology_json")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Ontologie des Quellgraphen ist kein gültiges JSON, die Kopie startet ohne")
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


__all__ = [
    "GraphDuplicateError",
    "GraphDuplicateService",
    "GraphDuplicateSourceNotFound",
    "GraphDuplicateSourceStateError",
    "PAGE_SIZE",
    "RUN_TYPE",
    "mapped_uuid",
]
