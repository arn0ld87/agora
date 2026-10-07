"""
Graph API: Handänderungen und Sperrzustand (Issue #1808, ADR-0022).

Routen unter ``/api/graph``:

* ``GET    /<graph_id>/lock`` — Sperrzustand (Scope ``graph:read``)
* ``GET    /<graph_id>/ontology`` — Ontologie und zulässige Entitätstypen (Scope ``graph:read``)
* ``POST   /<graph_id>/entities`` — Entität anlegen (201, bei Wiederholung 200)
* ``PATCH  /<graph_id>/entities/<uuid>`` — Entität ändern
* ``DELETE /<graph_id>/entities/<uuid>`` — Entität samt Beziehungen löschen
* ``POST   /<graph_id>/entities/merge`` — Entitäten zusammenführen
* ``POST   /<graph_id>/relations`` — Beziehung anlegen (201, bei Wiederholung 200)
* ``PATCH  /<graph_id>/relations/<uuid>`` — Beziehung ändern
* ``DELETE /<graph_id>/relations/<uuid>`` — Beziehung löschen

Schreibende Routen verlangen ``graph:write``. Anfragen werden mit den
Pydantic-Modellen aus ``graph_edit_contract`` validiert, Antworten aus den
Ansichtsmodellen serialisiert. Die Fachregeln liegen im ``GraphEditService``.

Fehler: ``graph_locked`` (409, mit ``used_by``), ``graph_edit_conflict``
(409), ``embedding_migration_running`` (409), ``validation_failed`` (400),
``invalid_id`` (400), ``not_found`` (404), ``service_unavailable`` (503, wenn
die Einbettung nicht berechnet werden kann).
"""

from __future__ import annotations

import re
from typing import Callable

from flask import request
from pydantic import BaseModel, ValidationError

from . import graph_bp
from ..container import get_container
from ..contracts.graph_edit_contract import (
    EntityCreate,
    EntityMerge,
    EntityUpdate,
    RelationCreate,
    RelationUpdate,
)
from ..services.graph_edit_service import (
    EmbeddingMigrationRunningError,
    GraphEditConflict,
    GraphEditEmbeddingError,
    GraphEditNotFound,
    GraphEditService,
    GraphEditValidationError,
    embedding_migration_active,
)
from ..services.graph_lock import GraphLockedError, ensure_graph_unlocked, get_graph_lock_state
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.scopes import require_scope
from ..utils.validation import validate_graph_id
from .graph_guard import graph_locked_response

_ELEMENT_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _service() -> GraphEditService:
    return GraphEditService(
        get_container().neo4j_storage,
        lock_check=ensure_graph_unlocked,
        migration_active=embedding_migration_active,
    )


