"""LLM-Profile Blueprint (P5.2).

  GET    /api/settings/llm-profiles          -- alle Profile
  POST   /api/settings/llm-profiles          -- neues Profil
  PUT    /api/settings/llm-profiles/<id>     -- Profil aktualisieren
  DELETE /api/settings/llm-profiles/<id>     -- Profil loschen
  POST   /api/settings/llm-profiles/<id>/default -- als Standard setzen
"""
from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from ..contracts.llm_profile_contract import LlmProfileCreateRequest, LlmProfileListResponse
from ..services.llm_profiles_store import get_llm_profiles_store
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

llm_profiles_bp = Blueprint("llm_profiles", __name__)
logger = get_logger("agora.api.llm_profiles")


@llm_profiles_bp.route("", methods=["GET"])
@llm_profiles_bp.route("/", methods=["GET"])
@handle_api_errors
def list_profiles():
    store = get_llm_profiles_store()
    profiles = store.list()
    return json_success(LlmProfileListResponse(profiles=profiles).model_dump(mode="json"))


@llm_profiles_bp.route("", methods=["POST"])
@llm_profiles_bp.route("/", methods=["POST"])
@handle_api_errors
def create_profile():
    payload = request.get_json(silent=True) or {}
    try:
        body = LlmProfileCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid request body",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    store = get_llm_profiles_store()
    created = store.create(body)
    return json_success(created.model_dump(mode="json"), status=201)


@llm_profiles_bp.route("/<profile_id>", methods=["PUT"])
@handle_api_errors
def update_profile(profile_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        body = LlmProfileCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid request body",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    store = get_llm_profiles_store()
    updated = store.update(profile_id, body)
    if updated is None:
        return json_error(f"Profile not found: {profile_id}", status=404, code="not_found")
    return json_success(updated.model_dump(mode="json"))


@llm_profiles_bp.route("/<profile_id>", methods=["DELETE"])
@handle_api_errors
def delete_profile(profile_id: str):
    store = get_llm_profiles_store()
    deleted = store.delete(profile_id)
    if not deleted:
        return json_error(f"Profile not found: {profile_id}", status=404, code="not_found")
    return json_success({"deleted": profile_id})


@llm_profiles_bp.route("/<profile_id>/default", methods=["POST"])
@handle_api_errors
def set_default_profile(profile_id: str):
    store = get_llm_profiles_store()
    profile = store.set_default(profile_id)
    if profile is None:
        return json_error(f"Profile not found: {profile_id}", status=404, code="not_found")
    return json_success(profile.model_dump(mode="json"))
