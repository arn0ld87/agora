"""
Lifecycle and metadata endpoints split from the main simulation API module.
"""

import os
import traceback

from flask import current_app, jsonify, request

from . import simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.simulation_manager import SimulationManager, SimulationStatus
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
        neo4j_error = (
            "Neo4j storage not initialised — check NEO4J_URI / NEO4J_PASSWORD and that Neo4j is running."
        )

    return jsonify({
        "success": True,
        "data": {
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
        },
    })


@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """Create a new simulation."""
    try:
        data = request.get_json() or {}

        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "Please provide project_id",
            }), 400

        if not validate_project_id(project_id):
            return jsonify({"success": False, "error": "Invalid project_id format"}), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project does not exist: {project_id}",
            }), 404

        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Project has not built knowledge graph yet, please call /api/graph/build first",
            }), 400

        if not validate_graph_id(graph_id):
            return jsonify({"success": False, "error": "Invalid graph_id format"}), 400

        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
        )

        return jsonify({
            "success": True,
            "data": state.to_dict(),
        })

    except Exception as exc:
        logger.error(f"Failed to create simulation: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """Get simulation status."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}",
            }), 404

        result = state.to_dict()
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)

        return jsonify({
            "success": True,
            "data": result,
        })

    except Exception as exc:
        logger.error(f"Failed to get simulation status: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """List simulations, optionally filtered by project_id."""
    try:
        project_id = request.args.get('project_id')

        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)

        return jsonify({
            "success": True,
            "data": [simulation.to_dict() for simulation in simulations],
            "count": len(simulations),
        })

    except Exception as exc:
        logger.error(f"Failed to list simulations: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500
