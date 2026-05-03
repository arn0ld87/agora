"""
Runs-Contract v1 (Pydantic v2).

Kanonische Status-Werte spiegeln RunRegistry.canonical_status()-Ausgabe:
  pending | processing | paused | completed | failed | stopped

Kein "running", "queued", "cancelled" o.ä. auf diesem Layer — die Registry
normalisiert Roh-Inputs auf die obige Menge (vgl. run_registry.py:47-67).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Exakt die kanonischen Ausgabewerte aus RunRegistry.canonical_status()
RunStatus = Literal["pending", "processing", "paused", "completed", "failed", "stopped"]

_STRICT = ConfigDict(extra="forbid")


class RunSummary(BaseModel):
    """Lesepfad-Anreicherung: Felder aus Projekt + Simulation (N+1-gecacht)."""

    model_config = _STRICT

    model: Optional[str] = None
    document_name: Optional[str] = None
    persona_count: Optional[int] = None
    graph_id: Optional[str] = None
    graph_name: Optional[str] = None
    branch_name: Optional[str] = None


class RunDetail(BaseModel):
    """Vollständige Run-Repräsentation mit optionalen Live-Metriken."""

    model_config = ConfigDict(extra="allow")  # Manifest kann weitere Felder haben

    run_id: str
    run_type: str
    entity_id: str
    parent_run_id: Optional[str] = None
    status: RunStatus
    progress: int = Field(ge=0, le=100)
    message: str = ""
    error: Optional[str] = None
    started_at: str
    updated_at: str
    completed_at: Optional[str] = None
    branch_label: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    linked_ids: dict = Field(default_factory=dict)
    artifacts: dict = Field(default_factory=dict)
    resume_capability: dict = Field(default_factory=dict)

    # Read-path Anreicherung
    summary: Optional[RunSummary] = None

    # Live-Metriken (Sub-Slice 33, Layer 7)
    # eta_seconds: aus RunRegistry-Metadaten, falls vorhanden
    eta_seconds: Optional[int] = None
    # log_tail: letzte Events als kurze Nachricht-Liste (kein separater I/O-Pfad)
    log_tail: Optional[list[str]] = None
    # metrics: beliebige numerische/String-Kennzahlen aus dem Manifest
    metrics: Optional[dict[str, float | int | str]] = None


class RunsAggregation(BaseModel):
    """Status-Aggregation: Anzahl je kanonischem Status + Gesamtsumme."""

    model_config = _STRICT

    counts: dict[str, int]
    total: int


class RunsListResponse(BaseModel):
    """Normierter List-Response für GET /api/runs."""

    model_config = _STRICT

    runs: list[RunDetail]
    total: int
    aggregation: Optional[RunsAggregation] = None


class RunsFilterQuery(BaseModel):
    """Validierte Query-Parameter für GET /api/runs.

    Mehrfach-Status: ?status=processing&status=pending
    ODER kommagetrennt: ?status=processing,pending
    (Beide Varianten werden in list_runs() vor Validierung geparst.)
    """

    model_config = _STRICT

    status: Optional[list[RunStatus]] = None
    simulation_id: Optional[str] = None
    since: Optional[datetime] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
    aggregate: Optional[Literal["status"]] = None
