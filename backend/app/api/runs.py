"""
Run registry API.
"""

from __future__ import annotations

import threading
import traceback
from collections.abc import Mapping
from typing import Any, Optional

from flask import current_app, request

from pydantic import ValidationError

from . import runs_bp
from ..config import Config
from ..contracts.runs_contract import (
    RunDetail,
    RunsAggregation,
    RunsFilterQuery,
    RunsListResponse,
)
from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager, TaskStatus
from ..container import get_container
from ..services.graph_builder import GraphBuilderService  # noqa: F401
from ..services.graph_tools import GraphToolsService
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import RunnerStatus, SimulationRunner
from ..services.sim.cancel_flag import request_cancel as _request_cancel
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.llm_client import LLMClient
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from ..utils.validation import validate_run_id

logger = get_logger("agora.api.runs")
run_registry = RunRegistry()


def _simulation_artifacts(simulation_id: str):
    return ArtifactLocator.existing_paths({
        "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
    })


def _get_run_or_404(run_id: str):
    if not validate_run_id(run_id):
        return None, json_error("Invalid run_id format", status=400)
    run = run_registry.get_run(run_id)
    if not run:
        return None, json_error(f"Run does not exist: {run_id}", status=404)
    return run, None


def _linked_or_entity_id(run: Mapping[str, Any], linked_key: str, label: str) -> str:
    linked_ids = run.get("linked_ids")
    value = linked_ids.get(linked_key) if isinstance(linked_ids, Mapping) else None
    if value is None:
        value = run.get("entity_id")
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Run is missing {label} linkage")


def _resolve_simulation_summary(simulation_id: str, sim_cache: dict) -> dict:
    if simulation_id in sim_cache:
        return sim_cache[simulation_id]

    entry: dict = {"config": None, "state": None, "persona_count": None}
    try:
        manager = SimulationManager()
        entry["config"] = manager.get_simulation_config(simulation_id)
        entry["state"] = manager.get_simulation(simulation_id)
    except Exception as exc:  # pragma: no cover - defensive read path
        logger.debug("Could not load simulation %s for run summary: %s", simulation_id, exc)

    store = current_app.extensions.get("artifact_store") if current_app else None
    if store is not None:
        try:
            if store.exists(simulation_id, "reddit_profiles"):
                profiles = store.read_json(simulation_id, "reddit_profiles", default=[]) or []
                if isinstance(profiles, list):
                    entry["persona_count"] = len(profiles)
        except Exception as exc:  # pragma: no cover - defensive read path
            logger.debug("Could not read reddit_profiles for %s: %s", simulation_id, exc)

    sim_cache[simulation_id] = entry
    return entry


def _resolve_project(project_id: str, project_cache: dict):
    if project_id in project_cache:
        return project_cache[project_id]
    try:
        project = ProjectManager.get_project(project_id)
    except Exception as exc:  # pragma: no cover - defensive read path
        logger.debug("Could not load project %s for run summary: %s", project_id, exc)
        project = None
    project_cache[project_id] = project
    return project


