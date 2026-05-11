"""
LLM Routing API.
"""

import typing

from flask import request
from . import runs_bp
from ..services.runtime_run_config import RuntimeRunConfig
from ..services.run_registry import RunRegistry
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageId, StageLLMRoute
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.logger import get_logger
from pydantic import ValidationError

logger = get_logger("agora.api.llm_routing")
run_registry = RunRegistry()

_VALID_STAGE_IDS: tuple[StageId, ...] = typing.get_args(StageId)


def _coerce_stage_id(stage_id: str) -> StageId | None:
    """Validate a URL/query stage_id string against the StageId Literal."""
    if stage_id in _VALID_STAGE_IDS:
        return stage_id
    return None


def _get_run_state(run_id: str):
    run = run_registry.get_run(run_id)
    if not run:
        return None
    return run.get("status")

@runs_bp.route("/<run_id>/llm-routing", methods=["GET"])
@handle_api_errors(logger=logger)
def get_run_llm_routing(run_id: str):
    """Get runtime LLM routing for a run."""
    config_service = RuntimeRunConfig(run_id)
    config = config_service.load_config()

    # Also include snapshots for started stages
    snapshots = {}
    for stage in _VALID_STAGE_IDS:
        snap = config_service.load_stage_snapshot(stage)
        if snap:
            snapshots[stage] = snap

    return json_success({
        "runtime_config": config.model_dump(mode="json"),
        "snapshots": snapshots
    })

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

        return json_success(new_config.model_dump(mode="json"))
    except ValidationError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )

@runs_bp.route("/<run_id>/llm-routing/stages/<stage_id>", methods=["PATCH"])
@handle_api_errors(logger=logger)
def patch_stage_llm_routing(run_id: str, stage_id: str):
    """Update routing for a specific stage."""
    stage = _coerce_stage_id(stage_id)
    if stage is None:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=f"Unknown stage_id: {stage_id}",
        )

    # 1. Check if stage already started/locked
    config_service = RuntimeRunConfig(run_id)
    if config_service.load_stage_snapshot(stage):
        return json_error(
            "Stage already started, route is locked",
            status=409,
            extra={"code": "stage_already_started"}
        )

    # 2. Update override in runtime config
    try:
        data = request.get_json() or {}
        route_override = StageLLMRoute.model_validate(data)

        config = config_service.load_config()
        config.stage_overrides[stage] = route_override
        config.routing_version += 1

        config_service.save_config(config)
        return json_success(config.model_dump(mode="json"))
    except ValidationError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )
