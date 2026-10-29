"""
Action log, rounds, timeline, agent-stats, control, and environment endpoints for simulation runs.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

from flask import jsonify, request
from pydantic import ValidationError

from ..contracts.post_event_contract import Platform
from ..contracts.sim_action_contract import (
    RoundSummary,
    SimActionPage,
    SimActionRecord,
    SimActionType,
)
from ..services.simulation_manager import SimulationStatus
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error, json_success
from ..utils.pagination import clamp_int, DEFAULT_LIMIT, MAX_LIMIT
from .simulation_common import (
    logger,
    simulation_resume_capability as _default_simulation_resume_capability,
    simulation_run_artifacts as _default_simulation_run_artifacts,
)

if TYPE_CHECKING:
    from ..services.sim.run_state_store import AgentAction


def _sim_mod():
    from . import simulation_run
    return simulation_run


def _get_sym(name: str, fallback: Any) -> Any:
    mod = _sim_mod()
    return getattr(mod, name, fallback)


def _decode_actions_cursor(raw: str | None) -> int:
    """Cursor ist ein opakes Offset-Token (str(int)). Ungueltig/negativ -> 0
    statt 400 — dieselbe stille Clamp-Semantik wie das alte offset (#1713)."""
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return max(value, 0)


def _coerce_action_type(raw: str) -> SimActionType:
    """Unbekannte Rohtypen landen in ``OTHER`` — auch beim Filtern (#1713)."""
    try:
        return SimActionType(raw)
    except ValueError:
        return SimActionType.OTHER


def _resolve_target_post_id(action_type: str, args: dict) -> str | None:
    """Post, auf den die Aktion wirkt — nicht der ggf. neu erzeugte Beitrag
    (der steht bereits im Feed-Event, nicht im Protokoll-Ziel)."""
    if action_type in ("LIKE_POST", "DISLIKE_POST", "CREATE_COMMENT"):
        value = args.get("post_id")
    elif action_type == "REPOST":
        value = args.get("original_post_id")
    elif action_type == "QUOTE_POST":
        value = args.get("quoted_id")
    else:
        value = None
    return str(value) if value is not None else None


def _agent_action_to_record(action: "AgentAction") -> SimActionRecord | None:
    """Konvertiert die interne ``AgentAction``-Dataclass in den API-Vertrag
    ``SimActionRecord`` (#1713 UI-2a). Gibt ``None`` bei vertragswidrigen
    Altbestandsdaten zurueck statt die ganze Seite abzureissen — dieselbe
    Degradations-Haltung wie ``evidence_omitted`` bei ``/report/<id>/evidence``.
    """
    args = action.action_args or {}
    action_type = _coerce_action_type(action.action_type)

    comment_id = args.get("comment_id") if action_type in (
        SimActionType.LIKE_COMMENT,
        SimActionType.DISLIKE_COMMENT,
    ) else None

    # Handle timestamp string or datetime
    ts = action.timestamp
    if isinstance(ts, str):
        try:
            ts_dt = datetime.fromisoformat(ts)
        except ValueError:
            ts_dt = datetime.utcnow()
    elif isinstance(ts, datetime):
        ts_dt = ts
    else:
        ts_dt = datetime.utcnow()

    try:
        return SimActionRecord(
            round_num=action.round_num,
            sim_time=None,  # Aktionsprotokoll persistiert keine Sim-Zeit.
            timestamp=ts_dt,
            platform=Platform(action.platform),
            agent_id=str(action.agent_id),
            agent_name=action.agent_name,
            action_type=action_type,
            target_post_id=_resolve_target_post_id(action.action_type, args),
            target_comment_id=str(comment_id) if comment_id is not None else None,
            target_agent_id=None,  # Kein numerischer Ziel-Agent im Protokoll verfuegbar.
            target_agent_name=args.get("target_user_name") or None,
            content=args.get("content") or None,
            success=action.success,
            role_conflict=action.role_conflict,
        )
    except (ValidationError, ValueError, TypeError):
        # Vertragswidriger Altbestand (z. B. unbekannter platform-Wert) darf
        # nicht die ganze Seite abreissen — dieselbe Degradations-Haltung
        # wie ``evidence_omitted`` bei ``/report/<id>/evidence``.
        logger.warning(
            "Failed to convert AgentAction to SimActionRecord (skipped)",
            exc_info=True,
        )
        return None


def execute_stop_simulation():
    """Stop a running simulation."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    runner_cls = _get_sym("SimulationRunner", None)
    run_state = runner_cls.stop_simulation(simulation_id)
    manager_cls = _get_sym("SimulationManager", None)
    manager = manager_cls()
    state = manager.get_simulation(simulation_id)
    if state:
        manager._set_status(state, SimulationStatus.STOPPED)
        reg = _get_sym("run_registry", None)
        run = reg.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
        if run:
            artifacts_fn = _get_sym("_simulation_run_artifacts", _default_simulation_run_artifacts)
            resume_fn = _get_sym("_simulation_resume_capability", _default_simulation_resume_capability)
            reg.update_run(
                run["run_id"],
                status="stopped",
                progress=run_state.to_dict().get("progress_percent", 0),
                message="Simulation stopped",
                message_key="run.simulation_stopped",
                artifacts=artifacts_fn(simulation_id),
                resume_capability=resume_fn(simulation_id, state),
            )
    return json_success(run_state.to_dict())


def execute_pause_simulation(simulation_id: str):
    """Set the soft-pause flag so the simulation halts after the current round."""
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import set_pause_state

    sim_dir_fn = _get_sym("_simulation_dir", None)
    sim_dir = sim_dir_fn(simulation_id)
    if not os.path.isdir(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    state = set_pause_state(sim_dir, True)
    logger.info(f"Pause requested for {simulation_id}")
    reg = _get_sym("run_registry", None)
    run = reg.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        manager_cls = _get_sym("SimulationManager", None)
        sim_state = manager_cls().get_simulation(simulation_id)
        artifacts_fn = _get_sym("_simulation_run_artifacts", _default_simulation_run_artifacts)
        resume_fn = _get_sym("_simulation_resume_capability", _default_simulation_resume_capability)
        reg.update_run(
            run["run_id"],
            status="paused",
            message="Pause requested",
            message_key="run.pause_requested",
            artifacts=artifacts_fn(simulation_id),
            resume_capability=resume_fn(simulation_id, sim_state),
        )
    return json_success({"simulation_id": simulation_id, "control_state": state})


def execute_resume_simulation(simulation_id: str):
    """Clear the pause flag so the simulation continues."""
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import set_pause_state

    sim_dir_fn = _get_sym("_simulation_dir", None)
    sim_dir = sim_dir_fn(simulation_id)
    if not os.path.isdir(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    state = set_pause_state(sim_dir, False)
    logger.info(f"Resume requested for {simulation_id}")
    reg = _get_sym("run_registry", None)
    run = reg.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        manager_cls = _get_sym("SimulationManager", None)
        sim_state = manager_cls().get_simulation(simulation_id)
        artifacts_fn = _get_sym("_simulation_run_artifacts", _default_simulation_run_artifacts)
        resume_fn = _get_sym("_simulation_resume_capability", _default_simulation_resume_capability)
        reg.update_run(
            run["run_id"],
            status="processing",
            message="Run resumed",
            message_key="run.run_resumed",
            artifacts=artifacts_fn(simulation_id),
            resume_capability=resume_fn(simulation_id, sim_state),
        )
    return json_success({"simulation_id": simulation_id, "control_state": state})


def execute_get_simulation_console_log(simulation_id: str):
    """Read incremental subprocess console logs for a simulation."""
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )
    from_line = request.args.get('from_line', 0, type=int)
    runner_cls = _get_sym("SimulationRunner", None)
    data = runner_cls.get_console_log(simulation_id, from_line=from_line)
    return json_success(data)


def execute_get_run_status(simulation_id: str):
    """Get lightweight real-time run status for frontend polling."""
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import read_control_state

    runner_cls = _get_sym("SimulationRunner", None)
    run_state = runner_cls.get_run_state(simulation_id)
    sim_dir_fn = _get_sym("_simulation_dir", None)
    control = read_control_state(sim_dir_fn(simulation_id))
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


def execute_get_run_status_detail(simulation_id: str):
    """
    Liefert den detaillierten Laufstatus mit aggregierten Aktionszahlen und paginierten Aktionen.
    """
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    runner_cls = _get_sym("SimulationRunner", None)
    run_state = runner_cls.get_run_state(simulation_id)
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

    all_actions = runner_cls.get_all_actions(simulation_id=simulation_id, platform=platform_filter)
    twitter_actions = runner_cls.get_all_actions(
        simulation_id=simulation_id, platform="twitter"
    ) if not platform_filter or platform_filter == "twitter" else []
    reddit_actions = runner_cls.get_all_actions(
        simulation_id=simulation_id, platform="reddit"
    ) if not platform_filter or platform_filter == "reddit" else []
    current_round = run_state.current_round
    recent_actions = runner_cls.get_all_actions(
        simulation_id=simulation_id,
        platform=platform_filter,
        round_num=current_round,
    ) if current_round > 0 else []

    # Paginierte actions-Subquery (Aggregat-Felder bleiben im Top-Level)
    paginated_actions = runner_cls.get_actions(
        simulation_id=simulation_id,
        limit=limit,
        offset=offset,
        platform=platform_filter,
    )

    result = run_state.to_dict()
    result["actions_total"] = len(all_actions)
    result["actions"] = [action.to_dict() for action in paginated_actions]
    result["twitter_actions_count"] = len(twitter_actions)
    result["reddit_actions_count"] = len(reddit_actions)
    result["rounds_count"] = len(run_state.rounds)
    result["recent_actions"] = [action.to_dict() for action in recent_actions]
    return json_success(result)


def execute_get_simulation_actions(simulation_id: str):
    """Cursor-paginiertes Aktionsprotokoll (#1713 UI-2a, ``SimActionPage``)."""
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
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
    decode_cursor_fn = _get_sym("_decode_actions_cursor", _decode_actions_cursor)
    offset = decode_cursor_fn(request.args.get('cursor'))
    platform = request.args.get('platform')
    agent_id = request.args.get('agent_id', type=int)
    round_num = request.args.get('round_num', type=int)
    action_type_raw = request.args.get('action_type')
    action_type_filter: SimActionType | None = None
    if action_type_raw is not None:
        try:
            action_type_filter = SimActionType(action_type_raw)
        except ValueError:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message=f"Unbekannter action_type: {action_type_raw!r}",
                status=400,
            )

    runner_cls = _get_sym("SimulationRunner", None)
    matching = runner_cls.get_all_actions(
        simulation_id=simulation_id,
        platform=platform,
        agent_id=agent_id,
        round_num=round_num,
    )
    coerce_fn = _get_sym("_coerce_action_type", _coerce_action_type)
    if action_type_filter is not None:
        matching = [
            a for a in matching if coerce_fn(a.action_type) is action_type_filter
        ]

    page_slice = matching[offset:offset + limit]
    next_offset = offset + limit
    next_cursor = str(next_offset) if next_offset < len(matching) else None

    agent_fn = _get_sym("_agent_action_to_record", _agent_action_to_record)
    items = [
        record
        for record in (agent_fn(a) for a in page_slice)
        if record is not None
    ]
    page = SimActionPage(items=items, next_cursor=next_cursor)
    return json_success(page.model_dump(mode="json"))


def execute_get_simulation_rounds(simulation_id: str):
    """Aktionsbilanz je Runde und Plattform (#1713 UI-2a, ``RoundSummary``).

    Anders als ``/timeline`` (ein kombinierter Eintrag je Runde ueber beide
    Plattformen) liefert dieser Endpoint einen Eintrag je (round_num,
    platform) — die Runden-Ansicht des Feeds filtert je Plattform.
    """
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    runner_cls = _get_sym("SimulationRunner", None)
    actions = runner_cls.get_all_actions(simulation_id=simulation_id)
    grouped: dict[tuple[int, str], dict[SimActionType, int]] = {}
    for action in actions:
        key = (action.round_num, action.platform)
        counts = grouped.setdefault(key, {})
        try:
            action_type = SimActionType(action.action_type)
        except ValueError:
            action_type = SimActionType.OTHER
        counts[action_type] = counts.get(action_type, 0) + 1

    summaries: list[RoundSummary] = []
    for (round_num, platform), counts in grouped.items():
        try:
            plat = Platform(platform)
        except ValueError:
            logger.warning(
                "get_simulation_rounds: unbekannter platform-Wert %r in Altbestand — "
                "Eintrag wird uebersprungen",
                platform,
            )
            continue
        summaries.append(RoundSummary(round_num=round_num, platform=plat, action_counts=counts))
    summaries.sort(key=lambda s: (s.round_num, s.platform.value))
    return json_success({"rounds": [s.model_dump(mode="json") for s in summaries]})


def execute_get_simulation_timeline(simulation_id: str):
    """Get round-level timeline summaries for a simulation."""
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    start_round = request.args.get('start_round', 0, type=int)
    end_round = request.args.get('end_round', type=int)
    runner_cls = _get_sym("SimulationRunner", None)
    timeline = runner_cls.get_timeline(
        simulation_id=simulation_id,
        start_round=start_round,
        end_round=end_round,
    )
    return json_success({"rounds_count": len(timeline), "timeline": timeline})


def execute_get_agent_stats(simulation_id: str):
    """Get aggregated per-agent statistics."""
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    runner_cls = _get_sym("SimulationRunner", None)
    stats = runner_cls.get_agent_stats(simulation_id)
    return json_success({"agents_count": len(stats), "stats": stats})


def execute_get_env_status():
    """Get current simulation environment availability."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if not validate_fn(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    runner_cls = _get_sym("SimulationRunner", None)
    env_alive = runner_cls.check_env_alive(simulation_id)
    env_status = runner_cls.get_env_status_detail(simulation_id)
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


def execute_close_simulation_env():
    """Gracefully close a simulation environment and update simulation status."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    validate_fn = _get_sym("validate_simulation_id", lambda s: True)
    if simulation_id and not validate_fn(simulation_id):
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

    runner_cls = _get_sym("SimulationRunner", None)
    result = runner_cls.close_simulation_env(simulation_id=simulation_id, timeout=timeout)
    manager_cls = _get_sym("SimulationManager", None)
    manager = manager_cls()
    state = manager.get_simulation(simulation_id)
    if state:
        manager._set_status(state, SimulationStatus.COMPLETED)

    # Preserve legacy envelope: outer ``success`` mirrors runner's inner success flag.
    return jsonify({"success": result.get("success", False), "data": result})
