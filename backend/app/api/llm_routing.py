"""
LLM Routing API.
"""

from flask import request
from . import runs_bp
from ..services.runtime_run_config import RuntimeRunConfig
from ..services.run_registry import RunRegistry
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, StageId
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.logger import get_logger
from ..utils.validation import validate_run_id
from pydantic import ValidationError

logger = get_logger("agora.api.llm_routing")
run_registry = RunRegistry()


def _get_run_or_error(run_id: str):
    if not validate_run_id(run_id):
        return None, json_error("Invalid run_id format", status=400)
    run = run_registry.get_run(run_id)
    if not run:
        return None, json_error(f"Run does not exist: {run_id}", status=404)
    return run, None

@runs_bp.route("/<run_id>/llm-routing", methods=["GET"])
@handle_api_errors(logger=logger)
def get_run_llm_routing(run_id: str):
    """Get runtime LLM routing for a run."""
    _, error = _get_run_or_error(run_id)
    if error:
        return error
    config_service = RuntimeRunConfig(run_id)
    config = config_service.load_config()

    # Also include snapshots for started stages
    snapshots = {}
    import typing
    for stage in typing.get_args(StageId):
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
    run, error = _get_run_or_error(run_id)
    if error:
        return error
    status = run.get("status")
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
        return json_error(str(exc), status=400)

@runs_bp.route("/<run_id>/llm-routing/stages/<stage_id>", methods=["PATCH"])
@handle_api_errors(logger=logger)
def patch_stage_llm_routing(run_id: str, stage_id: str):
    """Update routing for a specific stage."""
    _, error = _get_run_or_error(run_id)
    if error:
        return error
    # Validate stage_id
    import typing
    if stage_id not in typing.get_args(StageId):
        return json_error(f"Invalid stage_id: {stage_id}", status=400)

    typed_stage_id = typing.cast(StageId, stage_id)

    # 1. Check if stage already started/locked
    config_service = RuntimeRunConfig(run_id)
    snapshot = config_service.load_stage_snapshot(typed_stage_id)
    if snapshot:
        # Determine current_stage from snapshots or run state
        # For now, we use the stage_id itself as the one that already started
        return json_error(
            "Stage already started, route is locked",
            status=409,
            extra={
                "code": "stage_already_started",
                "current_stage": typed_stage_id,
                "target_stage": typed_stage_id,
                "applies_from": None
            }
        )

    # 2. Update override in runtime config
    try:
        data = request.get_json() or {}
        route_override = StageLLMRoute.model_validate(data)

        config = config_service.load_config()
        config.stage_overrides[typed_stage_id] = route_override
        config.routing_version += 1

        config_service.save_config(config)
        return json_success(config.model_dump(mode="json"))
    except ValidationError as exc:
        return json_error(str(exc), status=400)
