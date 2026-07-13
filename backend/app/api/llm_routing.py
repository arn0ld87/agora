"""
LLM Routing API.
"""

import json
import os
from collections import deque

from flask import request
from pydantic import ValidationError

from . import runs_bp, llm_bp
from ..services.runtime_run_config import RuntimeRunConfig
from ..services.run_registry import RunRegistry
from ..services.workspace_routing_store import get_workspace_routing_store
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, StageId
from ..contracts.ai_provider_contract import (
    AiRoute,
    RouteSource,
    ai_route_from_stage_route,
)
from ..contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger

logger = get_logger("agora.api.llm_routing")
run_registry = RunRegistry()

ALL_STAGE_IDS: tuple[StageId, ...] = (
    "document_ingest",
    "ontology_generation",
    "graph_build",
    "persona_generation",
    "simulation_rounds",
    "report_generation",
    "evaluation",
)

_PUBLIC_AI_PROVIDER_OPTION_KEYS = frozenset({"base_url", "num_ctx"})


def _serialize_public_ai_route(
    route: StageLLMRoute,
    *,
    source: RouteSource,
) -> dict[str, object]:
    """Serialize the canonical route without its private legacy round-trip marker."""
    public_route = route.model_copy(
        update={
            "provider_options": {
                key: value
                for key, value in route.provider_options.items()
                if key in _PUBLIC_AI_PROVIDER_OPTION_KEYS
            }
        }
    )
    payload = ai_route_from_stage_route(public_route).model_dump(mode="json")
    payload["source"] = source
    provider_options = payload.get("provider_options")
    if isinstance(provider_options, dict):
        provider_options.pop("__legacy_stage_route__", None)
    return AiRoute.model_validate(payload).model_dump(mode="json")


def _with_ai_route(
    legacy_payload: dict[str, object],
    route: StageLLMRoute,
    *,
    source: RouteSource,
) -> dict[str, object]:
    return {
        **legacy_payload,
        "ai_route": _serialize_public_ai_route(route, source=source),
    }

def _get_run_state(run_id: str):
    run = run_registry.get_run(run_id)
    if not run:
        return None
    return run.get("status")


def _load_invocation_events(run_id: str, limit: int = 200) -> list[dict]:
    """Read structured LLM call events for a run, newest last."""
    log_path = os.path.join(ArtifactLocator.run_dir(run_id), "llm_call_events.jsonl")
    if not os.path.exists(log_path):
        return []

    from typing import Any
    events: deque[Any] = deque(maxlen=limit if limit > 0 else None)
    with open(log_path, "r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed llm_call_events line for run %s", run_id)
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    return list(events)

@runs_bp.route("/<run_id>/llm-routing", methods=["GET"])
@handle_api_errors(logger=logger)
def get_run_llm_routing(run_id: str):
    """Get runtime LLM routing for a run."""
    config_service = RuntimeRunConfig(run_id)
    config = config_service.load_config()

    # Also include snapshots for started stages
    snapshots = {}
    for stage in ALL_STAGE_IDS:
        snap = config_service.load_stage_snapshot(stage)
        if snap:
            snapshots[stage] = snap

    return json_success(
        _with_ai_route(
            {
                "runtime_config": config.model_dump(mode="json"),
                "snapshots": snapshots,
                "invocation_events": _load_invocation_events(run_id),
            },
            config.global_default,
            source="legacy",
        )
    )

@runs_bp.route("/<run_id>/llm-routing", methods=["PUT"])
@handle_api_errors(logger=logger)
def update_run_llm_routing(run_id: str):
    """Replace runtime LLM routing for a run."""
    status = _get_run_state(run_id)
    if status in ("completed", "failed", "stopped"):
        return json_error("Cannot update routing for a finished run", status=409)

    try:
        data = request.get_json() or {}
        new_config = RuntimeLlmRouting.model_validate(data)

        config_service = RuntimeRunConfig(run_id)
        old_config = config_service.load_config()

        # Increment version
        new_config.routing_version = old_config.routing_version + 1
        config_service.save_config(new_config)

        return json_success(
            _with_ai_route(
                new_config.model_dump(mode="json"),
                new_config.global_default,
                source="run_override",
            )
        )
    except ValidationError as exc:
        return json_error(
            "Validation failed",
            status=400,
            code="validation_failed",
            extra={"details": exc.errors()},
        )

