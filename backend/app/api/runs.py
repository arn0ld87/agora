"""
Run registry API.
"""

from __future__ import annotations

import os
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
from ..services.llm_routing_seed import (
    build_runtime_llm_config,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.report_generation import (
    finish_cancelled_run,
    finish_completed_run,
    was_run_cancelled,
)
from ..services.run_lifecycle import RunLifecycle
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import RunnerStatus, SimulationRunner
from ..services.stage_model_router import StageModelRouter
from ..services.sim.cancel_flag import request_cancel as _request_cancel
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.llm_client import LLMClient
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from ..utils.validation import validate_run_id, validate_simulation_id

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


def _get_run_by_run_or_simulation_id(identifier: str):
    """Löst ``run_``- *oder* ``sim_``-IDs zu einem Run auf.

    Schritt 3 im Frontend kennt nur die ``simulation_id`` und schickt sie an
    ``POST /api/runs/<id>/cancel``. ``run_id`` und ``simulation_id`` haben
    aber unterschiedliche Formate (``run_``/``sim_`` + 12 Hex) und werden
    unabhängig voneinander vergeben — kein ``create_run``-Aufruf im Repository
    setzt ``run_id`` explizit, alle nutzen den Default in
    ``RunRegistry.create_run``. Die einzige Verknüpfung ist
    ``linked_ids.simulation_id``. Ohne diese Auflösung scheiterte jeder
    Abbrechen-Klick an ``validate_run_id`` mit HTTP 400, ohne irgendetwas
    abzubrechen.

    Der Auflösungspfad ist derselbe wie in
    ``simulation_run.py::stop_simulation`` — kein zweites Muster.
    """
    if validate_simulation_id(identifier):
        run = run_registry.get_latest_by_linked_id(
            "simulation_id", identifier, run_type="simulation_run"
        )
        if not run:
            return None, json_error(
                f"Run does not exist for simulation: {identifier}", status=404
            )
        return run, None
    return _get_run_or_404(identifier)


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
    except Exception as exc:  # pragma: no cover - defensive read path  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.debug("Could not load simulation %s for run summary: %s", simulation_id, exc)

    store = current_app.extensions.get("artifact_store") if current_app else None
    if store is not None:
        try:
            if store.exists(simulation_id, "reddit_profiles"):
                profiles = store.read_json(simulation_id, "reddit_profiles", default=[]) or []
                if isinstance(profiles, list):
                    entry["persona_count"] = len(profiles)
        except Exception as exc:  # pragma: no cover - defensive read path  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.debug("Could not read reddit_profiles for %s: %s", simulation_id, exc)

    sim_cache[simulation_id] = entry
    return entry


def _resolve_project(project_id: str, project_cache: dict):
    if project_id in project_cache:
        return project_cache[project_id]
    try:
        project = ProjectManager.get_project(project_id)
    except Exception as exc:  # pragma: no cover - defensive read path  # noqa: BLE001 — exception is logged; swallowed intentionally
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

    # Budget & Verbrauch (Issue #764): Budget-Status nur wenn ein Budget
    # gesetzt ist; Verbrauch live aggregiert (Abschluss-Snapshot bevorzugt).
    # Beides bleibt bei Alt-Runs ohne Daten ehrlich None (= unknown im UI).
    try:
        from ..services.run_budget import get_run_budget_status
        from ..services.run_usage_ledger import (
            aggregate_usage,
            load_call_events_cached,
            load_usage_summary,
        )

        budget_status = get_run_budget_status(run["run_id"])
        if budget_status is not None:
            enriched["budget"] = budget_status.model_dump(mode="json")

        usage = load_usage_summary(run["run_id"])
        if usage is None:
            events = load_call_events_cached(run["run_id"])
            if events:
                usage = aggregate_usage(
                    run["run_id"],
                    events=events,
                    started_at=run.get("started_at"),
                    ended_at=run.get("completed_at"),
                )
                # Snapshot-Persist läuft nicht hier: RunRegistry.update_run
                # triggert persist_usage_summary am Lifecycle-Übergang
                # nicht-terminal → terminal (Issue #764 / Codex P2). Ein
                # zweiter Persist hier würde doppelt schreiben und den
                # idempotenten Snapshot-Pfad in run_usage_ledger unnötig
                # aufheizen.
        if usage is not None:
            enriched["usage"] = usage.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — Anreicherung darf den Read nicht brechen
        logger.warning("budget/usage enrichment failed for run %s", run.get("run_id"), exc_info=True)
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


@runs_bp.route("/<run_id>/usage", methods=["GET"])
def get_run_usage(run_id: str):
    """GET /api/runs/<run_id>/usage — Verbrauchsaufstellung (Issue #764).

    Liefert den RunUsage-Contract: gesamt + pro Stage/Provider/Modell.
    Runs ohne Messdaten antworten mit ehrlichem measurement_status=unknown.
    """
    from ..services.run_usage_ledger import (
        aggregate_usage,
        load_call_events_cached,
        load_usage_summary,
    )

    run, error = _get_run_or_404(run_id)
    if error:
        return error

    usage = load_usage_summary(run_id)
    if usage is None:
        usage = aggregate_usage(
            run_id,
            events=load_call_events_cached(run_id),
            started_at=run.get("started_at"),
            ended_at=run.get("completed_at"),
        )
    return json_success(usage.model_dump(mode="json"))


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
    except Exception as exc:  # noqa: BLE001 — exception returned as JSON error response
        return json_error(str(exc), status=400)


@runs_bp.route("/<run_id>/cancel", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to cancel run")
def cancel_run(run_id: str):
    """POST /api/runs/<run_id>/cancel — Cooperative Cancellation.

    Setzt das Cancel-Flag im in-process Cancel-Store. Konsumenten (#1082):
    Für ``report_generation`` prüft der ReportAgent das Flag zwischen
    Stage-Boundaries und bricht sauber ab (letzter LLM-Call läuft fertig,
    dann Teilreport). Für ``simulation_run`` konsumiert der Monitor-Thread
    das Flag im Elternprozess und beendet den OASIS-Subprozess (SIGTERM,
    Grace-Period, dann SIGKILL); der Run endet als ``stopped`` mit
    ``termination_reason="user_cancel"``, Teilergebnisse bleiben erhalten.

    ``run_id`` akzeptiert auch eine ``simulation_id`` — Schritt 3 im Frontend
    kennt nur diese. Die Auflösung läuft über ``linked_ids.simulation_id``,
    siehe :func:`_get_run_by_run_or_simulation_id`.

    Antwort: 202 Accepted (asynchron — der Abbruch erfolgt kooperativ). Das
    Feld ``run_id`` im Body trägt immer die aufgelöste ``run_``-ID, nie die
    übergebene ``simulation_id``.

    Fehler:
    - 404 wenn run_id/simulation_id unbekannt
    - 400 wenn Run nicht im Status ``processing`` ist
    """
    run, error = _get_run_by_run_or_simulation_id(run_id)
    if error:
        return error

    resolved_run_id = run.get("run_id") or run_id

    current_status = run.get("status", "")
    if current_status == "pending":
        # Issue #1176: Ein Run in ``pending`` hat noch keinen Subprozess, den
        # ein Cancel-Flag erreichen könnte — kooperativer Abbruch läuft ins
        # Leere. Vor diesem Slice lehnte die Route ihn deshalb ab, und die
        # betroffenen Runs blieben dauerhaft in der Liste stehen: nicht
        # abbrechbar, weil nicht aktiv, und nicht aktiv werdend, weil der
        # Start nie durchlief. Sie werden direkt beendet.
        RunRegistry().update_run(
            resolved_run_id,
            status="failed",
            message="Vom Nutzer abgebrochen, bevor die Simulation gestartet war",
        )
        from flask import jsonify, make_response

        return make_response(
            jsonify(
                {"success": True, "status": "cancelled", "run_id": resolved_run_id}
            ),
            200,
        )

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

    _request_cancel(resolved_run_id)

    # RunRegistry ist Singleton — Instanz pro Call holen (Gemini-Finding).
    RunRegistry().update_run(
        resolved_run_id,
        message="Cancel requested — finishing current stage before stopping",
    )

    logger.info(
        "cancel_run: cancel flag set for run_id=%s simulation_id=%s",
        resolved_run_id,
        simulation_id,
    )

    from flask import make_response, jsonify
    body = jsonify(
        {"success": True, "status": "cancel_requested", "run_id": resolved_run_id}
    )
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

    # Issue #1183: Anlage-Fenster hinter RunLifecycle — jeder Abbruch bis zum
    # Thread-Start markiert den Run als failed statt ihn pending zu verwaisen.
    with RunLifecycle.begin(
        run_registry,
        "graph_build",
        project_id,
        parent_run_id=run["run_id"],
        failure_message="Graph build restart failed: {exc_type}",
        progress=0,
        message="Graph build restart queued",
        linked_ids={"project_id": project_id},
        artifacts=ArtifactLocator.existing_paths({"project_dir": ProjectManager._get_project_dir(project_id)}),
        resume_capability={"available": True, "action": "restart", "label": "Restart graph build"},
        metadata={"graph_name": graph_name},
    ) as lifecycle:
        new_run = lifecycle.record
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            f"Build graph: {graph_name}",
            metadata={"project_id": project_id, "run_id": new_run["run_id"]},
        )
        lifecycle.attach_task(task_manager, task_id)
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
            except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
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
    # Issue #841/#844/#1183: Anlage-Fenster hinter RunLifecycle — Markierung,
    # Task-Reihenfolge und strikte Persistenzsemantik liegen im Kontextmanager.
    with RunLifecycle.begin(
        run_registry,
        "simulation_prepare",
        simulation_id,
        parent_run_id=run["run_id"],
        failure_message="Simulation preparation restart failed: {exc_type}",
        progress=0,
        message="Simulation preparation restart queued",
        linked_ids={"simulation_id": simulation_id, "project_id": state.project_id},
        artifacts=_simulation_artifacts(simulation_id),
        resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
        branch_label=state.branch_name,
        metadata={"graph_id": state.graph_id, "branch_name": state.branch_name},
    ) as lifecycle:
        new_run = lifecycle.record
        run_id = new_run["run_id"]

        # Restart hat keinen Request-Payload — llm_runtime=None, damit das
        # Resolving ausschließlich über die persistierte Route bzw. den in der
        # Settings-DB hinterlegten Store-Key läuft und nicht still auf
        # Config.LLM_API_KEY/LLM_BASE_URL aus der lokalen .env zurückfällt (#798,
        # Opus-Review-Folgebefund zu #778). Exakt derselbe Resolver-Pfad wie
        # simulation_prepare.py::prepare_simulation.
        from ..utils.endpoints import LOCAL_NO_AUTH_API_KEY, is_local_endpoint

        seed_run_stage_routing(
            run_id,
            "persona_generation",
            llm_model_override=config.get("llm_model"),
            llm_runtime=None,
        )
        route_router = StageModelRouter(run_id)
        resolved_route = route_router.resolve("persona_generation")
        route_router.lock_stage("persona_generation", resolved_route)
        resolved_api_key = resolve_route_api_key(resolved_route, None)

        if resolved_api_key is None and not is_local_endpoint(resolved_route.base_url_sanitized):
            guard_message = (
                f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
                f"für Provider '{resolved_route.provider_id}'. "
                "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                "oder im Sitzungsfeld eingeben."
            )
            guard_error = ValueError(guard_message)
            # RunLifecycle liest die failed-Meldung über dieses Attribut (#841).
            guard_error.run_failure_message = guard_message  # type: ignore[attr-defined]
            raise guard_error

        if resolved_api_key is None and is_local_endpoint(resolved_route.base_url_sanitized):
            resolved_api_key = LOCAL_NO_AUTH_API_KEY

        effective_llm_runtime = build_runtime_llm_config(resolved_route, resolved_api_key)

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "simulation_prepare",
            metadata={"simulation_id": simulation_id, "project_id": state.project_id, "run_id": new_run["run_id"]},
        )
        lifecycle.attach_task(task_manager, task_id)
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
                    llm_runtime=effective_llm_runtime,
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
            except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
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

    # Issue #1183: Der Run-Record entsteht VOR dem Prozessstart im
    # Lifecycle-Fenster — schlägt der Start fehl, existiert ein failed-Record
    # statt gar keinem (vorher: create_run erst nach start_simulation).
    with RunLifecycle.begin(
        run_registry,
        "simulation_run",
        simulation_id,
        parent_run_id=run["run_id"],
        failure_message="Simulation restart failed: {exc_type}",
        progress=0,
        message="Simulation restart queued",
        linked_ids={"simulation_id": simulation_id, "project_id": state.project_id},
        artifacts=_simulation_artifacts(simulation_id),
        resume_capability={"available": True, "action": "resume", "label": "Resume run"},
        branch_label=state.branch_name,
        metadata={"graph_id": state.graph_id, "branch_name": state.branch_name},
    ) as lifecycle:
        new_run = lifecycle.record
        new_run_state = SimulationRunner.start_simulation(simulation_id=simulation_id, platform="parallel")
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        lifecycle.succeed(status="processing", message="Simulation restarted")
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
    # Budget-Enforcement + Routing-SSoT (#984): Der Resume-Client entsteht aus
    # der beim Original-Start gelockten Stage-Route MIT run_id — das frühere
    # LLMClient(model=...) ohne run_id lieferte keinen Budget-Enforcer, ein
    # fortgesetzter Report lief ohne jede Budgetdurchsetzung.
    # StageModelRouter.resolve() gibt den gelockten Snapshot zurück; nur für
    # Alt-Runs ohne Snapshot entscheidet der kanonische Resolver. Keine zweite
    # Client-Bauweise neben der Route (SSoT aus #817).
    from ..services.ai_route_resolver import NoAiRouteCandidateError
    from ..services.secret_resolver import SecretResolver

    try:
        route_router = StageModelRouter(run["run_id"])
        resolved_route = route_router.resolve("report_generation")
        shared_llm_client: Optional[LLMClient] = LLMClient.from_route(
            resolved_route,
            secret_resolver=SecretResolver(),
            run_id=run["run_id"],
        )
    except (ValueError, NoAiRouteCandidateError) as exc:
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
    graph_tools = GraphToolsService(storage=storage, llm_client=shared_llm_client)

    task_manager = TaskManager()
    task_id = task_manager.create_task(
        "report_generate",
        metadata={"simulation_id": simulation_id, "graph_id": graph_id, "report_id": report_id, "run_id": run["run_id"]},
    )

    from ..services.run_budget import BudgetExceededError, mark_budget_abort

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

            # Issue #1243: auch der Resume-Pfad muss abbrechbar sein — ohne
            # cancel_run_id liest generate_report das Flag nie.
            report = agent.generate_report(
                progress_callback=progress_callback,
                report_id=report_id,
                cancel_run_id=run["run_id"],
            )
            ReportManager.save_report(report)
            if was_run_cancelled(run["run_id"]):
                # Teilreport nach Nutzerabbruch traegt status=COMPLETED; ohne
                # diesen Zweig waere er von einem vollstaendigen Lauf nicht zu
                # unterscheiden.
                # Reihenfolge bindend (#978): complete_task spiegelt sich per
                # sync_task auf den Run zurueck und wuerde "stopped" wieder
                # ueberschreiben. Der Run-Update laeuft zuletzt.
                task_manager.complete_task(
                    task_id,
                    result={
                        "report_id": report_id,
                        "simulation_id": simulation_id,
                        "cancelled": True,
                    },
                )
                finish_cancelled_run(
                    run["run_id"], report_id=report_id, simulation_id=simulation_id
                )
            elif report.status == ReportStatus.COMPLETED:
                finish_completed_run(
                    run["run_id"], report_id=report_id, simulation_id=simulation_id
                )
                task_manager.complete_task(task_id, result={"report_id": report_id, "simulation_id": simulation_id})
            else:
                run_registry.update_run(run["run_id"], status="failed", message=report.error or "Report generation failed", error=report.error)
                task_manager.fail_task(task_id, report.error or "Report generation failed")
        except BudgetExceededError as exc:
            # Budgetabbruch (#984): Teilresultate bleiben erhalten, Status
            # "stopped" + termination_reason statt technischem "failed".
            # Reihenfolge bindend (#978, gleiche Falle wie #841): fail_task()
            # zuerst — sync_task setzt generisch "failed" —, der detaillierte
            # mark_budget_abort() zuletzt (setzt stopped + termination_reason).
            logger.warning(
                "Resume report budget-aborted (run_id=%s, report_id=%s): %s",
                run["run_id"], report_id, exc,
            )
            task_manager.fail_task(task_id, str(exc))
            mark_budget_abort(run["run_id"], exc.dimension, exc.observed, exc.threshold)
        except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
            run_registry.update_run(run["run_id"], status="failed", message=str(exc), error=str(exc))
            task_manager.fail_task(task_id, str(exc))

    run_registry.update_run(run["run_id"], status="processing", progress=0, message="Report generation resumed")
    threading.Thread(target=run_generate, daemon=True).start()
    return {"run_id": run["run_id"], "task_id": task_id, "status": "processing"}


