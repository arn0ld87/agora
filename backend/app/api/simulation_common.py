"""
Shared helpers for simulation-related API modules.
"""

import os

from flask import current_app

from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger

logger = get_logger('agora.api.simulation')
run_registry = RunRegistry()

# Adding this prefix can prevent agents from calling tools and reply directly with text.
INTERVIEW_PROMPT_PREFIX = (
    "Based on your persona, all your past memories and actions, reply directly to me "
    "with text without calling any tools:"
)


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


def simulation_run_artifacts(simulation_id: str):
    return ArtifactLocator.existing_paths({
        "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
    })


def simulation_resume_capability(simulation_id: str, state=None):
    control_state_path = ArtifactLocator.simulation_file(simulation_id, "control_state.json")
    config_path = ArtifactLocator.simulation_file(simulation_id, "simulation_config.json")
    run_state = SimulationRunner.get_run_state(simulation_id)
    current_state = state or SimulationManager().get_simulation(simulation_id)

    if run_state and run_state.runner_status == RunnerStatus.PAUSED:
        return {"available": True, "action": "resume", "label": "Resume run"}
    if run_state and run_state.runner_status == RunnerStatus.STOPPED and os.path.exists(config_path):
        return {"available": True, "action": "restart", "label": "Restart run"}
    if current_state and current_state.status == SimulationStatus.READY and os.path.exists(config_path):
        return {"available": True, "action": "restart", "label": "Start run"}
    if os.path.exists(control_state_path) and os.path.exists(config_path):
        return {"available": True, "action": "restart", "label": "Restart run"}
    return {"available": False, "action": None, "label": None}
