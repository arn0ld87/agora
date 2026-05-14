"""API-Keys Blueprint (Slice G2, Single-Workspace-Scope).

Endpunkte (hinter Standard-Blueprint-Guard, identisch zur restlichen
``/api/*``-Konvention):

  - GET    /api/api-keys           — Liste aller (auch revoked) Schlüssel
  - POST   /api/api-keys           — neuen Schlüssel anlegen (201 + Klartext-Token einmalig)
  - DELETE /api/api-keys/<key_id>  — Schlüssel revoken

Audit-Log-Hook ist Out-of-Scope für G2 (kommt in G3).
"""
from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from ..contracts.api_keys_contract import (
    ApiKeyCreateRequest,
    ApiKeysListResponse,
)
from ..services.api_keys_store import get_api_keys_store
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

api_keys_bp = Blueprint("api_keys", __name__)
logger = get_logger("agora.api.api_keys")


@api_keys_bp.route("", methods=["GET"])
@api_keys_bp.route("/", methods=["GET"])
@handle_api_errors
def list_api_keys():
    store = get_api_keys_store()
    items = store.list()
    response = ApiKeysListResponse(items=items, total=len(items))
    return json_success(response.model_dump(mode="json"))


@api_keys_bp.route("", methods=["POST"])
@api_keys_bp.route("/", methods=["POST"])
@handle_api_errors
def create_api_key():
    payload = request.get_json(silent=True) or {}
    try:
        body = ApiKeyCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid request body",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    store = get_api_keys_store()
    created = store.create(label=body.label, scopes=list(body.scopes))
    return json_success(created.model_dump(mode="json"), status=201)


@api_keys_bp.route("/<key_id>", methods=["DELETE"])
@handle_api_errors
def revoke_api_key(key_id: str):
    store = get_api_keys_store()
    revoked = store.revoke(key_id)
    if revoked is None:
        return json_error(
            f"API key does not exist: {key_id}",
            status=404,
            code="not_found",
        )
    return json_success(revoked.model_dump(mode="json"))
