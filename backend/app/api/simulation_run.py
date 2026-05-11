"""
Run-control and live-status routes split from the main simulation API module.
"""

import os

from flask import jsonify, request

from . import simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.persona_review_service import PersonaReviewService
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.artifact_locator import ArtifactLocator
from ..utils.validation import validate_simulation_id
from .simulation_common import (
    get_artifact_store,
    logger,
    run_registry,
    simulation_resume_capability as _simulation_resume_capability,
    simulation_run_artifacts as _simulation_run_artifacts,
)
from .simulation_prepare import _check_simulation_prepared


def _evaluate_persona_review_gate(simulation_id: str):
    """Return a 409 response when PERSONA_REVIEW_ENABLED blocks the start.

    Returns None when the gate is open. The gate is silent while the global
    ``PERSONA_REVIEW_ENABLED`` flag is off so existing behaviour is unchanged
    until an operator explicitly opts in.
    """
    if not Config.PERSONA_REVIEW_ENABLED:
        return None
    review = PersonaReviewService(get_artifact_store()).evaluate_start_gate(
        simulation_id
    )
    if review["allowed"]:
        return None
    return json_error(
        ApiErrorCode.PERSONA_REVIEW_REQUIRED,
        status=409,
        message="Persona review pending. Approve all personas before starting the simulation.",
        extra={"review": review},
    )


def _simulation_dir(simulation_id: str) -> str:
    return ArtifactLocator.simulation_dir(simulation_id)


