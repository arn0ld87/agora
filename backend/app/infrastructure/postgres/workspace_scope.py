"""Workspace-Bindung der PostgreSQL-Adapter (ADR-0018, Issue #1614).

Jede Metadaten-Zeile gehört genau einem Workspace (``workspace_id``). Welcher
Workspace gilt, hängt davon ab, wer fragt:

* **Im Request** gilt der Workspace des Principals, den der Guard abgelegt
  hat. Fehlt der Principal im Tenant-Modus (Supabase-JWT aktiv), ist das ein
  Programmierfehler (:class:`WorkspaceScopeMissing`), kein stiller Default.
  Ohne Tenant-Modus ist Agora einmandantig; dann gilt der System-Kontext. Gelesen, gelöscht
  und aktualisiert wird nur im eigenen Workspace; eine Zeile eines fremden
  Workspace ist für diesen Request nicht vorhanden.
* **Außerhalb eines Requests** — Hintergrund-Threads (Simulationslauf,
  Report-Erzeugung), Start-Reconciliation, Migrationsskripte — gilt der
  System-Kontext: Lesen ungefiltert, eine neue Zeile erbt den Workspace
  ihres Elternteils (Projekt → Simulation → Run/Report), ein Projekt ohne
  Elternteil landet im Default-Workspace. Diese Pfade kennen ihre Kennungen
  bereits aus einem Request.

Die RLS-Policies aus #1615 sind die zweite Schranke; diese Filter bleiben
(Plan §17, Defense in Depth).
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from flask import has_request_context

from ...contracts.workspace_contract import DEFAULT_WORKSPACE_ID
from ...security.principal_context import current_principal, tenant_mode_active


class WorkspaceScopeMissing(RuntimeError):
    """Ein Request ohne Principal greift auf workspace-gebundene Daten zu."""


class RecordInOtherWorkspace(LookupError):
    """Die Kennung gehört einem anderen Workspace als dem des Requests.

    Für den Aufrufer dasselbe wie „nicht vorhanden“; die Meldung nennt den
    fremden Workspace nicht.
    """


def active_workspace_id() -> Optional[UUID]:
    """Workspace des Requests, ``None`` im System-Kontext."""
    if not has_request_context():
        return None
    principal = current_principal()
    if principal is not None:
        return principal.workspace_id
    if tenant_mode_active():
        raise WorkspaceScopeMissing(
            'request without principal accessed workspace-scoped metadata'
        )
    return None


def visible[R](row: Optional[R], workspace_id: Optional[UUID]) -> Optional[R]:
    """``row``, wenn sie im Workspace liegt (oder System-Kontext), sonst ``None``."""
    if row is None or workspace_id is None:
        return row
    return row if row.workspace_id == workspace_id else None  # type: ignore[attr-defined]


def scoped(query: Any, model: Any, workspace_id: Optional[UUID]) -> Any:
    """``query`` auf den Workspace eingeschränkt; im System-Kontext unverändert."""
    if workspace_id is None:
        return query
    return query.where(model.workspace_id == workspace_id)


def workspace_for_write(
    session: Any,
    existing: Any,
    workspace_id: Optional[UUID],
    *,
    parent_model: Any = None,
    parent_id: Optional[str] = None,
    record_label: str = 'record',
) -> UUID:
    """Workspace, unter dem eine Zeile geschrieben wird.

    * Eine bestehende Zeile behält ihren Workspace. Gehört sie im Request
      einem anderen, ist das :class:`RecordInOtherWorkspace` — kein Upsert
      über die Grenze.
    * Eine neue Zeile nimmt den Workspace des Requests, sonst den des
      Elternteils, sonst den Default-Workspace.
    """
    if existing is not None:
        if workspace_id is not None and existing.workspace_id != workspace_id:
            raise RecordInOtherWorkspace(f'{record_label} does not exist in this workspace')
        return existing.workspace_id
    if workspace_id is not None:
        return workspace_id
    if parent_model is not None and parent_id:
        parent = session.get(parent_model, parent_id)
        if parent is not None:
            return parent.workspace_id
    return DEFAULT_WORKSPACE_ID


# -- Verweise in Requests (zentrale Prüfung im Guard) ---------------------------


#: Zustand eines Verweises aus Sicht eines Workspace.
REFERENCE_OWN = 'own'
REFERENCE_FOREIGN = 'foreign'
REFERENCE_UNKNOWN = 'unknown'


def reference_state(kind: str, value: str, workspace_id: UUID) -> str:
    """``own``, ``foreign`` oder ``unknown`` für die Ressource ``value``.

    ``unknown`` heißt: in keinem Workspace gespeichert — etwa ein Report,
    dessen Metadaten erst der Worker am Ende schreibt (Codex-Review auf #1623).
    """
    from sqlalchemy import or_, select

    from .models.project import ProjectModel
    from .models.report import ReportModel
    from .models.run import RunModel
    from .models.simulation import SimulationModel
    from .session import get_database

    if kind == 'project_id':
        query = select(ProjectModel.workspace_id).where(ProjectModel.id == value)
    elif kind == 'graph_id':
        query = select(ProjectModel.workspace_id).where(ProjectModel.graph_id == value)
    elif kind in ('simulation_id', 'sim_id'):
        query = select(SimulationModel.workspace_id).where(SimulationModel.id == value)
    elif kind == 'run_id':
        query = select(RunModel.workspace_id).where(RunModel.id == value)
    elif kind == 'report_id':
        # Ablageschlüssel oder Kennung im Datensatz (Altbestand, #1607).
        query = select(ReportModel.workspace_id).where(
            or_(ReportModel.id == value, ReportModel.report_id == value)
        )
    else:
        raise ValueError(f'unknown reference kind: {kind}')
    with get_database().session() as session:
        owners = set(session.scalars(query.limit(5)).all())
    if not owners:
        return REFERENCE_UNKNOWN
    return REFERENCE_OWN if owners == {workspace_id} else REFERENCE_FOREIGN


def reference_visible(kind: str, value: str, workspace_id: UUID) -> bool:
    """Liegt die Ressource gespeichert im Workspace?"""
    return reference_state(kind, value, workspace_id) == REFERENCE_OWN
