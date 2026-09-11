"""Supabase-Mirror: idempotenter App-Metadaten-Index (Phase 1).

Rollenverteilung (docs/plans/supabase.md):
- Wahrheit: Dateisystem (Run-Manifeste, Report-Metadaten, Dokument-Manifeste)
  bzw. Neo4j (Graph/Vektoren). Postgres (schema ``agora``) ist nur Index.
- Write-Through: best-effort, asynchron, nie fatal. Ein Supabase-Ausfall
  darf die Pipeline weder blockieren noch brechen.
- Rebuild: ``rebuild_index()`` rekonstruiert den kompletten Index aus der
  Wahrheit — der Beweis, dass der Spiegel beliebig (flag aus/an) ist.

Hooks (Production-Pfade):
- ``RunRegistry._write_run``        -> ``mirror_run``
- ``ReportManager.save_report``     -> ``mirror_report``
- ``api/graph_build.py`` (Upload)   -> ``mirror_documents``
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from ...config import Config
from ...contracts.document_manifest_contract import DocumentManifestEntry
from ...contracts.supabase_mirror_contract import (
    MAX_EVENT_MESSAGE_CHARS,
    DocumentMirrorRecord,
    ReportIndexRecord,
    RunEventMirrorRecord,
    RunMirrorRecord,
)
from ...utils.logger import get_logger
from .client import SupabaseMirrorError, SupabaseRestClient

logger = get_logger("agora.supabase_mirror")

_SHA256_CHUNK = 64 * 1024

# Obergrenze wartender Spiegel-Auftraege. Pro Entitaet (Run, Report, Projekt)
# wartet hoechstens ein Snapshot — neuere ersetzen aeltere derselben Entitaet.
# Erst wenn mehr *verschiedene* Entitaeten anstehen als hier erlaubt, wird
# verworfen (mit Warnung): Der Spiegel ist Index, kein Transaktionslog, und
# der Rebuild schliesst jede so entstandene Luecke.
MAX_PENDING_MIRROR_JOBS = 256


def _utc_now_iso() -> str:
    """Zeitstempel fuer ``mirrored_at`` — eine Uhr fuer Write und Sweep.

    Bewusst nicht der Postgres-Default ``now()``: Der Rebuild-Sweep
    vergleicht ``mirrored_at`` gegen seinen eigenen Startstempel. Kaemen
    Write-Through-Zeilen von der DB-Uhr und der Sweep-Stempel von der
    App-Uhr, wuerde Uhren-Drift frisch gespiegelte Zeilen loeschen.
    """
    return datetime.now(timezone.utc).isoformat()


def _sha256_of_file(path: str) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_SHA256_CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        logger.warning("supabase mirror: sha256 of %s failed: %s", path, exc)
        return None


def _build_run_record(manifest: Dict[str, Any]) -> Optional[RunMirrorRecord]:
    linked = manifest.get("linked_ids") or {}
    metadata = manifest.get("metadata") or {}
    try:
        progress = int(manifest.get("progress") or 0)
        return RunMirrorRecord(
            run_id=manifest.get("run_id") or "",
            run_type=manifest.get("run_type") or "",
            entity_id=manifest.get("entity_id") or "",
            parent_run_id=manifest.get("parent_run_id"),
            status=manifest.get("status") or "pending",
            progress=max(0, min(100, progress)),
            message=manifest.get("message") or "",
            error=manifest.get("error"),
            started_at=manifest.get("started_at") or "",
            updated_at=manifest.get("updated_at") or "",
            completed_at=manifest.get("completed_at"),
            branch_label=manifest.get("branch_label"),
            termination_reason=manifest.get("termination_reason"),
            project_id=linked.get("project_id") or metadata.get("project_id"),
            simulation_id=linked.get("simulation_id") or metadata.get("simulation_id"),
        )
    except ValidationError as exc:
        logger.warning("supabase mirror: run record invalid, skipped (%s)", exc)
        return None


def _build_event_rows(manifest: Dict[str, Any]) -> List[RunEventMirrorRecord]:
    run_id = manifest.get("run_id") or ""
    rows: List[RunEventMirrorRecord] = []
    for seq, event in enumerate(manifest.get("events") or []):
        message = str(event.get("message") or "")
        if len(message) > MAX_EVENT_MESSAGE_CHARS:
            message = message[:MAX_EVENT_MESSAGE_CHARS]
        progress = event.get("progress")
        try:
            rows.append(
                RunEventMirrorRecord(
                    run_id=run_id,
                    seq=seq,
                    occurred_at=event.get("timestamp") or "",
                    event_type=event.get("type") or "updated",
                    status=event.get("status") or manifest.get("status") or "pending",
                    progress=max(0, min(100, int(progress))) if progress is not None else None,
                    message=message,
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            logger.warning("supabase mirror: run event seq=%d invalid, skipped (%s)", seq, exc)
    return rows


def _build_report_record(report_dict: Dict[str, Any]) -> Optional[ReportIndexRecord]:
    report_id = report_dict.get("report_id")
    if not report_id:
        logger.warning("supabase mirror: report record without report_id, skipped")
        return None
    try:
        return ReportIndexRecord(
            report_id=report_id,
            # Kein "unknown"-Fallback: Ein Status ausserhalb des
            # ReportStatus-Vertrags ist kein Spiegelwert, sondern ein Defekt
            # der Wahrheit — die Zeile wird uebersprungen, nicht erfunden.
            status=report_dict.get("status"),
            evidence_ok=bool(report_dict.get("has_evidence")),
            evidence_sections=int(report_dict.get("evidence_sections") or 0),
            artifact_path=f"reports/{report_id}",
            created_at=report_dict.get("created_at"),
            updated_at=report_dict.get("updated_at"),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        logger.warning("supabase mirror: report record invalid, skipped (%s)", exc)
        return None


def _row(record: Any, mirrored_at: str) -> Dict[str, Any]:
    """Contract-Record -> PostgREST-Zeile mit Sweep-Stempel."""
    payload = record.model_dump(mode="json")
    payload["mirrored_at"] = mirrored_at
    return payload


class SupabaseMirror:
    """Async-best-effort Spiegel der App-Metadaten nach Supabase/Postgres."""

    _instance: Optional["SupabaseMirror"] = None
    _instance_lock = threading.Lock()

    _client: Optional[SupabaseRestClient]
    _lock: threading.Lock
    _queue_lock: threading.Lock
    _pending: Dict[str, Callable[[], None]]
    _event_counts: Dict[str, int]
    _executor: ThreadPoolExecutor

    def __new__(cls) -> "SupabaseMirror":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._client = None
                    instance._lock = threading.Lock()
                    # Delta-Tracker: run_id -> Anzahl bereits gespiegelter Events.
                    # Erstkontakt spiegelt alle Events (idempotent via
                    # on_conflict=run_id,seq), danach nur das Delta.
                    instance._event_counts = {}
                    instance._queue_lock = threading.Lock()
                    # Wartende Auftraege pro Entitaets-Key. Der Executor
                    # bekommt nur einen Platzhalter je Key; der Snapshot
                    # dahinter wird bis zur Ausfuehrung ueberschrieben.
                    instance._pending = {}
                    instance._executor = ThreadPoolExecutor(
                        max_workers=1, thread_name_prefix="supabase-mirror"
                    )
                    cls._instance = instance
        return cls._instance

    @property
    def enabled(self) -> bool:
        return bool(
            Config.SUPABASE_ENABLED
            and Config.SUPABASE_URL
            and Config.SUPABASE_SERVICE_ROLE_KEY
        )

    def _get_client(self) -> SupabaseRestClient:
        with self._lock:
            if self._client is None:
                self._client = SupabaseRestClient(
                    Config.SUPABASE_URL,
                    Config.SUPABASE_SERVICE_ROLE_KEY,
                    schema=Config.SUPABASE_SCHEMA,
                    timeout_seconds=Config.SUPABASE_TIMEOUT_SECONDS,
                )
            return self._client

    def reset_for_tests(self) -> None:
        """Test-Helper: Client/Delta-Zustand verwerfen (Singleton im Prozess)."""
        with self._lock:
            self._client = None
            self._event_counts = {}
        with self._queue_lock:
            self._pending = {}

    def _submit(self, fn: Callable[[], None], *, key: str) -> None:
        """Auftrag einreihen — pro Entitaets-Key hoechstens einer wartend.

        ``ThreadPoolExecutor(max_workers=1)`` begrenzt nur die Parallelitaet;
        seine interne Queue ist unbegrenzt. Waehrend ein Upsert bis zum
        Timeout haengt, wuerde jeder weitere Run-/Report-/Dokument-Update
        einen weiteren Snapshot im Speicher halten. Darum wird pro Entitaet
        verdichtet: Der neueste Snapshot ersetzt den wartenden aelteren
        derselben Entitaet — die Wahrheit ist ohnehin kumulativ (Manifest,
        meta.json, Dokument-Manifest), ein uebersprungener Zwischenstand
        geht nicht verloren.
        """
        if not self.enabled:
            return
        with self._queue_lock:
            if key in self._pending:
                self._pending[key] = fn  # verdichtet: nur der neueste Stand zaehlt
                return
            if len(self._pending) >= MAX_PENDING_MIRROR_JOBS:
                logger.warning(
                    "supabase mirror: %d jobs pending, dropping update for %s "
                    "(rebuild closes the gap)",
                    len(self._pending),
                    key,
                )
                return
            self._pending[key] = fn
        try:
            self._executor.submit(self._run_pending, key)
        except RuntimeError:
            # Executor nach Interpreter-Shutdown — Mirror ist best-effort.
            logger.debug("supabase mirror: executor rejected task (shutdown)")
            with self._queue_lock:
                self._pending.pop(key, None)

    def _run_pending(self, key: str) -> None:
        with self._queue_lock:
            fn = self._pending.pop(key, None)
        if fn is not None:
            self._guarded(fn)

    @staticmethod
    def _guarded(fn) -> None:
        try:
            fn()
        except SupabaseMirrorError as exc:
            logger.warning("supabase mirror failed (non-fatal): %s", exc)
        except Exception:  # noqa: BLE001 — Mirror darf die Pipeline nie brechen
            logger.warning("supabase mirror raised (non-fatal)", exc_info=True)

    # ---------------------------------------------------------------- Runs

    def mirror_run(self, manifest: Dict[str, Any]) -> None:
        run_id = manifest.get("run_id")
        if not run_id:
            return
        snapshot = dict(manifest)
        self._submit(lambda: self._mirror_run_sync(snapshot), key=f"run:{run_id}")

    def _mirror_run_sync(
        self,
        manifest: Dict[str, Any],
        *,
        mirrored_at: Optional[str] = None,
        full: bool = False,
    ) -> None:
        record = _build_run_record(manifest)
        if record is None:
            return
        stamp = mirrored_at or _utc_now_iso()
        client = self._get_client()
        client.upsert("runs", [_row(record, stamp)], on_conflict=["run_id"])

        events = _build_event_rows(manifest)
        # Der Rebuild spiegelt immer alle Events: Nur so traegt jede noch
        # gueltige Zeile den Sweep-Stempel und ueberlebt delete_stale().
        seen = 0 if full else self._event_counts.get(record.run_id, 0)
        if seen > len(events):
            seen = 0  # Manifest gekuerzt/neu aufgebaut -> vollstaendig spiegeln
        delta = events[seen:]
        if delta:
            client.upsert(
                "run_events",
                [_row(event, stamp) for event in delta],
                on_conflict=["run_id", "seq"],
            )
        self._event_counts[record.run_id] = len(events)

    # -------------------------------------------------------------- Reports

    def mirror_report(self, report_dict: Dict[str, Any]) -> None:
        snapshot = dict(report_dict)
        self._submit(
            lambda: self._mirror_report_sync(snapshot),
            key=f"report:{snapshot.get('report_id') or ''}",
        )

    def _mirror_report_sync(
        self, report_dict: Dict[str, Any], *, mirrored_at: Optional[str] = None
    ) -> None:
        record = _build_report_record(report_dict)
        if record is None:
            return
        self._get_client().upsert(
            "report_index",
            [_row(record, mirrored_at or _utc_now_iso())],
            on_conflict=["report_id"],
        )

    # ------------------------------------------------------------ Dokumente

    def mirror_documents(
        self,
        project_id: str,
        entries: List[DocumentManifestEntry],
        *,
        file_paths: Optional[Dict[str, str]] = None,
    ) -> None:
        paths = dict(file_paths or {})
        snapshot = list(entries)
        self._submit(
            lambda: self._mirror_documents_sync(project_id, snapshot, paths),
            key=f"documents:{project_id}",
        )

    def _mirror_documents_sync(
        self,
        project_id: str,
        entries: List[DocumentManifestEntry],
        file_paths: Dict[str, str],
        *,
        mirrored_at: Optional[str] = None,
    ) -> None:
        stamp = mirrored_at or _utc_now_iso()
        rows: List[Dict[str, Any]] = []
        for entry in entries:
            try:
                record = DocumentMirrorRecord(
                    project_id=project_id,
                    document_id=entry.document_id,
                    filename=entry.filename,
                )
            except ValidationError as exc:
                logger.warning(
                    "supabase mirror: document record invalid, skipped (%s)", exc
                )
                continue
            # exclude_none: size_bytes/sha256/ingested_at sind abgeleitete
            # Anreicherung — ohne Datei werden die Spalten NICHT geliefert,
            # und PostgREST überschreibt nur gelieferte Spalten (Rebuild
            # nullt damit keine vorhandenen Checksums).
            payload = record.model_dump(mode="json", exclude_none=True)
            payload["mirrored_at"] = stamp
            path = file_paths.get(entry.document_id)
            if path:
                size = None
                try:
                    size = os.path.getsize(path)
                except OSError as exc:
                    logger.warning(
                        "supabase mirror: size of %s unavailable: %s", path, exc
                    )
                if size is not None:
                    payload["size_bytes"] = size
                checksum = _sha256_of_file(path)
                if checksum:
                    payload["sha256"] = checksum
            rows.append(payload)
        if rows:
            self._get_client().upsert(
                "documents",
                rows,
                on_conflict=["project_id", "document_id"],
            )

    # -------------------------------------------------------------- Rebuild

    def rebuild_index(self) -> Dict[str, int]:
        """Voller Index-Neuaufbau aus der Wahrheit (Dateisystem).

        Phase-1-Exit-Kriterium: Der Rebuild beweist, dass Postgres nur
        Spiegel ist — der Zustand ist jederzeit aus Run-Manifesten,
        Report-Metadaten und Dokument-Manifesten rekonstruierbar.
        Dokument-Anreicherungen (size/sha256) werden vom Rebuild NICHT
        geliefert (PostgREST ueberschreibt nur gelieferte Spalten).

        Der Rebuild ist nicht nur additiv: Jede geschriebene Zeile traegt
        den Startstempel dieses Laufs in ``mirrored_at``; danach loescht
        ein Sweep alles Aeltere. Zeilen lokal geloeschter Runs, Reports
        oder Projekte verschwinden damit aus dem Spiegel, statt dauerhaft
        von der Wahrheit abzuweichen.
        """
        if not self.enabled:
            raise SupabaseMirrorError(
                "Supabase mirror is disabled (SUPABASE_ENABLED=false)"
            )
        # Lazy Imports: RunRegistry importiert dieses Modul im Hook-Pfad.
        from ...models.project import ProjectManager
        from ..run_registry import RunRegistry

        counts = {"runs": 0, "run_events": 0, "reports": 0, "documents": 0}
        sweep_stamp = _utc_now_iso()

        registry_dir = RunRegistry.REGISTRY_DIR
        if os.path.isdir(registry_dir):
            for filename in sorted(os.listdir(registry_dir)):
                if not filename.endswith(".json") or filename.startswith("."):
                    continue
                with open(os.path.join(registry_dir, filename), "r", encoding="utf-8") as handle:
                    manifest = json.load(handle)
                self._mirror_run_sync(manifest, mirrored_at=sweep_stamp, full=True)
                counts["runs"] += 1
                counts["run_events"] += len(manifest.get("events") or [])

        reports_dir = os.path.join(Config.UPLOAD_FOLDER, "reports")
        if os.path.isdir(reports_dir):
            for folder in sorted(os.listdir(reports_dir)):
                meta_path = os.path.join(reports_dir, folder, "meta.json")
                if not os.path.isfile(meta_path):
                    continue
                with open(meta_path, "r", encoding="utf-8") as handle:
                    report_dict = json.load(handle)
                self._mirror_report_sync(report_dict, mirrored_at=sweep_stamp)
                counts["reports"] += 1

        # iter_projects statt list_projects(limit=...): ein Limit wuerde den
        # Rebuild stillschweigend nach N Projekten abschneiden und trotzdem
        # "complete" melden.
        for project in ProjectManager.iter_projects():
            manifest = ProjectManager.get_document_manifest(project.project_id)
            if not manifest:
                continue
            self._mirror_documents_sync(
                project.project_id, manifest.documents, {}, mirrored_at=sweep_stamp
            )
            counts["documents"] += len(manifest.documents)

        self._sweep_stale_rows(sweep_stamp)
        return counts

    def _sweep_stale_rows(self, sweep_stamp: str) -> None:
        """Loescht alles, was dieser Rebuild nicht bestaetigt hat.

        ``runs`` zuerst: ``run_events`` haengt per ON DELETE CASCADE daran.
        Der anschliessende Sweep auf ``run_events`` raeumt zusaetzlich
        Events, die aus einem noch existierenden Manifest verschwunden sind.
        """
        client = self._get_client()
        for table in ("runs", "run_events", "report_index", "documents"):
            client.delete_stale(table, mirrored_before=sweep_stamp)


def get_supabase_mirror() -> SupabaseMirror:
    """Prozessweiter Mirror-Singleton (wie RunRegistry)."""
    return SupabaseMirror()
