"""
Run-control and live-status routes split from the main simulation API module.
"""

import os

from flask import jsonify, request

from . import simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.persona_review_service import PersonaReviewService
from ..services.llm_routing_seed import (
    build_route_subprocess_env,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from ..api.simulation_prepare import _is_local_endpoint
from ..services.llm_runtime import parse_runtime_llm_config
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
@require_scope("simulation:control")
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
    # Explizite UI-Auswahl (AiModelRef) ist die autoritative Sim-Route und darf
    # nicht still mit Legacy-Feldern kombiniert werden (Issue #817, analog
    # /api/report/generate). Wenn gesetzt, wird die ProviderConnection zur
    # Single Source of Truth für Modell, Base-URL und gebundenen Key — kein
    # .env-Fallback. Root Cause des OASIS-404 ``model MiniMax-M3 not found``:
    # der Legacy-Pfad reichte nur den nackten Modellnamen weiter und produzierte
    # eine Route ohne Base-URL + Default-Provider-Key → CAMEL traf den
    # OpenAI-Default-Endpoint. Der ai_model_ref-Pfad bindet Connection-URL und
    # -Secret atomar (connection_only=True).
    ai_model_ref = None
    raw_ref = data.get('ai_model_ref')
    if raw_ref is not None:
        from pydantic import ValidationError as _ValidationError

        from ..contracts.ai_provider_contract import AiModelRef as _AiModelRef
        try:
            ai_model_ref = _AiModelRef.model_validate(raw_ref)
        except _ValidationError:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="ai_model_ref ist ungültig",
            )
        # Nur die Legacy-Felder prüfen, die dieser Handler auch ausliest und
        # weiterreicht (llm_model → llm_model_override, llm_provider →
        # llm_runtime). llm_profile_id wird im Sim-Start nicht unterstützt und
        # daher nicht als Konfliktgrund geführt — ein Profilpfad ist hier nicht
        # implementiert (CodeRabbit PR #852).
        conflicting = [
            key for key in ('llm_model', 'llm_provider')
            if data.get(key)
        ]
        if conflicting:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=(
                    f"ai_model_ref darf nicht mit {', '.join(conflicting)} "
                    "kombiniert werden"
                ),
            )
        # Legacy-Override stummschalten: die Connection ist maßgeblich.
        llm_model_override = None
        llm_runtime = parse_runtime_llm_config({})
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
                except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
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

    # Pre-Check VOR der Run-Record-Creation, damit kein orphaned Run entsteht
    # (Copilot PR #466, simulation_run.py:247). Dafür simulieren wir die
    # Stage-Auflösung ohne Persistenz: ein leerer Routing-Stub reicht für die
    # Provider/Key-Bestimmung, weil ``seed_run_stage_routing`` nichts anderes
    # tut als Workspace-Default + Override zusammenzuführen.
    if llm_runtime.enabled and not llm_runtime.api_key:
        from ..services.llm_routing_seed import map_runtime_provider_to_route_provider
        from ..services.secret_resolver import SecretResolver
        from ..services.llm_provider_registry import LlmProviderRegistry
        provider_id_preview = map_runtime_provider_to_route_provider(llm_runtime.provider)
        if provider_id_preview:
            registry = LlmProviderRegistry()
            descriptor = next((p for p in registry.get_providers() if p.id == provider_id_preview), None)
            p_type = descriptor.type if descriptor else "openai_compatible"
            stored_key = SecretResolver().get_api_key(provider_id_preview, p_type)
            if not stored_key and not _is_local_endpoint(
                (descriptor.base_url if descriptor else None) or llm_runtime.base_url
            ):
                return json_error(
                    ApiErrorCode.VALIDATION_FAILED,
                    status=422,
                    message=(
                        f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
                        f"für Provider '{provider_id_preview}'. "
                        "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                        "oder im Sitzungsfeld eingeben."
                    ),
                )

    # ai_model_ref-Pre-Check VOR der Run-Record-Creation: die Connection muss
    # existieren, aktiviert sein und (für api_key-Connections) ein gebundenes
    # Secret tragen — sonst kein .env-Fallback, sondern 422 (analog dem
    # Legacy-Pre-Check, kein orphaned Run). Die volle Model-Discovery
    # (Connection/Model-Mismatch, Issue #819) läuft später in
    # ``seed_run_stage_routing``; deren ValueError wird am Endpunkt zu 4xx.
    if ai_model_ref is not None:
        from ..services.llm_routing_seed import prevalidate_ai_model_ref
        try:
            prevalidate_ai_model_ref(ai_model_ref)
        except ValueError as exc:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=422,
                message=str(exc),
            )

    run_record = run_registry.create_run(
        run_type="simulation_run",
        entity_id=simulation_id,
        status="pending",
        progress=0,
        message="Simulation run queued",
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
    seed_run_stage_routing(
        run_record["run_id"],
        "simulation_rounds",
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
        ai_model_ref=ai_model_ref,
    )
    route_router = StageModelRouter(run_record["run_id"])
    resolved_route = route_router.resolve("simulation_rounds")
    route_router.lock_stage("simulation_rounds", resolved_route)
    resolved_api_key = resolve_route_api_key(resolved_route, llm_runtime)

    if resolved_api_key is None and not _is_local_endpoint(resolved_route.base_url_sanitized):
        # Fallback-422 bleibt für Workspace-Default-Fälle (kein Frontend-Override) —
        # da kann die Run-Record schon erstellt sein; markiere sie als failed,
        # damit keine Phantom-Runs in der Liste landen.
        try:
            run_registry.update_run(
                run_record["run_id"],
                status="failed",
                message=f"Missing API key for provider {resolved_route.provider_id}",
            )
        except Exception:  # noqa: BLE001 — best effort
            logger.warning("Failed to mark orphaned run as failed", exc_info=True)
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=422,
            message=(
                f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
                f"für Provider '{resolved_route.provider_id}'. "
                "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                "oder im Sitzungsfeld eingeben."
            ),
        )

    if simulation_days is not None or llm_model_override or llm_runtime.enabled or ai_model_ref is not None:
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
        if llm_model_override or ai_model_ref is not None:
            config["llm_model"] = resolved_route.model
        if (llm_runtime.enabled or ai_model_ref is not None) and resolved_route.base_url_sanitized:
            config["llm_base_url"] = resolved_route.base_url_sanitized
        store.write_json(simulation_id, "simulation_config", config)

    run_state = SimulationRunner.start_simulation(
        simulation_id=simulation_id,
        platform=platform,
        max_rounds=max_rounds,
        enable_graph_memory_update=enable_graph_memory_update,
        graph_id=graph_id,
        runtime_env=build_route_subprocess_env(
            resolved_route,
            resolved_api_key,
            run_record["run_id"],
        ),
    )

    manager._set_status(state, SimulationStatus.RUNNING)
    run_registry.update_run(
        run_record["run_id"],
        status="processing",
        progress=0,
        message="Simulation run started",
        resume_capability=_simulation_resume_capability(simulation_id, state),
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
@require_scope("simulation:control")
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
@require_scope("simulation:control")
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
@require_scope("simulation:control")
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
# TODO(scope-rollout): explicit @require_scope("simulation:read") after grace period — Code-Review 2026-05-17 §3.3
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
    """
    Liefert den detaillierten Laufstatus mit aggregierten Aktionszahlen und paginierten Aktionen.
    
    Parameter:
    	simulation_id (str): ID der Simulation.
    
    Returns:
    	Response: JSON-Antwort mit Laufstatus, Aktionszahlen, paginierten Aktionen und aktuellen Rundenaktionen.
    """
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
            "actions_total": 0,
            "actions": [],
            "all_actions": [],
            "twitter_actions": [],
            "reddit_actions": [],
        })

    # Pagination-Parameter für actions-Subquery
    limit = clamp_int(
        request.args.get('limit', type=int),
        default=DEFAULT_LIMIT,
        minimum=1,
        maximum=MAX_LIMIT,
    )
    offset = max(request.args.get('offset', 0, type=int), 0)

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

    # Paginierte actions-Subquery (Aggregat-Felder bleiben im Top-Level)
    paginated_actions = SimulationRunner.get_actions(
        simulation_id=simulation_id,
        limit=limit,
        offset=offset,
        platform=platform_filter,
    )

    result = run_state.to_dict()
    # Aggregate + Counts statt redundanter Full-Lists (Gemini-Review PR #526).
    # Detail-Daten holt der Client über die paginierte `actions`-Subquery
    # bzw. /actions?platform=... — das Pagination-Ziel wäre sonst untergraben.
    result["actions_total"] = len(all_actions)
    result["actions"] = [action.to_dict() for action in paginated_actions]
    result["twitter_actions_count"] = len(twitter_actions)
    result["reddit_actions_count"] = len(reddit_actions)
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

    limit = clamp_int(
        request.args.get('limit', type=int),
        default=DEFAULT_LIMIT,
        minimum=1,
        maximum=MAX_LIMIT,
    )
    offset = max(request.args.get('offset', 0, type=int), 0)
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
