"""Personasaetze als Bibliotheksobjekt: ``/api/persona-sets`` (Issue #1807).

Duenne HTTP-Schicht ueber ``services.persona_set_service``. Anfragen werden
gegen die Pydantic-Modelle aus ``contracts/persona_set_contract.py`` geprueft,
Antworten aus denselben Modellen serialisiert. Fehler laufen ueber den
bestehenden Envelope (``json_error``):

* ``404 not_found`` — unbekannter Satz oder Eintrag
* ``409 persona_set_locked`` — der Satz ist gesperrt (ein Lauf ist daraus
  entstanden); nur Name/Beschreibung sind aenderbar, sonst nur Duplizieren
* ``409 conflict`` — ``username`` kommt im Satz schon vor
* ``400 validation_failed`` — Anfrage verletzt den Vertrag

Zugriffsschutz wie die alten Persona-Bibliotheks-Endpunkte
(``/api/simulation/persona-library``): Blueprint-Guard plus ``operator_only``.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Type, TypeVar

from flask import Blueprint, request
from pydantic import BaseModel, ValidationError

from ..contracts.persona_set_contract import (
    PersonaSetCreate,
    PersonaSetDeleteResponse,
    PersonaSetDuplicate,
    PersonaSetEntriesDelete,
    PersonaSetEntriesDeleteResponse,
    PersonaSetEntryCreate,
    PersonaSetEntryUpdate,
    PersonaSetListResponse,
    PersonaSetUpdate,
)
from ..services.persona_set_service import (
    PersonaSetConflict,
    PersonaSetEmpty,
    PersonaSetEntryNotFound,
    PersonaSetLocked,
    PersonaSetNotFound,
    PersonaSetService,
)
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.auth import operator_only
from ..utils.logger import get_logger

logger = get_logger("agora.api.persona_sets")

persona_sets_bp = Blueprint("persona_sets", __name__)

_M = TypeVar("_M", bound=BaseModel)


def _parse(model: Type[_M]) -> _M:
    """Liest den JSON-Body als ``model``; ``ValidationError`` faengt ``_view`` ab."""
    return model.model_validate(request.get_json(silent=True) or {})


def _view(log_prefix: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Uebersetzt fachliche Fehler des Dienstes in den API-Envelope.

    Ein unerwarteter Fehler faellt an ``handle_api_errors`` (500, Details nur im
    Log).
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(view)
        def mapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return view(*args, **kwargs)
            except ValidationError as exc:
                return json_error(
                    ApiErrorCode.VALIDATION_FAILED,
                    status=400,
                    extra={"errors": exc.errors(include_url=False, include_context=False)},
                )
            except PersonaSetNotFound as exc:
                return json_error(
                    ApiErrorCode.NOT_FOUND,
                    status=404,
                    message=f"Persona set not found: {exc}",
                )
            except PersonaSetEntryNotFound as exc:
                return json_error(
                    ApiErrorCode.NOT_FOUND,
                    status=404,
                    message=f"Persona set entry not found: {exc}",
                )
            except PersonaSetLocked as exc:
                return json_error(
                    ApiErrorCode.PERSONA_SET_LOCKED,
                    status=409,
                    message=(
                        f"Persona set {exc} is locked because a run was created "
                        "from it; duplicate it to change its personas"
                    ),
                )
            except PersonaSetConflict as exc:
                return json_error(ApiErrorCode.CONFLICT, status=409, message=str(exc))
            except PersonaSetEmpty as exc:
                return json_error(
                    ApiErrorCode.VALIDATION_FAILED,
                    status=400,
                    message=f"Persona set {exc} has no personas",
                )

        return handle_api_errors(log_prefix=log_prefix)(mapped)

    return decorator


@persona_sets_bp.route("", methods=["GET"])
@operator_only
@_view("Failed to list persona sets")
def list_persona_sets():
    """Alle Saetze als Kacheln. Uebernimmt beim ersten Aufruf den Altbestand."""
    service = PersonaSetService()
    try:
        service.ensure_legacy_import()
    except Exception:  # noqa: BLE001 — Liste bleibt lesbar; Fehler steht im Log
        logger.exception("persona_set.legacy_import failed; listing without it")
    sets = service.list_sets()
    response = PersonaSetListResponse(count=len(sets), sets=sets)
    return json_success(response.model_dump(mode="json"))


@persona_sets_bp.route("", methods=["POST"])
@operator_only
@_view("Failed to create persona set")
def create_persona_set():
    record = PersonaSetService().create_set(_parse(PersonaSetCreate))
    return json_success(record.model_dump(mode="json"), status=201)


@persona_sets_bp.route("/<set_id>", methods=["GET"])
@operator_only
@_view("Failed to get persona set")
def get_persona_set(set_id: str):
    return json_success(PersonaSetService().get_set(set_id).model_dump(mode="json"))


@persona_sets_bp.route("/<set_id>", methods=["PATCH"])
@operator_only
@_view("Failed to update persona set")
def update_persona_set(set_id: str):
    record = PersonaSetService().update_set(set_id, _parse(PersonaSetUpdate))
    return json_success(record.model_dump(mode="json"))


@persona_sets_bp.route("/<set_id>", methods=["DELETE"])
@operator_only
@_view("Failed to delete persona set")
def delete_persona_set(set_id: str):
    PersonaSetService().delete_set(set_id)
    return json_success(PersonaSetDeleteResponse(removed=set_id).model_dump(mode="json"))


@persona_sets_bp.route("/<set_id>/duplicate", methods=["POST"])
@operator_only
@_view("Failed to duplicate persona set")
def duplicate_persona_set(set_id: str):
    record = PersonaSetService().duplicate_set(set_id, _parse(PersonaSetDuplicate))
    return json_success(record.model_dump(mode="json"), status=201)


@persona_sets_bp.route("/<set_id>/quality", methods=["GET"])
@operator_only
@_view("Failed to compute persona set quality")
def get_persona_set_quality(set_id: str):
    return json_success(PersonaSetService().quality(set_id).model_dump(mode="json"))


@persona_sets_bp.route("/<set_id>/entries", methods=["POST"])
@operator_only
@_view("Failed to add persona set entry")
def add_persona_set_entry(set_id: str):
    entry = PersonaSetService().add_entry(set_id, _parse(PersonaSetEntryCreate))
    return json_success(entry.model_dump(mode="json"), status=201)


@persona_sets_bp.route("/<set_id>/entries/delete", methods=["POST"])
@operator_only
@_view("Failed to delete persona set entries")
def delete_persona_set_entries(set_id: str):
    request_body = _parse(PersonaSetEntriesDelete)
    entry_ids = list(dict.fromkeys(request_body.entry_ids))
    summary = PersonaSetService().delete_entries(set_id, entry_ids)
    response = PersonaSetEntriesDeleteResponse(
        removed_entry_ids=entry_ids, set=summary
    )
    return json_success(response.model_dump(mode="json"))


@persona_sets_bp.route("/<set_id>/entries/<entry_id>", methods=["PATCH"])
@operator_only
@_view("Failed to update persona set entry")
def update_persona_set_entry(set_id: str, entry_id: str):
    entry = PersonaSetService().update_entry(
        set_id, entry_id, _parse(PersonaSetEntryUpdate)
    )
    return json_success(entry.model_dump(mode="json"))


@persona_sets_bp.route("/<set_id>/entries/<entry_id>", methods=["DELETE"])
@operator_only
@_view("Failed to delete persona set entry")
def delete_persona_set_entry(set_id: str, entry_id: str):
    summary = PersonaSetService().delete_entry(set_id, entry_id)
    response = PersonaSetEntriesDeleteResponse(
        removed_entry_ids=[entry_id], set=summary
    )
    return json_success(response.model_dump(mode="json"))