def _build_run_summary(run: dict, *, sim_cache: dict, project_cache: dict) -> dict:
    """Derive display fields for a run manifest without persisting them.

    Read-path enrichment: model, document name, persona count, graph metadata.
    Per-request caches keep N+1 reads bounded over a list response.
    """
    linked = run.get("linked_ids", {}) or {}
    metadata = run.get("metadata", {}) or {}

    summary: dict = {
        "model": None,
        "document_name": None,
        "persona_count": None,
        "graph_id": linked.get("graph_id") or metadata.get("graph_id"),
        "graph_name": metadata.get("graph_name"),
        "branch_name": run.get("branch_label") or metadata.get("branch_name"),
    }

    project_id = linked.get("project_id") or metadata.get("project_id")
    if project_id:
        project = _resolve_project(project_id, project_cache)
        if project is not None:
            files = getattr(project, "files", []) or []
            names: list = []
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("original_filename") or entry.get("filename")
                if name:
                    names.append(name)
            if names:
                summary["document_name"] = (
                    names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1})"
                )
            if not summary["graph_name"] and getattr(project, "name", None):
                summary["graph_name"] = project.name
            if not summary["graph_id"] and getattr(project, "graph_id", None):
                summary["graph_id"] = project.graph_id

    simulation_id = linked.get("simulation_id")
    if simulation_id:
        sim_entry = _resolve_simulation_summary(simulation_id, sim_cache)
        config = sim_entry.get("config") or {}
        state = sim_entry.get("state")
        if config:
            summary["model"] = config.get("llm_model") or summary["model"]
            if not summary["graph_id"]:
                summary["graph_id"] = config.get("graph_id")
        if state is not None:
            if not summary["graph_id"]:
                summary["graph_id"] = getattr(state, "graph_id", None)
            if not summary["branch_name"]:
                summary["branch_name"] = getattr(state, "branch_name", None)
        summary["persona_count"] = sim_entry.get("persona_count")

    return summary


def _attach_summary(run: dict, sim_cache: dict, project_cache: dict) -> dict:
    enriched = dict(run)
    enriched["summary"] = _build_run_summary(
        run, sim_cache=sim_cache, project_cache=project_cache
    )
    return enriched


def _parse_status_param(args) -> list | None:
    """Parse ?status= query param: supports multi-value and comma-separated."""
    raw_values = args.getlist("status")
    if not raw_values:
        return None
    # Flatten comma-separated entries: ?status=processing,pending
    statuses: list[str] = []
    for v in raw_values:
        for part in v.split(","):
            stripped = part.strip()
            if stripped:
                statuses.append(stripped)
    return statuses if statuses else None


@runs_bp.route("", methods=["GET"])
@handle_api_errors(logger=logger, log_prefix="Failed to list runs")
def list_runs():
    # Collect and validate query parameters via Pydantic.
    raw_params: dict = {
        "limit": request.args.get("limit", 50, type=int),
        "offset": request.args.get("offset", 0, type=int),
        "simulation_id": request.args.get("simulation_id"),
        "since": request.args.get("since"),
        "aggregate": request.args.get("aggregate"),
    }
    status_list = _parse_status_param(request.args)
    if status_list is not None:
        raw_params["status"] = status_list

    # Remove None-valued keys so Pydantic uses field defaults.
    raw_params = {k: v for k, v in raw_params.items() if v is not None}

    try:
        fq = RunsFilterQuery.model_validate(raw_params)
    except ValidationError as exc:
        return json_error(exc.errors(), status=400)

    # Pass legacy filter params through unchanged for backwards compatibility.
    runs = run_registry.list_runs(
        project_id=request.args.get("project"),
        run_type=request.args.get("run_type"),
        statuses=[str(s) for s in fq.status] if fq.status else None,
        branch=request.args.get("branch"),
        entity_id=request.args.get("entity_id"),
        simulation_id=fq.simulation_id,
        since=fq.since.isoformat() if fq.since else None,
        limit=fq.limit,
        offset=fq.offset,
    )

    sim_cache: dict = {}
    project_cache: dict = {}
    enriched = [_attach_summary(run, sim_cache, project_cache) for run in runs]

    # Build optional status aggregation (full scan, not page-scoped).
    aggregation = None
    if fq.aggregate == "status":
        counts = run_registry.aggregate_by_status(
            project_id=request.args.get("project"),
            run_type=request.args.get("run_type"),
            simulation_id=fq.simulation_id,
        )
        aggregation = RunsAggregation(counts=counts, total=sum(counts.values()))

    response = RunsListResponse(
        runs=[RunDetail.model_validate(r) for r in enriched],
        total=len(enriched),
        aggregation=aggregation,
    )
    return json_success(
        response.model_dump(mode="json"),
        count=response.total,
    )


