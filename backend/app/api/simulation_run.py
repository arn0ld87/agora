# ruff: noqa: F401, E402, F811
"""
Run-control and live-status routes split from the main simulation API module.
"""

from typing import TYPE_CHECKING

from flask import request

from . import simulation_bp
from ..config import Config
from ..contracts.auth_contract import AuthType
from ..contracts.post_event_contract import Platform
from ..contracts.sim_action_contract import (
    RoundSummary,
    SimActionPage,
    SimActionRecord,
    SimActionType,
)
from ..models.project import ProjectManager
from ..security.principal_context import current_principal
from ..services.persona_review_service import PersonaReviewService
from ..services.llm_routing_seed import (
    build_route_subprocess_env,
    resolve_route_api_key,
    seed_run_stage_routing,
    workspace_credential_metadata,
)
from ..utils.endpoints import is_local_endpoint
from ..services.llm_runtime import RuntimeLlmConfig, parse_runtime_llm_config
from ..services.manifest_capture import ManifestCapture
from ..services.run_lifecycle import RunLifecycle, RunPersistenceError
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..services.stage_model_router import StageModelRouter
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.artifact_locator import ArtifactLocator
from ..utils.pagination import clamp_int, DEFAULT_LIMIT, MAX_LIMIT
from ..utils.scopes import require_scope
from ..utils.validation import validate_simulation_id
from .simulation_common import (
    get_artifact_store,
    logger,
    run_registry,
    simulation_resume_capability as _simulation_resume_capability,
    simulation_run_artifacts as _simulation_run_artifacts,
)
from .simulation_prepare import _check_simulation_prepared

if TYPE_CHECKING:  # pragma: no cover — nur für Typprüfung
    from ..contracts.ai_provider_contract import AiModelRef
    from ..contracts.llm_routing_contract import ResolvedRoute
    from ..contracts.run_budget_contract import RunBudgetConfig
    from ..services.sim.run_state_store import AgentAction

from .simulation_run_start import (
    _StartRejected,
    _StartRequest,
    _apply_budget_to_simulation,
    _apply_demo_start_limits,
    _apply_route_to_simulation_config,
    _begin_start_run,
    _build_start_response,
    _capture_start_manifest_draft,
    _effective_start_budget,
    _ensure_startable_state,
    _evaluate_persona_review_gate,
    _has_config_overrides,
    _parse_ai_model_ref,
    _parse_bounded_int,
    _parse_budget_config,
    _parse_start_request,
    _precheck_ai_model_ref,
    _precheck_runtime_provider_key,
    _resolve_graph_memory_id,
    _resolve_start_route,
    _simulation_dir,
    _stop_running_simulation,
    execute_start_simulation,
)

from .simulation_run_actions import (
    _agent_action_to_record,
    _coerce_action_type,
    _decode_actions_cursor,
    _resolve_target_post_id,
    execute_close_simulation_env,
    execute_get_agent_stats,
    execute_get_env_status,
    execute_get_run_status,
    execute_get_run_status_detail,
    execute_get_simulation_actions,
    execute_get_simulation_console_log,
    execute_get_simulation_rounds,
    execute_get_simulation_timeline,
    execute_pause_simulation,
    execute_resume_simulation,
    execute_stop_simulation,
)