@simulation_bp.route('/start', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to start simulation")
def start_simulation():
    """Start running a prepared simulation."""
    data = request.get_json() or {}

    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    platform = data.get('platform', 'parallel')
    max_rounds = data.get('max_rounds')
    simulation_days = data.get('simulation_days')
    llm_model_override = (data.get('llm_model') or '').strip() or None
    try:
        llm_runtime = parse_runtime_llm_config(data)
    except ValueError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )
    enable_graph_memory_update = data.get('enable_graph_memory_update', False)
    force = data.get('force', False)

    if max_rounds is not None:
        try:
            max_rounds = int(max_rounds)
            if max_rounds <= 0:
                return json_error(
                    ApiErrorCode.VALIDATION_FAILED,
                    message="max_rounds must be a positive integer",
                )
        except (ValueError, TypeError):
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message="max_rounds must be a valid integer",
            )

    if simulation_days is not None:
        try:
            simulation_days = int(simulation_days)
            if simulation_days <= 0 or simulation_days > 365:
                return json_error(
                    ApiErrorCode.VALIDATION_FAILED,
                    message="simulation_days must be between 1 and 365",
                )
        except (ValueError, TypeError):
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message="simulation_days must be a valid integer",
            )

    if platform not in ['twitter', 'reddit', 'parallel']:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message=f"Invalid platform type: {platform}. Allowed: twitter/reddit/parallel",
        )

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    gate_response = _evaluate_persona_review_gate(simulation_id)
    if gate_response is not None:
        return gate_response

    force_restarted = False
    if state.status != SimulationStatus.READY:
        is_prepared, _prepare_info = _check_simulation_prepared(simulation_id)
        if not is_prepared:
            return json_error(
                ApiErrorCode.SIMULATION_NOT_PREPARED,
                status=409,
                message=(
                    f"Simulation not ready. Current status: {state.status.value}. "
                    "Please call /prepare first"
                ),
            )

        if state.status == SimulationStatus.RUNNING:
            run_state = SimulationRunner.get_run_state(simulation_id)
            if run_state and run_state.runner_status.value == 'running':
                if not force:
                    return json_error(
                        ApiErrorCode.SIMULATION_ALREADY_RUNNING,
                        status=409,
                        message=(
                            "Simulation is running. Please call /stop first or use force=true to force restart."
                        ),
                    )
                logger.info(f"Force mode: stopping running simulation {simulation_id}")
                try:
                    SimulationRunner.stop_simulation(simulation_id)
                except Exception as exc:
                    logger.warning(f"Warning when stopping simulation: {exc}")

        if force:
            logger.info(f"Force mode: cleaning simulation runtime files for {simulation_id}")
            cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
            if not cleanup_result.get("success"):
                logger.warning(f"Warning when cleaning logs: {cleanup_result.get('errors')}")
            force_restarted = True

        manager._reset_to_ready(
            state,
            reason=f"force start_run after status={state.status.value}",
        )

    graph_id = None
    if enable_graph_memory_update:
        graph_id = state.graph_id
        if not graph_id:
            project = ProjectManager.get_project(state.project_id)
            if project:
                graph_id = project.graph_id
        if not graph_id:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message=(
                    "Enable knowledge graph memory update requires valid graph_id. "
                    "Please ensure project graph is built."
                ),
            )
        logger.info(
            f"Enable knowledge graph memory update: simulation_id={simulation_id}, graph_id={graph_id}",
            extra={'simulation_id': simulation_id},
        )

    run_id = f"sim_{simulation_id}"
    from ..services.stage_model_router import StageModelRouter
    from ..services.runtime_run_config import RuntimeRunConfig
    from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute

    # 0. Initialise or update runtime routing
    config_service = RuntimeRunConfig(run_id)
    try:
        runtime_routing = config_service.load_config()
        if llm_runtime.enabled:
             runtime_routing.default_route = StageLLMRoute(
                 provider_id=llm_runtime.provider,
                 model=llm_model_override or Config.LLM_MODEL_NAME,
                 base_url=llm_runtime.base_url
             )
             runtime_routing.routing_version += 1
        elif llm_model_override:
             runtime_routing.default_route.model = llm_model_override
             runtime_routing.routing_version += 1
        config_service.save_config(runtime_routing)
    except:
        # Synthesis happens in load_config fallback
        pass

    router = StageModelRouter(run_id)
    rounds_route = router.resolve("simulation_rounds")
    router.lock_stage("simulation_rounds", rounds_route)

    # Reconstruct effective RuntimeLlmConfig for subprocess_env (OASIS compat)
    from ..services.llm_runtime import RuntimeLlmConfig
    from ..utils.llm_client import LLMClient

    rounds_client = LLMClient.from_route(rounds_route, run_id=run_id)
    effective_runtime = RuntimeLlmConfig(
        provider=rounds_route.provider_id,
        api_key=rounds_client.api_key,
        base_url=rounds_client.base_url
    )

    if simulation_days is not None or llm_model_override or llm_runtime.enabled:
        store = get_artifact_store()
        config = store.read_json(simulation_id, "simulation_config", default=None)
        if not config:
            return json_error(
                ApiErrorCode.SIMULATION_NOT_PREPARED,
                status=404,
                message="Simulation configuration does not exist. Please call /prepare first",
            )
        if simulation_days is not None:
            time_config = dict(config.get("time_config") or {})
            time_config["total_simulation_hours"] = simulation_days * 24
            config["time_config"] = time_config

        # Lock simulation_config to use the snapshot model/url
        config["llm_model"] = rounds_route.model
        config["llm_base_url"] = rounds_client.base_url
        store.write_json(simulation_id, "simulation_config", config)

    run_state = SimulationRunner.start_simulation(
        simulation_id=simulation_id,
        platform=platform,
        max_rounds=max_rounds,
        enable_graph_memory_update=enable_graph_memory_update,
        graph_id=graph_id,
        runtime_env=effective_runtime.subprocess_env(model=rounds_route.model),
    )

    manager._set_status(state, SimulationStatus.RUNNING)

    run_record = run_registry.create_run(
        run_type="simulation_run",
        entity_id=simulation_id,
        status="processing",
        progress=0,
        message="Simulation run started",
        linked_ids={"simulation_id": simulation_id, "project_id": state.project_id},
        artifacts=_simulation_run_artifacts(simulation_id),
        resume_capability=_simulation_resume_capability(simulation_id, state),
        branch_label=state.branch_name,
        metadata={
            "graph_id": state.graph_id,
            "platform": platform,
            "source_simulation_id": state.source_simulation_id,
            "root_simulation_id": state.root_simulation_id,
            "branch_name": state.branch_name,
            "branch_depth": state.branch_depth,
            "llm_model": llm_model_override,
            "llm_provider": llm_runtime.redacted_metadata() or None,
        },
    )

    response_data = run_state.to_dict()
    if max_rounds:
        response_data['max_rounds_applied'] = max_rounds
    if simulation_days:
        response_data['simulation_days_applied'] = simulation_days
    response_data['graph_memory_update_enabled'] = enable_graph_memory_update
    response_data['force_restarted'] = force_restarted
    response_data['run_id'] = run_record["run_id"]
    if enable_graph_memory_update:
        response_data['graph_id'] = graph_id

    return json_success(response_data)