def _build_run_detail(run: dict) -> dict:
    """Attach live metrics to a run manifest before serialisation.

    eta_seconds: taken from run metadata if present (populated by the runner).
    log_tail: last up-to-20 event messages — no extra I/O needed.
    metrics: subset of manifest fields as typed scalars.
    """
    enriched = _attach_summary(run, {}, {})

    # eta_seconds from metadata (runners may store it there).
    metadata = run.get("metadata") or {}
    eta_seconds: int | None = metadata.get("eta_seconds")

    # log_tail: last 20 event messages from the embedded event log.
    events: list[dict] = run.get("events") or []
    log_tail: list[str] | None = None
    if events:
        log_tail = [
            e.get("message") or ""
            for e in events[-20:]
            if e.get("message")
        ] or None

    # metrics: phase, round counter, last_event_at from the manifest/events.
    metrics: dict | None = None
    phase = metadata.get("phase") or metadata.get("stage")
    round_num = metadata.get("round_num") or metadata.get("round")
    last_event_ts = events[-1].get("timestamp") if events else None
    if any(v is not None for v in (phase, round_num, last_event_ts)):
        metrics = {}
        if phase is not None:
            metrics["phase"] = str(phase)
        if round_num is not None:
            metrics["round_num"] = int(round_num)
        if last_event_ts is not None:
            metrics["last_event_at"] = str(last_event_ts)

    enriched["eta_seconds"] = eta_seconds
    enriched["log_tail"] = log_tail
    enriched["metrics"] = metrics
    return enriched