def _parse[M: BaseModel](model: type[M]) -> tuple[M | None, object | None]:
    """Validiert den JSON-Body. Rückgabe ``(Modell, None)`` oder ``(None, Fehlerantwort)``."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, json_error(
            ApiErrorCode.VALIDATION_FAILED, status=400, message="JSON-Objekt als Body erwartet"
        )
    try:
        return model.model_validate(body), None
    except ValidationError as exc:
        return None, json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            extra={"errors": exc.errors(include_url=False)},
        )


def _invalid_id():
    return json_error(ApiErrorCode.INVALID_ID, status=400)


def _run(action: Callable[[], object]):
    """Führt eine Dienstaktion aus und bildet Fachfehler auf die Antwort-Umschläge ab."""
    try:
        return action()
    except GraphLockedError as exc:
        return graph_locked_response(exc)
    except EmbeddingMigrationRunningError:
        return json_error(ApiErrorCode.EMBEDDING_MIGRATION_RUNNING, status=409)
    except GraphEditConflict as exc:
        return json_error(ApiErrorCode.GRAPH_EDIT_CONFLICT, status=409, message=str(exc))
    except GraphEditNotFound:
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message="Element nicht gefunden")
    except GraphEditValidationError as exc:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message=str(exc))
    except GraphEditEmbeddingError:
        return json_error(
            ApiErrorCode.SERVICE_UNAVAILABLE,
            status=503,
            message="Die Einbettung konnte nicht berechnet werden, es wurde nichts geändert",
        )


@graph_bp.route("/<graph_id>/lock", methods=["GET"])
@require_scope("graph:read")
@handle_api_errors
def get_graph_lock(graph_id: str):
    """Sperrzustand: gesperrt, sobald eine Simulation den Graphen oder sein Projekt verwendet."""
    if not validate_graph_id(graph_id):
        return _invalid_id()
    return json_success(get_graph_lock_state(graph_id).model_dump(mode="json"))


@graph_bp.route("/<graph_id>/ontology", methods=["GET"])
@require_scope("graph:read")
@handle_api_errors
def get_graph_ontology(graph_id: str):
    """Liefert die Ontologie und zulässige Entitätstypen des Graphen."""
    if not validate_graph_id(graph_id):
        return _invalid_id()
    types = _service().get_allowed_entity_types(graph_id)
    ontology = get_container().neo4j_storage.get_ontology(graph_id) or {}
    return json_success({"ontology": ontology, "entity_types": types})


@graph_bp.route("/<graph_id>/entities", methods=["POST"])
@require_scope("graph:write")
@handle_api_errors
def create_entity(graph_id: str):
    if not validate_graph_id(graph_id):
        return _invalid_id()
    payload, error = _parse(EntityCreate)
    if error is not None:
        return error
    assert payload is not None

    def _action():
        view, created = _service().create_entity(graph_id, payload)
        return json_success(view.model_dump(mode="json"), status=201 if created else 200)

    return _run(_action)


@graph_bp.route("/<graph_id>/entities/merge", methods=["POST"])
@require_scope("graph:write")
@handle_api_errors
def merge_entities(graph_id: str):
    if not validate_graph_id(graph_id):
        return _invalid_id()
    payload, error = _parse(EntityMerge)
    if error is not None:
        return error
    assert payload is not None

    return _run(
        lambda: json_success(_service().merge_entities(graph_id, payload).model_dump(mode="json"))
    )


@graph_bp.route("/<graph_id>/entities/<entity_uuid>", methods=["PATCH"])
@require_scope("graph:write")
@handle_api_errors
def update_entity(graph_id: str, entity_uuid: str):
    if not validate_graph_id(graph_id) or not _ELEMENT_UUID_RE.match(entity_uuid):
        return _invalid_id()
    payload, error = _parse(EntityUpdate)
    if error is not None:
        return error
    assert payload is not None

    return _run(
        lambda: json_success(
            _service().update_entity(graph_id, entity_uuid, payload).model_dump(mode="json")
        )
    )


@graph_bp.route("/<graph_id>/entities/<entity_uuid>", methods=["DELETE"])
@require_scope("graph:write")
@handle_api_errors
def delete_entity(graph_id: str, entity_uuid: str):
    if not validate_graph_id(graph_id) or not _ELEMENT_UUID_RE.match(entity_uuid):
        return _invalid_id()
    return _run(
        lambda: json_success(_service().delete_entity(graph_id, entity_uuid).model_dump(mode="json"))
    )


@graph_bp.route("/<graph_id>/relations", methods=["POST"])
@require_scope("graph:write")
@handle_api_errors
def create_relation(graph_id: str):
    if not validate_graph_id(graph_id):
        return _invalid_id()
    payload, error = _parse(RelationCreate)
    if error is not None:
        return error
    assert payload is not None

    def _action():
        view, created = _service().create_relation(graph_id, payload)
        return json_success(view.model_dump(mode="json"), status=201 if created else 200)

    return _run(_action)


@graph_bp.route("/<graph_id>/relations/<relation_uuid>", methods=["PATCH"])
@require_scope("graph:write")
@handle_api_errors
def update_relation(graph_id: str, relation_uuid: str):
    if not validate_graph_id(graph_id) or not _ELEMENT_UUID_RE.match(relation_uuid):
        return _invalid_id()
    payload, error = _parse(RelationUpdate)
    if error is not None:
        return error
    assert payload is not None

    return _run(
        lambda: json_success(
            _service().update_relation(graph_id, relation_uuid, payload).model_dump(mode="json")
        )
    )


@graph_bp.route("/<graph_id>/relations/<relation_uuid>", methods=["DELETE"])
@require_scope("graph:write")
@handle_api_errors
def delete_relation(graph_id: str, relation_uuid: str):
    if not validate_graph_id(graph_id) or not _ELEMENT_UUID_RE.match(relation_uuid):
        return _invalid_id()
    return _run(
        lambda: json_success(
            _service().delete_relation(graph_id, relation_uuid).model_dump(mode="json")
        )
    )
