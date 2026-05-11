"""
LLM Routing API.
"""

import json
import os

from flask import request
from pydantic import ValidationError

from . import runs_bp
from ..services.runtime_run_config import RuntimeRunConfig
from ..services.run_registry import RunRegistry
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, StageId
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

    events: list[dict] = []
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
    if limit > 0:
        return events[-limit:]
    return events

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

    return json_success({
        "runtime_config": config.model_dump(mode="json"),
        "snapshots": snapshots,
        "invocation_events": _load_invocation_events(run_id),
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
    if config_service.load_stage_snapshot(stage_id):
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
        config.stage_overrides[stage_id] = route_override
        config.routing_version += 1

        config_service.save_config(config)
        return json_success(config.model_dump(mode="json"))
    except ValidationError as exc:
        return json_error(
            "Validation failed",
            status=400,
            code="validation_failed",
            extra={"details": exc.errors()},
        )