@runs_bp.route("/<run_id>", methods=["GET"])
def get_run(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error
    detail = RunDetail.model_validate(_build_run_detail(run))
    return json_success(detail.model_dump(mode="json"))


@runs_bp.route("/<run_id>/events", methods=["GET"])
def get_run_events(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error
    return json_success(run.get("events", []))


@runs_bp.route("/<run_id>/stop", methods=["POST"])
def stop_run(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error

    if run.get("run_type") != "simulation_run":
        return json_error("Stop is only supported for simulation_run in this version", status=409)

    simulation_id = run.get("linked_ids", {}).get("simulation_id")
    if not simulation_id:
        return json_error("Run is missing simulation_id linkage", status=409)

    try:
        run_state = SimulationRunner.stop_simulation(simulation_id)
        manager = SimulationManager()
        sim_state = manager.get_simulation(simulation_id)
        if sim_state:
            sim_state.status = SimulationStatus.STOPPED
            manager._save_simulation_state(sim_state)
        run_registry.update_run(
            run_id,
            status="stopped",
            progress=run_state.to_dict().get("progress_percent", 0),
            message="Simulation stopped",
            artifacts=_simulation_artifacts(simulation_id),
            resume_capability={"available": True, "action": "restart", "label": "Restart run"},
        )
        return json_success(run_registry.get_run(run_id))
    except Exception as exc:
        return json_error(str(exc), status=400)


@runs_bp.route("/<run_id>/cancel", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to cancel run")
def cancel_run(run_id: str):
    """POST /api/runs/<run_id>/cancel — Cooperative Cancellation.

    Setzt das Cancel-Flag im in-process Cancel-Store. Der laufende Worker
    (SimulationRunner / ReportAgent) prüft das Flag zwischen Stage-Boundaries
    und bricht sauber ab (letzter LLM-Call läuft fertig, dann Teilreport).

    Antwort: 202 Accepted (asynchron — der Abbruch erfolgt kooperativ).

    Fehler:
    - 404 wenn run_id unbekannt
    - 400 wenn Run nicht im Status ``processing`` ist
    """
    run, error = _get_run_or_404(run_id)
    if error:
        return error

    current_status = run.get("status", "")
    if current_status != "processing":
        return json_error(
            f"Run is not in 'processing' state (current: {current_status!r}). "
            "Cancel is only valid for active runs.",
            status=400,
            code="run_not_active",
        )

    # linked_ids kann ``None`` sein (nicht nur fehlend) — ``or {}`` schützt
    # vor AttributeError, wenn der Key explizit None ist (Gemini-Finding).
    simulation_id = (run.get("linked_ids") or {}).get("simulation_id")
    if not simulation_id:
        return json_error("Run is missing simulation_id linkage", status=409)

    _request_cancel(run_id)

    # RunRegistry ist Singleton — Instanz pro Call holen (Gemini-Finding).
    RunRegistry().update_run(
        run_id,
        message="Cancel requested — finishing current stage before stopping",
    )

    logger.info(
        "cancel_run: cancel flag set for run_id=%s simulation_id=%s",
        run_id,
        simulation_id,
    )

    from flask import make_response, jsonify
    body = jsonify({"success": True, "status": "cancel_requested", "run_id": run_id})
    return make_response(body, 202)


def _restart_graph_build(run: dict):
    project_id = _linked_or_entity_id(run, "project_id", "project_id")
    project = ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(f"Project does not exist: {project_id}")

    text = ProjectManager.get_extracted_text(project_id)
    if not text:
        raise ValueError("Extracted text not found")
    ontology = project.ontology
    if not ontology:
        raise ValueError("Ontology definition not found")

    container = get_container()
    if container.neo4j_storage is None:
        raise ValueError("GraphStorage not initialized")

    graph_name = project.name or "Agora Graph"
    chunk_size = project.chunk_size or Config.DEFAULT_CHUNK_SIZE
    chunk_overlap = project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP

    new_run = run_registry.create_run(
        run_type="graph_build",
        entity_id=project_id,
        parent_run_id=run["run_id"],
        status="pending",
        progress=0,
        message="Graph build restart queued",
        linked_ids={"project_id": project_id},
        artifacts=ArtifactLocator.existing_paths({"project_dir": ProjectManager._get_project_dir(project_id)}),
        resume_capability={"available": True, "action": "restart", "label": "Restart graph build"},
        metadata={"graph_name": graph_name},
    )
    task_manager = TaskManager()
    task_id = task_manager.create_task(
        f"Build graph: {graph_name}",
        metadata={"project_id": project_id, "run_id": new_run["run_id"]},
    )
    project.status = ProjectStatus.GRAPH_BUILDING
    project.graph_build_task_id = task_id
    ProjectManager.save_project(project)

    def build_task():
        try:
            task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Initializing graph build service...")
            builder = container.graph_builder()
            task_manager.update_task(task_id, message="Chunking text...", progress=5)
            from ..services.text_processor import TextProcessor
            chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
            total_chunks = len(chunks)
            task_manager.update_task(task_id, message="Creating graph...", progress=10)
            graph_id = builder.create_graph(name=graph_name)
            project.graph_id = graph_id
            ProjectManager.save_project(project)
            run_registry.update_run(new_run["run_id"], linked_ids={"graph_id": graph_id}, entity_id=graph_id)
            task_manager.update_task(task_id, message="Setting ontology definition...", progress=15)
            builder.set_ontology(graph_id, ontology)

            def add_progress_callback(msg, progress_ratio):
                progress = 15 + int(progress_ratio * 40)
                task_manager.update_task(task_id, message=msg, progress=progress)

            episodes = builder.add_text_batches(graph_id, chunks, batch_size=3, progress_callback=add_progress_callback)
            task_manager.update_task(task_id, message="Retrieving graph data...", progress=95)
            graph_data = builder.get_graph_data(graph_id)
            project.status = ProjectStatus.GRAPH_COMPLETED
            ProjectManager.save_project(project)
            task_manager.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                message="Graph build completed",
                progress=100,
                result={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "node_count": graph_data.get("node_count", 0),
                    "edge_count": graph_data.get("edge_count", 0),
                    "chunk_count": total_chunks,
                    "episode_count": len(episodes),
                },
            )
            run_registry.update_run(
                new_run["run_id"],
                status="completed",
                progress=100,
                message="Graph build completed",
                artifacts=ArtifactLocator.existing_paths({"project_dir": ProjectManager._get_project_dir(project_id)}),
            )
        except Exception as exc:
            project.status = ProjectStatus.FAILED
            project.error = str(exc)
            ProjectManager.save_project(project)
            task_manager.update_task(
                task_id,
                status=TaskStatus.FAILED,
                message=f"Build failed: {exc}",
                error=traceback.format_exc(),
            )
            run_registry.update_run(new_run["run_id"], status="failed", message=str(exc), error=str(exc))

    threading.Thread(target=build_task, daemon=True).start()
    return {"run_id": new_run["run_id"], "task_id": task_id, "status": "processing"}


def _restart_simulation_prepare(run: dict):
    simulation_id = _linked_or_entity_id(run, "simulation_id", "simulation_id")
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    project = ProjectManager.get_project(state.project_id)
    if not project:
        raise ValueError(f"Project does not exist: {state.project_id}")

    simulation_requirement = project.simulation_requirement or ""
    document_text = ProjectManager.get_extracted_text(state.project_id) or ""
    storage = current_app.extensions.get("neo4j_storage")
    if not storage:
        raise ValueError("GraphStorage not initialized")

    config = manager.get_simulation_config(simulation_id) or {}
    new_run = run_registry.create_run(
        run_type="simulation_prepare",
        entity_id=simulation_id,
        parent_run_id=run["run_id"],
        status="pending",
        progress=0,
        message="Simulation preparation restart queued",
        linked_ids={"simulation_id": simulation_id, "project_id": state.project_id},
        artifacts=_simulation_artifacts(simulation_id),
        resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
        branch_label=state.branch_name,
        metadata={"graph_id": state.graph_id, "branch_name": state.branch_name},
    )
    task_manager = TaskManager()
    task_id = task_manager.create_task(
        "simulation_prepare",
        metadata={"simulation_id": simulation_id, "project_id": state.project_id, "run_id": new_run["run_id"]},
    )
    state.status = SimulationStatus.PREPARING
    manager._save_simulation_state(state)

    def run_prepare():
        try:
            task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=0, message="Start preparing simulation environment...")

            def progress_callback(stage, progress, message, **kwargs):
                stage_weights = {
                    "reading": (0, 20),
                    "generating_profiles": (20, 70),
                    "generating_config": (70, 90),
                    "copying_scripts": (90, 100),
                }
                start, end = stage_weights.get(stage, (0, 100))
                current_progress = int(start + (end - start) * progress / 100)
                task_manager.update_task(task_id, progress=current_progress, message=f"[{stage}] {message}")

            # Sub-Slice 20a: quota_plan aus persistierter Run-Config wieder
            # aufnehmen, damit Restart denselben Soll-Plan nutzt wie der
            # ursprüngliche Prepare-Run. Inkonsistenter Plan im persisted
            # Config-Snapshot würde im Service-Layer als ValidationError
            # propagieren und den Restart als FAILED markieren — das ist
            # gewollt (kein silent-Fallback auf "ohne Plan").
            from ..api.simulation_prepare import _parse_quota_plan
            quota_plan = _parse_quota_plan(config or {})

            result_state = manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                defined_entity_types=None,
                use_llm_for_profiles=True,
                progress_callback=progress_callback,
                parallel_profile_count=None,
                storage=storage,
                llm_model=config.get("llm_model"),
                language=config.get("language"),
                max_agents=config.get("max_agents"),
                quota_plan=quota_plan,
            )
            task_manager.complete_task(task_id, result=result_state.to_simple_dict())
            run_registry.update_run(
                new_run["run_id"],
                status="completed",
                progress=100,
                message="Simulation preparation completed",
                artifacts=_simulation_artifacts(simulation_id),
                resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
            )
        except Exception as exc:
            task_manager.fail_task(task_id, str(exc))
            run_registry.update_run(new_run["run_id"], status="failed", message=str(exc), error=str(exc))

    threading.Thread(target=run_prepare, daemon=True).start()
    return {"run_id": new_run["run_id"], "task_id": task_id, "status": "processing"}


def _resume_or_restart_simulation_run(run: dict):
    simulation_id = _linked_or_entity_id(run, "simulation_id", "simulation_id")
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    existing_run_state = SimulationRunner.get_run_state(simulation_id)
    if existing_run_state and existing_run_state.runner_status == RunnerStatus.PAUSED:
        from ..services.simulation_ipc import set_pause_state
        set_pause_state(ArtifactLocator.simulation_dir(simulation_id), False)
        run_registry.update_run(
            run["run_id"],
            status="processing",
            message="Simulation resumed",
            artifacts=_simulation_artifacts(simulation_id),
            resume_capability={"available": True, "action": "resume", "label": "Resume run"},
        )
        return {"run_id": run["run_id"], "status": "processing", "message": "Simulation resumed"}

    new_run_state = SimulationRunner.start_simulation(simulation_id=simulation_id, platform="parallel")
    state.status = SimulationStatus.RUNNING
    manager._save_simulation_state(state)
    new_run = run_registry.create_run(
        run_type="simulation_run",
        entity_id=simulation_id,
        parent_run_id=run["run_id"],
        status="processing",
        progress=0,
        message="Simulation restarted",
        linked_ids={"simulation_id": simulation_id, "project_id": state.project_id},
        artifacts=_simulation_artifacts(simulation_id),
        resume_capability={"available": True, "action": "resume", "label": "Resume run"},
        branch_label=state.branch_name,
        metadata={"graph_id": state.graph_id, "branch_name": state.branch_name},
    )
    return {"run_id": new_run["run_id"], "status": new_run_state.runner_status.value, "message": "Simulation restarted"}


def _resume_report_generate(run: dict):
    report_id = run.get("linked_ids", {}).get("report_id") or run.get("entity_id")
    simulation_id = run.get("linked_ids", {}).get("simulation_id")
    if not simulation_id:
        raise ValueError("Run is missing simulation_id linkage")

    # Recover the model override that was active when the run was originally started.
    # The original /api/report/generate call stores llm_model_override in the run
    # metadata; we honour it on resume so the same model is used throughout.
    llm_model_override = (run.get("metadata") or {}).get("llm_model") or None
    # Wenn der originale Request ein UI-Profile-Token war (`profile:<id>`),
    # expandieren wir es jetzt — sonst landet der Pseudo-Modellname als Modell
    # beim LLM (Ollama 404, kein Entity-Output).
    if isinstance(llm_model_override, str) and llm_model_override.startswith("profile:"):
        from ..utils.llm_profile_resolver import expand_profile_in_data
        _expand_buf = {"llm_model": llm_model_override}
        expand_profile_in_data(_expand_buf)
        llm_model_override = (_expand_buf.get("llm_model") or "").strip() or None

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")
    project = ProjectManager.get_project(state.project_id)
    if not project:
        raise ValueError(f"Project does not exist: {state.project_id}")
    graph_id = state.graph_id or project.graph_id
    if not graph_id:
        raise ValueError("Missing graph ID")
    storage = current_app.extensions.get("neo4j_storage")
    if not storage:
        raise ValueError("GraphStorage not initialized")
    # Resume-Pfad teilt denselben LLMClient zwischen Agent und GraphTools
    # — api_key bleibt redacted (Secrets nicht persistiert), aber das Modell
    # kommt sauber aus der Run-Metadata durch. Vorher hat GraphTools beim
    # Lazy-Init Config-Default genommen.
    # Smoke-Fix Slice 04: LLMClient(model=...) ohne api_key wirft wenn Config.LLM_API_KEY
    # fehlt (z. B. in Test-Umgebung). Fallback auf None → GraphTools/ReportAgent nutzen
    # dann ihren eigenen Default-Client mit Config-Werten.
    if llm_model_override:
        try:
            shared_llm_client: Optional[LLMClient] = LLMClient(model=llm_model_override)
        except ValueError as exc:
            # Kein API-Key konfiguriert → kein sinnvoller Resume-Pfad möglich.
            # Synchron mit 422 antworten statt still None zu setzen und im
            # Worker-Thread beim ersten LLM-Call zu sterben (Copilot PR #466).
            logger.warning(
                "LLMClient für Resume-Report nicht verfügbar — synchrones 422: %s",
                exc,
            )
            return json_error(
                f"LLM-Provider nicht verfügbar: {exc}. "
                "Konfiguriere einen API-Key, bevor der Report fortgesetzt wird.",
                status=422,
                code="llm_client_unavailable",
            )
    else:
        shared_llm_client = None
    graph_tools = GraphToolsService(storage=storage, llm_client=shared_llm_client)

    task_manager = TaskManager()
    task_id = task_manager.create_task(
        "report_generate",
        metadata={"simulation_id": simulation_id, "graph_id": graph_id, "report_id": report_id, "run_id": run["run_id"]},
    )

    def run_generate():
        try:
            task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=0, message="Initializing Report Agent...")
            agent = ReportAgent(
                graph_id=graph_id,
                simulation_id=simulation_id,
                simulation_requirement=project.simulation_requirement or "",
                graph_tools=graph_tools,
                llm_client=shared_llm_client,
                model_name=llm_model_override,
            )

            def progress_callback(stage, progress, message):
                task_manager.update_task(task_id, progress=progress, message=f"[{stage}] {message}")

            report = agent.generate_report(progress_callback=progress_callback, report_id=report_id)
            ReportManager.save_report(report)
            if report.status == ReportStatus.COMPLETED:
                run_registry.update_run(
                    run["run_id"],
                    status="completed",
                    progress=100,
                    message="Report generated",
                    artifacts=ArtifactLocator.existing_paths({
                        "report": ArtifactLocator.report_artifacts(report_id),
                        "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
                    }),
                    resume_capability={"available": False, "action": None, "label": None},
                )
                task_manager.complete_task(task_id, result={"report_id": report_id, "simulation_id": simulation_id})
            else:
                run_registry.update_run(run["run_id"], status="failed", message=report.error or "Report generation failed", error=report.error)
                task_manager.fail_task(task_id, report.error or "Report generation failed")
        except Exception as exc:
            run_registry.update_run(run["run_id"], status="failed", message=str(exc), error=str(exc))
            task_manager.fail_task(task_id, str(exc))

    run_registry.update_run(run["run_id"], status="processing", progress=0, message="Report generation resumed")
    threading.Thread(target=run_generate, daemon=True).start()
    return {"run_id": run["run_id"], "task_id": task_id, "status": "processing"}


@runs_bp.route("/<run_id>/resume", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to resume run")
def resume_run(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error

    run_type = run.get("run_type")
    if run_type == "graph_build":
        data = _restart_graph_build(run)
    elif run_type == "simulation_prepare":
        data = _restart_simulation_prepare(run)
    elif run_type == "simulation_run":
        data = _resume_or_restart_simulation_run(run)
    elif run_type == "report_generate":
        # _resume_report_generate kann bei fehlendem LLM-Key direkt eine
        # Fehler-Response (Tuple) zurückgeben — in dem Fall weiterleiten.
        result = _resume_report_generate(run)
        if not isinstance(result, dict):
            return result
        return json_success(result)
    else:
        return json_error(f"Unsupported run type: {run_type}", status=409)
    return json_success(data)
