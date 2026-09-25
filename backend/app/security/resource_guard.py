"""Zentrale Prüfung von Ressourcen-Verweisen für Supabase-Nutzer (ADR-0018, #1614).

Die Repositories filtern nach Workspace. Viele Endpunkte lesen aber zusätzlich
Dateien — Report-Inhalte, Projekt-Uploads, Simulationsartefakte — über die
Kennung aus dem Request, und Neo4j-Graphen über die ``graph_id``. Damit eine
fremde Kennung dort nie ankommt, prüft der Guard **vor** jeder View alle
Verweise im Pfad, in der Query und im JSON-Body gegen den Workspace des
Principals. Eine fremde oder unbekannte Kennung ergibt 404, ohne zu verraten,
ob sie anderswo existiert.

Das gilt nur für JWT-Principals. Betreiber (Master-Token, ``ago_``-Keys)
arbeiten im Default-Workspace und sind vertrauenswürdig.
"""

from __future__ import annotations

from typing import Iterator, Optional
from uuid import UUID

from flask import request

#: Schlüssel, deren Wert eine Kennung einer workspace-gebundenen Ressource ist.
REFERENCE_KEYS: tuple[str, ...] = (
    'project_id',
    'graph_id',
    'simulation_id',
    'sim_id',
    'run_id',
    'report_id',
)

#: Listen solcher Kennungen im Body (z. B. Vergleiche, Batch-Aufrufe).
_LIST_KEYS: dict[str, str] = {
    'project_ids': 'project_id',
    'simulation_ids': 'simulation_id',
    'run_ids': 'run_id',
    'report_ids': 'report_id',
}


def _from_mapping(source: object) -> Iterator[tuple[str, str]]:
    if not hasattr(source, 'get'):
        return
    for key in REFERENCE_KEYS:
        value = source.get(key)  # type: ignore[attr-defined]
        if isinstance(value, str) and value:
            yield key, value
    for list_key, kind in _LIST_KEYS.items():
        values = source.get(list_key)  # type: ignore[attr-defined]
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value:
                    yield kind, value


def references_in(source: object) -> list[tuple[str, str]]:
    """Verweise in einem beliebigen Mapping (etwa Task-Metadaten)."""
    return list(dict.fromkeys(_from_mapping(source)))


def request_references() -> list[tuple[str, str]]:
    """Alle Verweise des laufenden Requests, ohne Duplikate."""
    found: dict[tuple[str, str], None] = {}
    for source in (request.view_args or {}, request.args):
        for ref in _from_mapping(source):
            found.setdefault(ref, None)
    if request.is_json:
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            for ref in _from_mapping(body):
                found.setdefault(ref, None)
    return list(found)


#: Verweise, die vor ihrer Speicherung schon abgefragt werden: ein Report
#: existiert bis zum Ende der Erzeugung nur als Dateien, und sein Besitzer
#: fragt Fortschritt und Abschnitte ab. Eine unbekannte ``report_id`` ist
#: deshalb erlaubt; eine fremde nie. Die Kennung ist zufällig (48 Bit).
_MAY_BE_PENDING = frozenset({'report_id'})


def _reference_allowed(kind: str, value: str, workspace_id: UUID) -> bool:
    from ..infrastructure.postgres.workspace_scope import (
        REFERENCE_OWN,
        REFERENCE_UNKNOWN,
        reference_state,
    )

    state = reference_state(kind, value, workspace_id)
    if state == REFERENCE_OWN:
        return True
    return state == REFERENCE_UNKNOWN and kind in _MAY_BE_PENDING


def task_visible(metadata: object, workspace_id: UUID) -> bool:
    """Ein Task gehört dem Workspace, wenn mindestens ein gespeicherter
    Verweis dort liegt und keiner in einem anderen. Noch nicht gespeicherte
    Verweise (etwa die ``report_id`` eines laufenden Reports) zählen nicht
    gegen ihn (Codex-Review auf #1623)."""
    from ..infrastructure.postgres.workspace_scope import (
        REFERENCE_FOREIGN,
        REFERENCE_OWN,
        reference_state,
    )

    states = {reference_state(kind, value, workspace_id) for kind, value in references_in(metadata)}
    return REFERENCE_OWN in states and REFERENCE_FOREIGN not in states


def _request_task_ids() -> list[str]:
    found: dict[str, None] = {}
    sources: list[object] = [request.view_args or {}, request.args]
    if request.is_json:
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            sources.append(body)
    for source in sources:
        value = source.get('task_id') if hasattr(source, 'get') else None  # type: ignore[attr-defined]
        if isinstance(value, str) and value:
            found.setdefault(value, None)
    return list(found)


def _tasks_allowed(workspace_id: UUID) -> bool:
    """Jeder ``task_id`` im Request gehört dem Workspace. Ein unbekannter Task
    bleibt der View überlassen (sie antwortet 404)."""
    task_ids = _request_task_ids()
    if not task_ids:
        return True
    from ..models.task import TaskManager

    manager = TaskManager()
    for task_id in task_ids:
        task = manager.get_task(task_id)
        if task is not None and not task_visible(task.metadata, workspace_id):
            return False
    return True


def first_foreign_reference(workspace_id: UUID) -> Optional[tuple[str, str]]:
    """Der erste Verweis, der nicht zum Workspace gehört, oder ``None``.

    Prüft Ressourcen-Kennungen (Pfad, Query, Body) und ``task_id``s: In-Memory-
    Tasks tragen Fortschritt, Ergebnis und Fehlertexte (Codex-Review auf #1623).
    """
    for kind, value in request_references():
        if not _reference_allowed(kind, value, workspace_id):
            return kind, value
    if not _tasks_allowed(workspace_id):
        return 'task_id', '*'
    return None
