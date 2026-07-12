"""Onboarding Blueprint (Onboarding Slice 2, Single-Workspace-Scope).

Endpunkte (hinter Standard-Blueprint-Guard, identisch zur restlichen
``/api/*``-Konvention):

  - GET  /api/onboarding          — Status (Zustand + Voraussetzungen)
  - PUT  /api/onboarding/step     — Schritt abschließen (idempotent, resumierbar)
  - POST /api/onboarding/complete — Onboarding fachlich abschließen (ADR-0008)
  - POST /api/onboarding/dismiss  — Wizard wegklicken (kein Lockout)
  - POST /api/onboarding/reopen   — Wizard erneut öffnen (Resume)
"""
from __future__ import annotations

from flask import Blueprint, request
from pydantic import ValidationError

from ..contracts.user_profile_contract import (
    OnboardingStatusResponse,
    OnboardingStepUpdateRequest,
)
from ..services.onboarding_state_store import (
    OnboardingIncompleteError,
    compute_onboarding_requirements,
    get_onboarding_state_store,
)
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

onboarding_bp = Blueprint("onboarding", __name__)
logger = get_logger("agora.api.onboarding")


@onboarding_bp.route("", methods=["GET"])
@onboarding_bp.route("/", methods=["GET"])
@handle_api_errors
def get_onboarding_status():
    store = get_onboarding_state_store()
    state = store.load()
    requirements = compute_onboarding_requirements()
    response = OnboardingStatusResponse(
        state=state,
        requirements=requirements,
        onboarding_required=state.status in ("not_started", "in_progress"),
    )
    return json_success(response.model_dump(mode="json"))


@onboarding_bp.route("/step", methods=["PUT"])
@handle_api_errors
def update_onboarding_step():
    payload = request.get_json(silent=True) or {}
    try:
        body = OnboardingStepUpdateRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid request body",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    store = get_onboarding_state_store()
    updated = store.complete_step(body)
    return json_success({"state": updated.model_dump(mode="json")})


@onboarding_bp.route("/complete", methods=["POST"])
@handle_api_errors
def complete_onboarding():
    store = get_onboarding_state_store()
    requirements = compute_onboarding_requirements()
    try:
        updated = store.complete(requirements)
    except OnboardingIncompleteError as exc:
        return json_error(
            "onboarding requirements not met",
            status=409,
            code="onboarding_incomplete",
            extra={"missing": exc.missing},
        )
    return json_success({"state": updated.model_dump(mode="json")})


@onboarding_bp.route("/dismiss", methods=["POST"])
@handle_api_errors
def dismiss_onboarding():
    store = get_onboarding_state_store()
    updated = store.dismiss()
    return json_success({"state": updated.model_dump(mode="json")})


@onboarding_bp.route("/reopen", methods=["POST"])
@handle_api_errors
def reopen_onboarding():
    store = get_onboarding_state_store()
    updated = store.reopen()
    return json_success({"state": updated.model_dump(mode="json")})