@simulation_bp.route('/stop', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to stop simulation")
def stop_simulation():
    """Stop a running simulation."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    run_state = SimulationRunner.stop_simulation(simulation_id)
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if state:
        manager._set_status(state, SimulationStatus.PAUSED)
        run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
        if run:
            run_registry.update_run(
                run["run_id"],
                status="stopped",
                progress=run_state.to_dict().get("progress_percent", 0),
                message="Simulation stopped",
                artifacts=_simulation_run_artifacts(simulation_id),
                resume_capability=_simulation_resume_capability(simulation_id, state),
            )
    return json_success(run_state.to_dict())


@simulation_bp.route('/<simulation_id>/pause', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to pause simulation")
def pause_simulation(simulation_id: str):
    """Set the soft-pause flag so the simulation halts after the current round."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import set_pause_state

    sim_dir = _simulation_dir(simulation_id)
    if not os.path.isdir(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    state = set_pause_state(sim_dir, True)
    logger.info(f"Pause requested for {simulation_id}")
    run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        sim_state = SimulationManager().get_simulation(simulation_id)
        run_registry.update_run(
            run["run_id"],
            status="paused",
            message="Pause requested",
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability=_simulation_resume_capability(simulation_id, sim_state),
        )
    return json_success({"simulation_id": simulation_id, "control_state": state})


@simulation_bp.route('/<simulation_id>/resume', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to resume simulation")
def resume_simulation(simulation_id: str):
    """Clear the pause flag so the simulation continues."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import set_pause_state

    sim_dir = _simulation_dir(simulation_id)
    if not os.path.isdir(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    state = set_pause_state(sim_dir, False)
    logger.info(f"Resume requested for {simulation_id}")
    run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        sim_state = SimulationManager().get_simulation(simulation_id)
        run_registry.update_run(
            run["run_id"],
            status="processing",
            message="Run resumed",
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability=_simulation_resume_capability(simulation_id, sim_state),
        )
    return json_success({"simulation_id": simulation_id, "control_state": state})


@simulation_bp.route('/<simulation_id>/console-log', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to read simulation console log")
def get_simulation_console_log(simulation_id: str):
    """Read incremental subprocess console logs for a simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )
    from_line = request.args.get('from_line', 0, type=int)
    data = SimulationRunner.get_console_log(simulation_id, from_line=from_line)
    return json_success(data)


@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get running status")
def get_run_status(simulation_id: str):
    """Get lightweight real-time run status for frontend polling."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import read_control_state

    run_state = SimulationRunner.get_run_state(simulation_id)
    control = read_control_state(_simulation_dir(simulation_id))
    if not run_state:
        return json_success({
            "simulation_id": simulation_id,
            "runner_status": "idle",
            "current_round": 0,
            "total_rounds": 0,
            "progress_percent": 0,
            "twitter_actions_count": 0,
            "reddit_actions_count": 0,
            "total_actions_count": 0,
            "paused": bool(control.get("paused")),
        })

    data = run_state.to_dict()
    data["paused"] = bool(control.get("paused"))
    return json_success(data)


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get detailed status")
def get_run_status_detail(simulation_id: str):
    """Get detailed run status including aggregated actions."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    run_state = SimulationRunner.get_run_state(simulation_id)
    platform_filter = request.args.get('platform')
    if not run_state:
        return json_success({
            "simulation_id": simulation_id,
            "runner_status": "idle",
            "all_actions": [],
            "twitter_actions": [],
            "reddit_actions": [],
        })

    all_actions = SimulationRunner.get_all_actions(simulation_id=simulation_id, platform=platform_filter)
    twitter_actions = SimulationRunner.get_all_actions(
        simulation_id=simulation_id, platform="twitter"
    ) if not platform_filter or platform_filter == "twitter" else []
    reddit_actions = SimulationRunner.get_all_actions(
        simulation_id=simulation_id, platform="reddit"
    ) if not platform_filter or platform_filter == "reddit" else []
    current_round = run_state.current_round
    recent_actions = SimulationRunner.get_all_actions(
        simulation_id=simulation_id,
        platform=platform_filter,
        round_num=current_round,
    ) if current_round > 0 else []

    result = run_state.to_dict()
    result["all_actions"] = [action.to_dict() for action in all_actions]
    result["twitter_actions"] = [action.to_dict() for action in twitter_actions]
    result["reddit_actions"] = [action.to_dict() for action in reddit_actions]
    result["rounds_count"] = len(run_state.rounds)
    result["recent_actions"] = [action.to_dict() for action in recent_actions]
    return json_success(result)


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get action history")
def get_simulation_actions(simulation_id: str):
    """Get paginated action history for a simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    platform = request.args.get('platform')
    agent_id = request.args.get('agent_id', type=int)
    round_num = request.args.get('round_num', type=int)
    actions = SimulationRunner.get_actions(
        simulation_id=simulation_id,
        limit=limit,
        offset=offset,
        platform=platform,
        agent_id=agent_id,
        round_num=round_num,
    )
    return json_success({
        "count": len(actions),
        "actions": [action.to_dict() for action in actions],
    })


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get timeline")
def get_simulation_timeline(simulation_id: str):
    """Get round-level timeline summaries for a simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    start_round = request.args.get('start_round', 0, type=int)
    end_round = request.args.get('end_round', type=int)
    timeline = SimulationRunner.get_timeline(
        simulation_id=simulation_id,
        start_round=start_round,
        end_round=end_round,
    )
    return json_success({"rounds_count": len(timeline), "timeline": timeline})


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get agent statistics")
def get_agent_stats(simulation_id: str):
    """Get aggregated per-agent statistics."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    stats = SimulationRunner.get_agent_stats(simulation_id)
    return json_success({"agents_count": len(stats), "stats": stats})


@simulation_bp.route('/env-status', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to get environment status")
def get_env_status():
    """Get current simulation environment availability."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    env_alive = SimulationRunner.check_env_alive(simulation_id)
    env_status = SimulationRunner.get_env_status_detail(simulation_id)
    message = (
        "Environment running, ready to receive interview requests"
        if env_alive
        else "Environment not running or closed"
    )
    return json_success({
        "simulation_id": simulation_id,
        "env_alive": env_alive,
        "twitter_available": env_status.get("twitter_available", False),
        "reddit_available": env_status.get("reddit_available", False),
        "message": message,
    })


@simulation_bp.route('/close-env', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to close environment")
def close_simulation_env():
    """Gracefully close a simulation environment and update simulation status."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )
    timeout = data.get('timeout', 30)
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )

    result = SimulationRunner.close_simulation_env(simulation_id=simulation_id, timeout=timeout)
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if state:
        manager._set_status(state, SimulationStatus.COMPLETED)

    # Preserve legacy envelope: outer ``success`` mirrors runner's inner success flag.
    return jsonify({"success": result.get("success", False), "data": result})
