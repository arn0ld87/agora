"""
Run registry API.
"""

from __future__ import annotations

import threading
import traceback

from flask import current_app, request

from . import runs_bp
from ..config import Config
from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager, TaskStatus
from ..services.graph_builder import GraphBuilderService
from ..services.graph_tools import GraphToolsService
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import RunnerStatus, SimulationRunner
from ..utils.api_responses import handle_api_errors, json_error, json_success
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


@runs_bp.route("", methods=["GET"])
@handle_api_errors(logger=logger, log_prefix="Failed to list runs")
def list_runs():
    runs = run_registry.list_runs(
        project_id=request.args.get("project"),
        run_type=request.args.get("run_type"),
        status=request.args.get("status"),
        branch=request.args.get("branch"),
        limit=request.args.get("limit", 200, type=int),
    )
    return json_success(runs, count=len(runs))


@runs_bp.route("/<run_id>", methods=["GET"])
def get_run(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error
    return json_success(run)


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


def _restart_graph_build(run: dict):
    project_id = run.get("linked_ids", {}).get("project_id") or run.get("entity_id")
    project = ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(f"Project does not exist: {project_id}")

    text = ProjectManager.get_extracted_text(project_id)
    if not text:
        raise ValueError("Extracted text not found")
    ontology = project.ontology
    if not ontology:
        raise ValueError("Ontology definition not found")

    storage = current_app.extensions.get("neo4j_storage")
    if not storage:
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
            builder = GraphBuilderService(storage=storage)
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
    simulation_id = run.get("linked_ids", {}).get("simulation_id") or run.get("entity_id")
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

            result_state = manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                defined_entity_types=None,
                use_llm_for_profiles=True,
                progress_callback=progress_callback,
                parallel_profile_count=5,
                storage=storage,
                llm_model=config.get("llm_model"),
                language=config.get("language"),
                max_agents=config.get("max_agents"),
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
    simulation_id = run.get("linked_ids", {}).get("simulation_id") or run.get("entity_id")
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
    graph_tools = GraphToolsService(storage=storage)

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
        data = _resume_report_generate(run)
    else:
        return json_error(f"Unsupported run type: {run_type}", status=409)
    return json_success(data)