@runs_bp.route("/<run_id>/replay", methods=["POST"])
@handle_api_errors(logger=logger, log_prefix="Failed to replay run")
def replay_run(run_id: str):
    """POST /api/runs/<run_id>/replay — Neuen Run aus Manifest starten (Issue #763).

    Liest das manifest.json des Original-Runs und erzeugt einen neuen Run
    mit identischer Konfiguration. Optionale Overrides erlauben Varianten-
    Replay mit anderem Seed-Dokument, Seed-Wert oder AI-Modell.

    Antwort: 202 { run_id, status: "pending" }
    """
    run, error = _get_run_or_404(run_id)
    if error:
        return error

    manifest_path = os.path.join(ArtifactLocator.run_dir(run_id), "manifest.json")
    if not os.path.exists(manifest_path):
        return json_error(
            f"Run {run_id} has no manifest — replay requires a manifest",
            status=400,
            code="no_manifest",
        )

    # Overrides aus dem Request-Body parsen
    overrides = None
    if request.is_json and request.get_json(silent=True):
        body = request.get_json(silent=True) or {}
        from ..contracts.run_manifest_contract import ReplayOverrides
        try:
            overrides = ReplayOverrides(**body) if body else None
        except ValidationError as exc:
            return json_error(exc.errors(), status=400)

    # Neuen Run anlegen
    new_run = run_registry.create_run(
        run_type=run.get("run_type", "simulation_run"),
        entity_id=run.get("entity_id", ""),
        replayed_from_run_id=run_id,
        status="pending",
        message=f"Replay of {run_id}",
        linked_ids=dict(run.get("linked_ids", {}) or {}),
        metadata=dict(run.get("metadata", {}) or {}),
    )

    # Overrides im neuen Run vermerken
    if overrides is not None:
        override_meta = overrides.model_dump(exclude_none=True)
        if override_meta:
            current_meta = dict(new_run.get("metadata", {}) or {})
            current_meta["replay_overrides"] = override_meta
            run_registry.update_run(new_run["run_id"], metadata=current_meta)

    from flask import make_response, jsonify
    body = jsonify({"run_id": new_run["run_id"], "status": "pending"})
    return make_response(body, 202)


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