@simulation_bp.route('/start', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to start simulation")
def start_simulation():
    """Start or restart a simulation."""
    return execute_start_simulation()


@simulation_bp.route('/stop', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to stop simulation")
def stop_simulation():
    """Stop a running simulation."""
    return execute_stop_simulation()


@simulation_bp.route('/<simulation_id>/pause', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to pause simulation")
def pause_simulation(simulation_id: str):
    """Set the soft-pause flag so the simulation halts after the current round."""
    return execute_pause_simulation(simulation_id)


@simulation_bp.route('/<simulation_id>/resume', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to resume simulation")
def resume_simulation(simulation_id: str):
    """Clear the pause flag so the simulation continues."""
    return execute_resume_simulation(simulation_id)


@simulation_bp.route('/<simulation_id>/console-log', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to read simulation console log")
def get_simulation_console_log(simulation_id: str):
    """Read incremental subprocess console logs for a simulation."""
    return execute_get_simulation_console_log(simulation_id)


@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get running status")
def get_run_status(simulation_id: str):
    """Get lightweight real-time run status for frontend polling."""
    return execute_get_run_status(simulation_id)


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get detailed status")
def get_run_status_detail(simulation_id: str):
    """Liefert den detaillierten Laufstatus mit aggregierten Aktionszahlen und paginierten Aktionen."""
    return execute_get_run_status_detail(simulation_id)


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get simulation actions")
def get_simulation_actions(simulation_id: str):
    """Get paginated actions for a simulation run."""
    return execute_get_simulation_actions(simulation_id)


@simulation_bp.route('/<simulation_id>/rounds', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get simulation rounds")
def get_simulation_rounds(simulation_id: str):
    """Get round-by-round summary for a simulation."""
    return execute_get_simulation_rounds(simulation_id)


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get simulation timeline")
def get_simulation_timeline(simulation_id: str):
    """Get aggregated chronological timeline of all actions."""
    return execute_get_simulation_timeline(simulation_id)


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get agent statistics")
def get_agent_stats(simulation_id: str):
    """Get aggregated per-agent statistics."""
    return execute_get_agent_stats(simulation_id)


@simulation_bp.route('/env-status', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to get environment status")
def get_env_status():
    """Get current simulation environment availability."""
    return execute_get_env_status()


@simulation_bp.route('/close-env', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to close environment")
def close_simulation_env():
    """Gracefully close a simulation environment and update simulation status."""
    return execute_close_simulation_env()


__all__ = [
    "start_simulation",
    "stop_simulation",
    "pause_simulation",
    "resume_simulation",
    "get_simulation_console_log",
    "get_run_status",
    "get_run_status_detail",
    "get_simulation_actions",
    "get_simulation_rounds",
    "get_simulation_timeline",
    "get_agent_stats",
    "get_env_status",
    "close_simulation_env",
    "execute_start_simulation",
    "execute_stop_simulation",
    "execute_pause_simulation",
    "execute_resume_simulation",
    "execute_get_simulation_console_log",
    "execute_get_run_status",
    "execute_get_run_status_detail",
    "execute_get_simulation_actions",
    "execute_get_simulation_rounds",
    "execute_get_simulation_timeline",
    "execute_get_agent_stats",
    "execute_get_env_status",
    "execute_close_simulation_env",
    "_agent_action_to_record",
    "_coerce_action_type",
    "_decode_actions_cursor",
    "_resolve_target_post_id",
    "_StartRejected",
    "_StartRequest",
    "_apply_budget_to_simulation",
    "_apply_demo_start_limits",
    "_apply_route_to_simulation_config",
    "_begin_start_run",
    "_build_start_response",
    "_capture_start_manifest_draft",
    "_effective_start_budget",
    "_ensure_startable_state",
    "_evaluate_persona_review_gate",
    "_has_config_overrides",
    "_parse_ai_model_ref",
    "_parse_bounded_int",
    "_parse_budget_config",
    "_parse_start_request",
    "_precheck_ai_model_ref",
    "_precheck_runtime_provider_key",
    "_resolve_graph_memory_id",
    "_resolve_start_route",
    "_simulation_dir",
    "_stop_running_simulation",
    "_simulation_resume_capability",
    "_simulation_run_artifacts",
    "_check_simulation_prepared",
    "validate_simulation_id",
    "clamp_int",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "SimulationRunner",
    "SimulationManager",
    "SimulationStatus",
    "StageModelRouter",
    "resolve_route_api_key",
    "seed_run_stage_routing",
    "get_artifact_store",
    "run_registry",
    "Config",
]