@runs_bp.route("/<run_id>/llm-routing/stages/<stage_id>", methods=["PATCH"])
@handle_api_errors(logger=logger)
def patch_stage_llm_routing(run_id: str, stage_id: str):
    """Update routing for a specific stage."""
    if stage_id not in ALL_STAGE_IDS:
        return json_error("Invalid stage_id", status=400, code="invalid_stage_id")

    # 1. Check if stage already started/locked
    config_service = RuntimeRunConfig(run_id)
    snapshot = config_service.load_stage_snapshot(stage_id)
    if snapshot:
        return json_error(
            "Stage already started, route is locked",
            status=409,
            extra={
                "code": "stage_already_started",
                "current_stage": stage_id,
                "target_stage": stage_id,
                "applies_from": None,
            }
        )

    # 2. Update override in runtime config
    try:
        data = request.get_json() or {}
        route_override = StageLLMRoute.model_validate(data)

        config = config_service.load_config()
        config.stage_overrides[stage_id] = route_override
        config.routing_version += 1

        config_service.save_config(config)
        return json_success(
            _with_ai_route(
                config.model_dump(mode="json"),
                route_override,
                source="stage_override",
            )
        )
    except ValidationError as exc:
        return json_error(
            "Validation failed",
            status=400,
            code="validation_failed",
            extra={"details": exc.errors()},
        )


# ---------------------------------------------------------------------------
# Workspace-weite Routing-Defaults (gilt für neue Runs, bis Stage versiegelt)
# ---------------------------------------------------------------------------


@llm_bp.route("/routing/defaults", methods=["GET"])
@handle_api_errors(logger=logger)
def get_routing_defaults():
    """Return the workspace-wide routing defaults."""
    defaults = get_workspace_routing_store().load()
    return json_success(
        _with_ai_route(
            defaults.model_dump(mode="json"),
            defaults.global_default,
            source="workspace",
        )
    )


@llm_bp.route("/routing/defaults", methods=["PUT"])
@handle_api_errors(logger=logger)
def replace_routing_defaults():
    """Replace the workspace-wide routing defaults."""
    payload = request.get_json(silent=True) or {}
    try:
        model = WorkspaceLlmRoutingDefaults.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Validation failed",
            status=400,
            code="validation_failed",
            extra={"details": exc.errors()},
        )
    stored = get_workspace_routing_store().save(model)
    return json_success(
        _with_ai_route(
            stored.model_dump(mode="json"),
            stored.global_default,
            source="workspace",
        )
    )


@llm_bp.route("/routing/defaults/stages/<stage_id>", methods=["PATCH"])
@handle_api_errors(logger=logger)
def patch_routing_default_stage(stage_id: str):
    """Set or clear the workspace-wide override for one stage.

    Empty body or ``{"clear": true}`` clears the override; otherwise the body
    is parsed as ``StageLLMRoute``.
    """
    if stage_id not in ALL_STAGE_IDS:
        return json_error("Invalid stage_id", status=400, code="invalid_stage_id")

    payload = request.get_json(silent=True) or {}
    store = get_workspace_routing_store()

    if payload.get("clear") is True or payload == {}:
        defaults = store.set_stage_override(stage_id, None)
        active_route = defaults.stage_overrides.get(stage_id, defaults.global_default)
        return json_success(
            _with_ai_route(
                defaults.model_dump(mode="json"),
                active_route,
                source="workspace",
            )
        )

    try:
        route = StageLLMRoute.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Validation failed",
            status=400,
            code="validation_failed",
            extra={"details": exc.errors()},
        )
    defaults = store.set_stage_override(stage_id, route)
    return json_success(
        _with_ai_route(
            defaults.model_dump(mode="json"),
            route,
            source="workspace",
        )
    )


@llm_bp.route("/routing/defaults/global", methods=["PUT"])
@handle_api_errors(logger=logger)
def replace_global_default():
    """Replace just the workspace-wide global default route."""
    payload = request.get_json(silent=True) or {}
    try:
        route = StageLLMRoute.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Validation failed",
            status=400,
            code="validation_failed",
            extra={"details": exc.errors()},
        )
    defaults = get_workspace_routing_store().set_global_default(route)
    return json_success(
        _with_ai_route(
            defaults.model_dump(mode="json"),
            defaults.global_default,
            source="workspace",
        )
    )
