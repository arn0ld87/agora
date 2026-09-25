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


def first_foreign_reference(workspace_id: UUID) -> Optional[tuple[str, str]]:
    """Der erste Verweis, der nicht im Workspace liegt, oder ``None``."""
    from ..infrastructure.postgres.workspace_scope import reference_visible

    for kind, value in request_references():
        if not reference_visible(kind, value, workspace_id):
            return kind, value
    return None
