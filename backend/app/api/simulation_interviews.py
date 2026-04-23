"""
Interview-related simulation API routes split from the main module.
"""

from flask import jsonify, request

from . import simulation_bp
from ..services.simulation_runner import SimulationRunner
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.validation import validate_simulation_id
from .simulation_common import logger, optimize_interview_prompt


def _require_simulation_id(simulation_id):
    """Shared guard: simulation_id present + well-formed."""
    if not simulation_id:
        return json_error("Please provide simulation_id")
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format")
    return None


def _validate_platform(platform):
    if platform and platform not in ("twitter", "reddit"):
        return json_error("platform Parameter can only be 'twitter' Or 'reddit'")
    return None


def _require_env_alive(simulation_id: str):
    if not SimulationRunner.check_env_alive(simulation_id):
        return json_error(
            "Simulation environment not running or closed. "
            "Please ensure simulation is started and wait for it to progress."
        )
    return None


def _echo_result(result: dict):
    """Return result as data while mirroring its internal ``success`` flag at the envelope level.

    Preserves the legacy response shape for interview endpoints, where the
    outer ``success`` tracked the runner's internal success rather than the HTTP
    layer outcome.
    """
    return jsonify({"success": result.get("success", False), "data": result})


@simulation_bp.route('/interview', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="InterviewFailed")
def interview_agent():
    """Interview a single agent."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')

    error = _require_simulation_id(simulation_id)
    if error:
        return error

    agent_id = data.get('agent_id')
    prompt = data.get('prompt')
    platform = data.get('platform')
    timeout = data.get('timeout', 60)

    if agent_id is None:
        return json_error("Please provide agent_id")
    if not prompt:
        return json_error("Please provide prompt（Interview question）")

    platform_error = _validate_platform(platform)
    if platform_error:
        return platform_error

    env_error = _require_env_alive(simulation_id)
    if env_error:
        return env_error

    optimized_prompt = optimize_interview_prompt(prompt)
    result = SimulationRunner.interview_agent(
        simulation_id=simulation_id,
        agent_id=agent_id,
        prompt=optimized_prompt,
        platform=platform,
        timeout=timeout,
    )
    return _echo_result(result)


@simulation_bp.route('/interview/batch', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="BatchInterviewFailed")
def interview_agents_batch():
    """Interview multiple agents in one request."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')

    error = _require_simulation_id(simulation_id)
    if error:
        return error

    interviews = data.get('interviews')
    platform = data.get('platform')
    timeout = data.get('timeout', 120)

    if not interviews or not isinstance(interviews, list):
        return json_error("Please provide interviews（Interview list）")

    platform_error = _validate_platform(platform)
    if platform_error:
        return platform_error

    for index, interview in enumerate(interviews, 1):
        if 'agent_id' not in interview:
            return json_error(f"Interview list item{index}Missing agent_id")
        if 'prompt' not in interview:
            return json_error(f"Interview list item{index}Missing prompt")
        item_platform = interview.get('platform')
        if item_platform and item_platform not in ("twitter", "reddit"):
            return json_error(
                f"Interview list item {index}: platform must be 'twitter' or 'reddit'"
            )

    env_error = _require_env_alive(simulation_id)
    if env_error:
        return env_error

    optimized_interviews = []
    for interview in interviews:
        optimized = interview.copy()
        optimized['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
        optimized_interviews.append(optimized)

    result = SimulationRunner.interview_agents_batch(
        simulation_id=simulation_id,
        interviews=optimized_interviews,
        platform=platform,
        timeout=timeout,
    )
    return _echo_result(result)


@simulation_bp.route('/interview/all', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="GlobalInterviewFailed")
def interview_all_agents():
    """Interview all agents with a shared prompt."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')

    error = _require_simulation_id(simulation_id)
    if error:
        return error

    prompt = data.get('prompt')
    platform = data.get('platform')
    timeout = data.get('timeout', 180)

    if not prompt:
        return json_error("Please provide prompt（Interview question）")

    platform_error = _validate_platform(platform)
    if platform_error:
        return platform_error

    env_error = _require_env_alive(simulation_id)
    if env_error:
        return env_error

    optimized_prompt = optimize_interview_prompt(prompt)
    result = SimulationRunner.interview_all_agents(
        simulation_id=simulation_id,
        prompt=optimized_prompt,
        platform=platform,
        timeout=timeout,
    )
    return _echo_result(result)


@simulation_bp.route('/interview/history', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to get interview history")
def get_interview_history():
    """Get stored interview history for a simulation."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')

    error = _require_simulation_id(simulation_id)
    if error:
        return error

    platform = data.get('platform')
    agent_id = data.get('agent_id')
    limit = data.get('limit', 100)

    history = SimulationRunner.get_interview_history(
        simulation_id=simulation_id,
        platform=platform,
        agent_id=agent_id,
        limit=limit,
    )
    return json_success({"count": len(history), "history": history})
