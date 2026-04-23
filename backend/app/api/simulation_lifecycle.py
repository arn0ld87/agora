"""
Lifecycle and metadata endpoints split from the main simulation API module.
"""

import os

from flask import current_app, request

from . import simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.validation import validate_graph_id, validate_project_id, validate_simulation_id
from .simulation_common import logger


@simulation_bp.route('/available-models', methods=['GET'])
def get_available_models():
    """
    Return the curated LLM presets plus locally installed Ollama models.
    """
    import requests

    presets = list(Config.LLM_MODEL_PRESETS or [])
    ollama_models = []
    ollama_error = None

    base = (Config.LLM_BASE_URL or '').rstrip('/')
    if base.endswith('/v1'):
        base = base[:-3]
    if not base:
        base = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')

    try:
        resp = requests.get(f"{base}/api/tags", timeout=2.5)
        resp.raise_for_status()
        payload = resp.json() or {}
        for model in payload.get('models', []) or []:
            name = model.get('name')
            if not name:
                continue
            details = model.get('details') or {}
            ollama_models.append({
                "name": name,
                "label": name,
                "size": model.get('size'),
                "family": details.get('family'),
                "parameter_size": details.get('parameter_size'),
                "kind": "ollama",
            })
    except Exception as exc:
        ollama_error = str(exc)
        logger.info(f"Could not reach Ollama at {base}: {exc}")

    storage = current_app.extensions.get('neo4j_storage')
    neo4j_reachable = storage is not None
    neo4j_error = None
    if storage is None:
        neo4j_error = current_app.extensions.get('neo4j_storage_error') or (
            "Neo4j storage not initialised — check NEO4J_URI / NEO4J_PASSWORD and that Neo4j is running."
        )

    return json_success({
        "ollama": ollama_models,
        "presets": presets,
        "current_default": Config.LLM_MODEL_NAME,
        "ollama_base_url": base,
        "ollama_reachable": ollama_error is None,
        "ollama_error": ollama_error,
        "neo4j_reachable": neo4j_reachable,
        "neo4j_error": neo4j_error,
        "neo4j_uri": Config.NEO4J_URI,
        "default_language": Config.AGENT_LANGUAGE,
        "agent_tools_enabled": Config.ENABLE_AGENT_TOOLS,
        "max_tool_calls_per_action": Config.MAX_TOOL_CALLS_PER_ACTION,
    })


@simulation_bp.route('/create', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to create simulation")
def create_simulation():
    """Create a new simulation."""
    data = request.get_json() or {}

    project_id = data.get('project_id')
    if not project_id:
        return json_error("Please provide project_id")
    if not validate_project_id(project_id):
        return json_error("Invalid project_id format")

    project = ProjectManager.get_project(project_id)
    if not project:
        return json_error(f"Project does not exist: {project_id}", status=404)

    graph_id = data.get('graph_id') or project.graph_id
    if not graph_id:
        return json_error(
            "Project has not built knowledge graph yet, please call /api/graph/build first"
        )
    if not validate_graph_id(graph_id):
        return json_error("Invalid graph_id format")

    manager = SimulationManager()
    state = manager.create_simulation(
        project_id=project_id,
        graph_id=graph_id,
        enable_twitter=data.get('enable_twitter', True),
        enable_reddit=data.get('enable_reddit', True),
    )
    return json_success(state.to_dict())


@simulation_bp.route('/<simulation_id>', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get simulation status")
def get_simulation(simulation_id: str):
    """Get simulation status."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format")

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

    result = state.to_dict()
    if state.status == SimulationStatus.READY:
        result["run_instructions"] = manager.get_run_instructions(simulation_id)
    return json_success(result)


@simulation_bp.route('/list', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to list simulations")
def list_simulations():
    """List simulations, optionally filtered by project_id."""
    project_id = request.args.get('project_id')

    manager = SimulationManager()
    simulations = manager.list_simulations(project_id=project_id)

    return json_success(
        [simulation.to_dict() for simulation in simulations],
        count=len(simulations),
    )
