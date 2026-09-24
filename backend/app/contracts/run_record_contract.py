"""Persistenz-Vertrag für Run-Registry-Einträge (#1579).

``RunRecord`` ist das kanonische Modell für das, was unter
``uploads/run_registry/<run_id>.json`` gespeichert wird.  Es unterscheidet
sich bewusst von ``RunDetail`` (API-Lesepfad in ``runs_contract.py``):

- ``events`` und ``replayed_from_run_id`` sind Bestandteile des gespeicherten
  Manifests, aber keine API-Antwortfelder.
- Anreicherungsfelder wie ``summary``, ``eta_seconds``, ``log_tail`` oder
  ``budget`` sind Lesepfad-Zusätze und gehören NICHT hierher.

Lease-Felder (``worker_pid``, ``worker_token``, ``heartbeat_at``,
``lease_ttl_s``) sind Runtime-State und landen in ``metadata`` — sie tauchen
bewusst nicht als Top-Level-Felder auf.  ``JobLease.to_metadata()`` /
``JobLease.from_metadata()`` sind die einzigen Lese-/Schreibpfade dafür
(``app/contracts/job_lease_contract.py``).

``extra="allow"`` sichert Vorwärtskompatibilität: Manifeste aus einer neueren
Agora-Version mit zusätzlichen Feldern bleiben lesbar, ohne dass jedes Feld
explizit deklariert sein muss.

Dieser Vertrag wird NICHT in ``dump_schemas.CONTRACTS`` geführt — er ist ein
interner Persistenzvertrag und überquert die HTTP-API-Grenze nicht als
eigenständiger Response-Body.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field



class RunRecord(BaseModel):
    """Vollständiges, persistiertes Run-Manifest.

    Enthält alle Felder, die ``RunRegistry.create_run`` in das JSON-Manifest
    schreibt.  Kein Feld darf beim Roundtrip (``RunRecord(**d).to_manifest()``)
    verloren gehen.
    """

    model_config = ConfigDict(extra="allow")

    # Kernidentität
    run_id: str = Field(..., min_length=1)
    # Nachsichtig wie der bisherige Dict-Pfad: die Ablage enthaelt Manifeste
    # aus frueheren Programmstaenden. Ein Pflichtfeld, eine Literal-Pruefung
    # auf ``status`` oder eine Bereichsgrenze auf ``progress`` machte aus
    # jedem abweichenden Altbestand einen "fehlenden" Run — er verschwaende
    # still aus ``list_runs``. Die Kanonisierung von ``status`` bleibt Sache
    # von ``RunRegistry.canonical_status`` beim Schreiben.
    run_type: Optional[str] = None
    entity_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    replayed_from_run_id: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    message: Optional[str] = None
    message_key: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    branch_label: Optional[str] = None
    termination_reason: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    resume_capability: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    linked_ids: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)

    def to_manifest(self) -> dict[str, Any]:
        """Das Manifest genau so, wie es gesetzt wurde.

        ``exclude_unset`` statt ``model_dump()``: sonst stuende jeder nicht
        gesetzte Vorgabewert (``None``, ``{}``) danach in der Datei und in den
        API-Antworten, die das Manifest durchreichen — ein stiller Formatwechsel
        der Ablage.
        """
        return self.model_dump(exclude_unset=True)
