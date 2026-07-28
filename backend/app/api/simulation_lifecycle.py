"""
Lifecycle and metadata endpoints split from the main simulation API module.
"""

import os

from flask import current_app, request
from opentelemetry import trace

from . import simulation_bp
from ..config import Config
from ..llm.providers.registry import detect_provider, resolve_ollama_tags_url
from ..models.project import ProjectManager
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.validation import validate_graph_id, validate_project_id, validate_simulation_id
from .simulation_common import logger

_tracer = trace.get_tracer(__name__)


def _detect_default_provider() -> str:
    """Infer the configured server-side LLM provider for UI gating.

    Delegiert an die Provider-Detection-SSoT
    ``app.llm.providers.registry.detect_provider`` im ``mode="http"``
    (Issue #669) statt eine lokale Heuristik zu pflegen. Vokabular:
    ``ollama|cloud|minimax|openai|google|unknown``.
    """
    model_name = (Config.LLM_MODEL_NAME or '').strip()
    base_url = (Config.LLM_BASE_URL or '').strip()
    return detect_provider(base_url, model_name, mode="http")


@simulation_bp.route('/available-models', methods=['GET'])
def get_available_models():
    """Return the curated LLM presets plus locally installed Ollama models.

    Ollama-Models werden alphabetisch sortiert. ``LLM_MODEL_PRESETS`` mit
    ``kind="ollama"`` werden nur durchgelassen, wenn das Modell tatsächlich in
    den Ollama-Tags steht — sonst landen halluzinierte Einträge (z. B.
    ``qwen2.5:32b`` ohne Install) im UI-Dropdown. Cloud-Presets bleiben, weil
    sie über andere Provider-Discovery-Pfade verifiziert werden.

    Ist der aktive Provider kein Ollama-kompatibler Server (MiniMax/OpenAI/
    Google), wird der ``/api/tags``-Probe übersprungen — die Route existiert
    dort nicht. Das Response-Schema erweitert sich additiv um
    ``ollama_skipped`` und ``ollama_skip_reason``.
    """
    import requests

    raw_presets = list(Config.LLM_MODEL_PRESETS or [])
    ollama_models: list = []
    ollama_error: str | None = None
    ollama_skipped = False
    ollama_skipped_provider: str | None = None
    ollama_skip_reason: str | None = None

    base = resolve_ollama_tags_url(
        Config.LLM_BASE_URL,
        Config.LLM_MODEL_NAME,
        explicit_base_url=os.environ.get('OLLAMA_BASE_URL'),
    )

    if base is None:
        # Provider kennt ``/api/tags`` garantiert nicht — Probe überspringen,
        # kein 404 im Log provozieren. ``ollama_skipped_provider`` ist der
        # maschinenlesbare Schlüssel für den i18n-Lookup im Frontend;
        # ``ollama_skip_reason`` bleibt reines Debug-Feld.
        provider = detect_provider(
            Config.LLM_BASE_URL, Config.LLM_MODEL_NAME, mode="http"
        )
        ollama_skipped = True
        ollama_skipped_provider = provider
        ollama_skip_reason = f"Active provider is {provider}"
        logger.debug(
            "Skipping Ollama /api/tags probe: active provider is %s", provider
        )
    else:
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
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            ollama_error = str(exc)
            logger.info(f"Could not reach Ollama at {base}: {exc}")

    ollama_models.sort(key=lambda m: m["name"].lower())
    installed_ollama_names = {m["name"] for m in ollama_models}
    presets = [
        preset for preset in raw_presets
        if preset.get("kind") != "ollama" or preset.get("name") in installed_ollama_names
    ]

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
        "default_provider": _detect_default_provider(),
        "ollama_base_url": base,
        "ollama_reachable": ollama_error is None and not ollama_skipped,
        "ollama_error": ollama_error,
        "ollama_skipped": ollama_skipped,
        "ollama_skipped_provider": ollama_skipped_provider,
        "ollama_skip_reason": ollama_skip_reason,
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
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide project_id",
        )
    if not validate_project_id(project_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid project_id format",
        )

    project = ProjectManager.get_project(project_id)
    if not project:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Project does not exist: {project_id}",
        )

    graph_id = data.get('graph_id') or project.graph_id
    if not graph_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Project has not built knowledge graph yet, please call /api/graph/build first",
        )
    if not validate_graph_id(graph_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid graph_id format",
        )

    enable_twitter = data.get('enable_twitter', True)
    enable_reddit = data.get('enable_reddit', True)
    platforms = ",".join(
        p for p, enabled in [("twitter", enable_twitter), ("reddit", enable_reddit)] if enabled
    )

    with _tracer.start_as_current_span("agora.simulation.create") as span:
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
        )
        span.set_attribute("agora.simulation.id", state.simulation_id)
        span.set_attribute("agora.simulation.platforms", platforms)
        return json_success(state.to_dict())


@simulation_bp.route('/<simulation_id>', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get simulation status")
def get_simulation(simulation_id: str):
    """Get simulation status."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

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
