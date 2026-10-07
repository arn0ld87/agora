"""
Graph API: Graph duplizieren (Issue #1808, Etappe 8, ADR-0022 §6).

Route unter ``/api/graph``:

* ``POST /<graph_id>/duplicate`` — Kopierauftrag anlegen (Scope ``graph:write``)

Body: ``GraphDuplicateRequest`` (``client_request_id``, ``name``). Antwort:
``202`` mit ``GraphDuplicateJob``. Eine Wiederholung mit derselben
``client_request_id`` liefert denselben Job (ebenfalls ``202``), nie eine
zweite Kopie. Fortschritt und Endzustand liefert ``GET /api/runs/<run_id>``
(``run_type='graph_duplicate'``).

Duplizieren ist auch aus einem gesperrten Graphen erlaubt: es liest die
Quelle nur. Fehler: ``validation_failed`` (400, Body oder ein fehlgeschlagener
Quellgraph), ``invalid_id`` (400), ``not_found`` (404, Quellgraph),
``graph_build_in_progress`` (409, Quelle wird gerade gebaut),
``embedding_migration_running`` (409).
"""

from __future__ import annotations

from typing import Callable

from . import graph_bp
from ..container import get_container
from ..contracts.graph_edit_contract import GraphDuplicateRequest
from ..services.graph_duplicate_service import (
    GraphDuplicateService,
    GraphDuplicateSourceNotFound,
    GraphDuplicateSourceStateError,
)
from ..services.graph_edit_service import EmbeddingMigrationRunningError
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.scopes import require_scope
from ..utils.validation import validate_graph_id
from .graph_edit import _invalid_id, _parse


def _service() -> GraphDuplicateService:
    return GraphDuplicateService(get_container().neo4j_storage)


def _run(action: Callable[[], object]):
    """Führt eine Dienstaktion aus und bildet Fachfehler auf die Antwort-Umschläge ab."""
    try:
        return action()
    except GraphDuplicateSourceNotFound:
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message="Graph nicht gefunden")
    except GraphDuplicateSourceStateError as exc:
        if exc.status == "building":
            return json_error(ApiErrorCode.GRAPH_BUILD_IN_PROGRESS, status=409)
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message=str(exc))
    except EmbeddingMigrationRunningError:
        return json_error(ApiErrorCode.EMBEDDING_MIGRATION_RUNNING, status=409)


@graph_bp.route("/<graph_id>/duplicate", methods=["POST"])
@require_scope("graph:write")
@handle_api_errors
def duplicate_graph(graph_id: str):
    """Legt einen Kopierauftrag an. Die Kopie ist ein neues, nicht gesperrtes Projekt."""
    if not validate_graph_id(graph_id):
        return _invalid_id()
    payload, error = _parse(GraphDuplicateRequest)
    if error is not None:
        return error
    assert payload is not None

    return _run(
        lambda: json_success(
            _service().start(graph_id, payload).model_dump(mode="json"), status=202
        )
    )
