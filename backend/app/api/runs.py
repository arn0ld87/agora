# ruff: noqa: F401, E402, F811
"""
Run registry API.
"""

from __future__ import annotations

import json  # noqa: F401
import os  # noqa: F401
import threading  # noqa: F401
import traceback  # noqa: F401
from collections.abc import Mapping  # noqa: F401
from typing import Any, Optional  # noqa: F401

from flask import current_app, request  # noqa: F401
from pydantic import ValidationError  # noqa: F401

from . import runs_bp
from ..config import Config  # noqa: F401
from ..contracts.ai_provider_contract import AiModelRef  # noqa: F401
from ..contracts.auth_contract import AuthType  # noqa: F401
from ..contracts.job_lease_contract import JobLease  # noqa: F401
from ..contracts.runs_contract import (
    RunDetail,
    RunsAggregation,
    RunsFilterQuery,
    RunsListResponse,
)
from ..models.project import ProjectManager, ProjectStatus  # noqa: F401
from ..models.task import TaskManager, TaskStatus  # noqa: F401
from ..container import get_container  # noqa: F401
from ..services.graph_build import GraphBuildService  # noqa: F401
from ..storage.ner_chunk_context import build_chunk_contexts  # noqa: F401
from ..services.graph_build_checkpoint import (  # noqa: F401
    GraphBuildCheckpoint,
    checkpoint_is_resumable,
    load_checkpoint,
)
from ..services.graph_builder import GraphBuilderService  # noqa: F401
from ..services.graph_tools import GraphToolsService  # noqa: F401
from ..services.llm_routing_seed import (  # noqa: F401
    build_route_subprocess_env,
    build_runtime_llm_config,
    prevalidate_ai_model_ref,
    resolve_route_api_key,
    seed_run_stage_routing,
    workspace_credential_context_for_run,
    workspace_credential_metadata,
)
from .simulation_common import DemoLimitExceededError, apply_demo_run_limits  # noqa: F401
from ..services.document_roles import load_document_roles  # noqa: F401
from ..services.report_agent import ReportAgent, ReportManager  # noqa: F401
from ..services.report_agent.output_contract import is_deliverable_report_status  # noqa: F401
from ..services.report_generation import (  # noqa: F401
    finish_cancelled_run,
    finish_completed_run,
    was_run_cancelled,
)
from ..services.run_export import select_run_export_files  # noqa: F401
from ..services.run_lifecycle import RunLifecycle  # noqa: F401
from ..services.run_read_model import attach_summary as _attach_summary  # noqa: F401
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager, SimulationStatus  # noqa: F401
from ..services.simulation_runner import RunnerStatus, SimulationRunner  # noqa: F401
from ..services.stage_model_router import StageModelRouter  # noqa: F401
from ..services.sim.cancel_flag import request_cancel as _request_cancel  # noqa: F401
from ..security.principal_context import current_principal  # noqa: F401
from ..utils.api_errors import ApiErrorCode  # noqa: F401
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.endpoints import is_local_endpoint  # noqa: F401
from ..utils.llm_client import LLMClient  # noqa: F401
from ..utils.artifact_locator import ArtifactLocator  # noqa: F401
from ..utils.logger import get_logger
from ..utils.validation import validate_run_id, validate_simulation_id  # noqa: F401

from .runs_replay import (
    _ai_model_ref_from_manifest_route,  # noqa: F401
    _build_run_detail,
    _capture_replay_manifest_draft,  # noqa: F401
    _parse_status_param,  # noqa: F401
    _replay_simulation_run,  # noqa: F401
)
from .runs_restart import (
    _restart_activity_mode,  # noqa: F401
    _restart_contested_question,  # noqa: F401
    _restart_graph_build,  # noqa: F401
    _restart_simulation_prepare,  # noqa: F401
    _resume_graph_build,  # noqa: F401
    _resume_or_restart_graph_build,  # noqa: F401
)
from .runs_resume import (
    _inherited_credential_scope_metadata,  # noqa: F401
    _original_run_is_workspace_scoped,  # noqa: F401
    _reject_if_route_api_key_missing,  # noqa: F401
    _resume_or_restart_simulation_run,  # noqa: F401
    _resume_report_generate,  # noqa: F401
)
from .runs_actions import (
    _LEASE_GUARD_ACTIVE_STATUSES,
    _get_run_by_run_or_simulation_id,
    _get_run_or_404,
    _linked_or_entity_id,
    _reject_if_lease_active,
    _simulation_artifacts,
    execute_cancel_run,
    execute_export_run,
    execute_get_run_manifest,
    execute_get_run_usage,
    execute_list_runs,
    execute_replay_run,
    execute_resume_run,
    execute_stop_run,
)

logger = get_logger("agora.api.runs")
run_registry = RunRegistry()


@runs_bp.route("", methods=["GET"])
@handle_api_errors(logger=logger, log_prefix="Failed to list runs")
def list_runs():
    return execute_list_runs()


@runs_bp.route("/<run_id>", methods=["GET"])
def get_run(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error
    detail = RunDetail.model_validate(_build_run_detail(run))
    return json_success(detail.model_dump(mode="json"))


@runs_bp.route("/<run_id>/events", methods=["GET"])
def get_run_events(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error
    return json_success(run.get("events", []))


@runs_bp.route("/<run_id>/usage", methods=["GET"])
def get_run_usage(run_id: str):
    return execute_get_run_usage(run_id)


@runs_bp.route("/<run_id>/stop", methods=["POST"])
def stop_run(run_id: str):
    return execute_stop_run(run_id)


@runs_bp.route("/<run_id>/cancel", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to cancel run")
def cancel_run(run_id: str):
    return execute_cancel_run(run_id)


@runs_bp.route("/<run_id>/replay", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to replay run")
def replay_run(run_id: str):
    return execute_replay_run(run_id)


@runs_bp.route("/<run_id>/manifest", methods=["GET"])
@handle_api_errors(logger=logger, log_prefix="Failed to get run manifest")
def get_run_manifest(run_id: str):
    return execute_get_run_manifest(run_id)


@runs_bp.route("/<run_id>/export", methods=["GET"])
@handle_api_errors(logger=logger, log_prefix="Failed to export run")
def export_run(run_id: str):
    return execute_export_run(run_id)


@runs_bp.route("/<run_id>/resume", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to resume run")
def resume_run(run_id: str):
    return execute_resume_run(run_id)
