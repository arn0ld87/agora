"""
Shared helpers for simulation-related API modules.
"""

from flask import current_app, request

from . import runs_bp, simulation_bp
from ..contracts.auth_contract import AuthType
from ..security.principal_context import current_principal
from ..services.artifact_store import SimulationArtifactStore
from ..services.llm_routing_seed import demo_mode_enabled
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

# Finding M1 (Security-Review 2026-09-26, #1688): ein Replay oder Resume löst
# denselben LLM-Traffic aus wie ein frischer Start, lief bisher aber weder
# durch dieses Rate-Limit noch durch die Demo-Rundenobergrenze — beide
# Endpoints leben auf ``runs_bp``, nicht auf ``simulation_bp``, dessen
# ``before_request`` sie deshalb nie erreichte.
_LLM_TRIGGER_ENDPOINTS = {
    "simulation.generate_profiles",
    "simulation.prepare_simulation",
    "simulation.start_simulation",
    "runs.replay_run",
    "runs.resume_run",
}


def _llm_trigger_rate_limit_key() -> str:
    return build_rate_limit_key("simulation-llm-trigger", include_endpoint=True)


def _limit_llm_trigger_endpoints():
    if request.method != "POST" or request.endpoint not in _LLM_TRIGGER_ENDPOINTS:
        return None

    # Finding M1: ``runs_bp`` läuft in einigen bestehenden Tests als
    # eigenständige Blueprint-App ohne vollen ``Config``-Import — ``.get()``
    # mit denselben Defaults wie ``Config`` statt hartem Key-Zugriff, sonst
    # würde jeder POST auf ``/replay``/``/resume`` in diesen Tests mit einem
    # ``KeyError`` statt der beabsichtigten Rate-Limit-Prüfung scheitern.
    result = llm_trigger_rate_limiter.check(
        _llm_trigger_rate_limit_key(),
        max_requests=current_app.config.get("AGORA_LLM_TRIGGER_RATE_LIMIT_MAX", 20),
        window_seconds=current_app.config.get(
            "AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS", 60
        ),
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


# ``runs_bp.route("/<run_id>/replay")`` und ``.../resume`` liegen auf einem
# eigenen Blueprint (Issue-Fund M1) — derselbe Rate-Limiter muss deshalb auf
# beiden Blueprints registriert werden, nicht nur auf ``simulation_bp``.
simulation_bp.before_request(_limit_llm_trigger_endpoints)
runs_bp.before_request(_limit_llm_trigger_endpoints)


class DemoLimitExceededError(Exception):
    """Raised when a demo-mode JWT run would exceed the hard round/budget cap."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _demo_jwt_principal_active() -> bool:
    if not demo_mode_enabled():
        return False
    principal = current_principal()
    return principal is not None and principal.auth_type == AuthType.JWT


def apply_demo_run_limits(max_rounds, budget_config):
    """Cap max_rounds/budget for a JWT run on an explicitly enabled demo instance.

    Finding M1: shared by ``/simulation/start``
    (``simulation_run._apply_demo_start_limits``) and the run replay/resume
    endpoints in ``runs.py``, so a demo JWT visitor cannot bypass the hard
    round/budget cap by cloning or restarting a run instead of starting a
    fresh one. Operator (master-token) runs and non-demo instances are
    returned unchanged.
    """
    if not _demo_jwt_principal_active():
        return max_rounds, budget_config
    if max_rounds is not None and max_rounds > 5:
        raise DemoLimitExceededError("Demo simulations allow at most 5 rounds")

    from ..contracts.run_budget_contract import RunBudgetConfig

    budget = budget_config or RunBudgetConfig.model_validate({})
    bounded_budget = budget.model_copy(update={
        "enforcement": "hard",
        "max_llm_calls": min(budget.max_llm_calls or 200, 200),
        "max_duration_seconds": min(budget.max_duration_seconds or 1800, 1800),
    })
    return max_rounds or 5, bounded_budget


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
