"""
Shared helpers for simulation-related API modules.
"""

from flask import current_app, request

from . import simulation_bp
from ..services.artifact_store import SimulationArtifactStore
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from ..utils.rate_limit import build_rate_limit_key, llm_trigger_rate_limiter

logger = get_logger('agora.api.simulation')
run_registry = RunRegistry()

# Adding this prefix can prevent agents from calling tools and reply directly with text.
INTERVIEW_PROMPT_PREFIX = (
    "Based on your persona, all your past memories and actions, reply directly to me "
    "with text without calling any tools:"
)

_LLM_TRIGGER_ENDPOINTS = {
    "simulation.generate_profiles",
    "simulation.prepare_simulation",
}


def _llm_trigger_rate_limit_key() -> str:
    return build_rate_limit_key("simulation-llm-trigger", include_endpoint=True)


@simulation_bp.before_request
def _limit_llm_trigger_endpoints():
    if request.method != "POST" or request.endpoint not in _LLM_TRIGGER_ENDPOINTS:
        return None

    result = llm_trigger_rate_limiter.check(
        _llm_trigger_rate_limit_key(),
        max_requests=current_app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"],
        window_seconds=current_app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"],
    )
    if result.allowed:
        return None

    response, status = json_error(
        ApiErrorCode.RATE_LIMITED,
        status=429,
        extra={"retry_after_seconds": result.retry_after_seconds},
    )
    response.headers["Retry-After"] = str(result.retry_after_seconds)
    return response, status


def optimize_interview_prompt(prompt: str) -> str:
    """Normalize interview prompts so agents answer directly."""
    if not prompt:
        return prompt
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def get_simulation_storage():
    """Fetch Neo4j storage from the Flask app context."""
    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        raise ValueError("GraphStorage not initialized")
    return storage


def get_artifact_store() -> SimulationArtifactStore:
    """Fetch the SimulationArtifactStore from the Flask app context (Issue #13)."""
    store = current_app.extensions.get('artifact_store')
    if store is None:
        raise RuntimeError("SimulationArtifactStore not initialized")
    return store


def simulation_run_artifacts(simulation_id: str):
    return ArtifactLocator.existing_paths({
        "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
    })


def simulation_resume_capability(simulation_id: str, state=None):
    store = get_artifact_store()
    has_config = store.exists(simulation_id, "simulation_config")
    has_control = store.exists(simulation_id, "control_state")
    run_state = SimulationRunner.get_run_state(simulation_id)
    current_state = state or SimulationManager().get_simulation(simulation_id)

    if run_state and run_state.runner_status == RunnerStatus.PAUSED:
        return {"available": True, "action": "resume", "label": "Resume run"}
    if run_state and run_state.runner_status == RunnerStatus.STOPPED and has_config:
        return {"available": True, "action": "restart", "label": "Restart run"}
    if current_state and current_state.status == SimulationStatus.READY and has_config:
        return {"available": True, "action": "restart", "label": "Start run"}
    if has_control and has_config:
        return {"available": True, "action": "restart", "label": "Restart run"}
    return {"available": False, "action": None, "label": None}
