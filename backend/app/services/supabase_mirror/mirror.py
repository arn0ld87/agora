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
from typing import Any, Dict, List, Optional

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
            status=report_dict.get("status") or "unknown",
            evidence_ok=bool(report_dict.get("has_evidence")),
            evidence_sections=int(report_dict.get("evidence_sections") or 0),
            artifact_path=f"reports/{report_id}",
            created_at=report_dict.get("created_at"),
            updated_at=report_dict.get("updated_at"),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        logger.warning("supabase mirror: report record invalid, skipped (%s)", exc)
        return None


class SupabaseMirror:
    """Async-best-effort Spiegel der App-Metadaten nach Supabase/Postgres."""

    _instance: Optional["SupabaseMirror"] = None
    _instance_lock = threading.Lock()

    _client: Optional[SupabaseRestClient]
    _lock: threading.Lock
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

    def _submit(self, fn) -> None:
        if not self.enabled:
            return
        try:
            self._executor.submit(self._guarded, fn)
        except RuntimeError:
            # Executor nach Interpreter-Shutdown — Mirror ist best-effort.
            logger.debug("supabase mirror: executor rejected task (shutdown)")

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
        if not manifest.get("run_id"):
            return
        self._submit(lambda: self._mirror_run_sync(dict(manifest)))

    def _mirror_run_sync(self, manifest: Dict[str, Any]) -> None:
        record = _build_run_record(manifest)
        if record is None:
            return
        client = self._get_client()
        client.upsert("runs", [record.model_dump()], on_conflict=["run_id"])

        events = _build_event_rows(manifest)
        seen = self._event_counts.get(record.run_id, 0)
        if seen > len(events):
            seen = 0  # Manifest gekuerzt/neu aufgebaut -> vollstaendig spiegeln
        delta = events[seen:]
        if delta:
            client.upsert(
                "run_events",
                [event.model_dump() for event in delta],
                on_conflict=["run_id", "seq"],
            )
        self._event_counts[record.run_id] = len(events)

    # -------------------------------------------------------------- Reports

    def mirror_report(self, report_dict: Dict[str, Any]) -> None:
        self._submit(lambda: self._mirror_report_sync(dict(report_dict)))

    def _mirror_report_sync(self, report_dict: Dict[str, Any]) -> None:
        record = _build_report_record(report_dict)
        if record is None:
            return
        self._get_client().upsert(
            "report_index", [record.model_dump()], on_conflict=["report_id"]
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
        self._submit(
            lambda: self._mirror_documents_sync(project_id, list(entries), paths)
        )

    def _mirror_documents_sync(
        self,
        project_id: str,
        entries: List[DocumentManifestEntry],
        file_paths: Dict[str, str],
    ) -> None:
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
            payload = record.model_dump(exclude_none=True)
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
        """
        if not self.enabled:
            raise SupabaseMirrorError(
                "Supabase mirror is disabled (SUPABASE_ENABLED=false)"
            )
        # Lazy Imports: RunRegistry importiert dieses Modul im Hook-Pfad.
        from ...models.project import ProjectManager
        from ..run_registry import RunRegistry

        counts = {"runs": 0, "run_events": 0, "reports": 0, "documents": 0}

        registry_dir = RunRegistry.REGISTRY_DIR
        if os.path.isdir(registry_dir):
            for filename in sorted(os.listdir(registry_dir)):
                if not filename.endswith(".json") or filename.startswith("."):
                    continue
                with open(os.path.join(registry_dir, filename), "r", encoding="utf-8") as handle:
                    manifest = json.load(handle)
                self._mirror_run_sync(manifest)
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
                self._mirror_report_sync(report_dict)
                counts["reports"] += 1

        for project in ProjectManager.list_projects(limit=1000):
            manifest = ProjectManager.get_document_manifest(project.project_id)
            if not manifest:
                continue
            self._mirror_documents_sync(project.project_id, manifest.documents, {})
            counts["documents"] += len(manifest.documents)

        return counts


def get_supabase_mirror() -> SupabaseMirror:
    """Prozessweiter Mirror-Singleton (wie RunRegistry)."""
    return SupabaseMirror()
