"""Supabase-Mirror-Contracts (Pydantic v2).

Spiegel-Records fuer den App-Metadaten-Index im self-hosted Supabase
(Schema ``agora``). Die Mirror-Tabellen sind ein abfragbarer Index —
die Wahrheit bleibt im Dateisystem (Run-Manifeste, Report-Metadaten,
Dokument-Manifeste) bzw. in Neo4j (Graph/Vektoren). Ein Rebuild aus der
Wahrheit muss dieselben Records erzeugen
(``app.services.supabase_mirror.rebuild``).

Bewusste Entscheidungen:
- Quell-Zeitstempel bleiben ISO-Text (naive Europe/Berlin-Strings aus
  RunRegistry/Report-Metadaten). Nur ``mirrored_at`` setzt der
  Postgres-Server selbst (DDL-Default ``now()``).
- Kein API-Surface: Diese Contracts haben keinen Zod-Spiegel, weil das
  Frontend sie nie sieht. Sie definieren die Spiegelzeilen fuer das
  Backend (service_role-only).

Aufruf zum Schema-Dump:
  cd backend && uv run python -m app.contracts.dump_schemas
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.runs_contract import RunStatus

_STRICT = ConfigDict(extra="forbid")

# Event-Message wird im Spiegel hart gekuerzt — run_events ist Status-Metrik,
# kein Prompt-/Dokumentinhaltsträger (Phase-0-Vertrag: payload-frei).
MAX_EVENT_MESSAGE_CHARS = 1000


class RunMirrorRecord(BaseModel):
    """Eine Zeile in ``agora.runs`` — Snapshot eines RunRegistry-Manifests."""

    model_config = _STRICT

    run_id: str
    run_type: str
    entity_id: str
    parent_run_id: Optional[str] = None
    status: RunStatus
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    error: Optional[str] = None
    started_at: str
    updated_at: str
    completed_at: Optional[str] = None
    branch_label: Optional[str] = None
    termination_reason: Optional[str] = None
    project_id: Optional[str] = None
    simulation_id: Optional[str] = None


class RunEventMirrorRecord(BaseModel):
    """Eine Zeile in ``agora.run_events`` — append-only Realtime-Quelle (Phase 2)."""

    model_config = _STRICT

    run_id: str
    seq: int = Field(..., ge=0, description="Event-Index innerhalb des Runs, beginnend bei 0.")
    occurred_at: str
    event_type: str
    status: RunStatus
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    message: str = ""


class ReportIndexRecord(BaseModel):
    """Eine Zeile in ``agora.report_index`` — Metadaten-Zeiger auf das Artefakt.

    ``artifact_path`` ist bewusst relativ (``reports/<report_id>``) — der
    Report-Content selbst bleibt im Dateisystem (Evidence-Commit-Modell).
    """

    model_config = _STRICT

    report_id: str
    status: str = Field(..., description="Report-Status inkl. INCOMPLETE (ReportStatus-Werte).")
    evidence_ok: bool = False
    evidence_sections: int = Field(default=0, ge=0)
    artifact_path: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentMirrorRecord(BaseModel):
    """Eine Zeile in ``agora.documents`` — Ingest-Index eines Projektdokuments.

    ``size_bytes``/``sha256`` sind abgeleitete Anreicherung aus dem
    Upload-Pfad; der Rebuild laesst sie bewusst weg (PostgREST ueberschreibt
    nur gelieferte Spalten), damit vorhandene Werte einen Rebuild ueberleben.
    """

    model_config = _STRICT

    project_id: str
    document_id: str
    filename: str
    size_bytes: Optional[int] = Field(default=None, ge=0)
    sha256: Optional[str] = None
    ingested_at: Optional[str] = None
