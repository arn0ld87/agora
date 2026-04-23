"""
Report API Routes
Provides interfaces for simulation report generation, retrieval, and conversation
"""

import os
import threading
import uuid
from flask import request, send_file, current_app

from . import report_bp
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..services.graph_tools import GraphToolsService
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from ..utils.validation import validate_report_id, validate_simulation_id, validate_task_id
from ..utils.api_responses import handle_api_errors, json_success, json_error

logger = get_logger(__name__)
run_registry = RunRegistry()

# ============== Report Generation Interface ==============

@report_bp.route('/generate', methods=['POST'])
@handle_api_errors(log_prefix="Failed to start report generation task")
def generate_report():
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error("Please provide simulation_id", status=400)

    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    force_regenerate = data.get('force_regenerate', False)
    llm_model_override = (data.get('llm_model') or '').strip() or None
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

    if not force_regenerate:
        existing_report = ReportManager.get_report_by_simulation(simulation_id)
        if existing_report and existing_report.status == ReportStatus.COMPLETED:
            return json_success({
                "simulation_id": simulation_id,
                "report_id": existing_report.report_id,
                "status": "completed",
                "message": "Report already exists",
                "already_generated": True
            })

    project = ProjectManager.get_project(state.project_id)
    if not project:
        return json_error(f"Project does not exist: {state.project_id}", status=404)

    graph_id = state.graph_id or project.graph_id
    if not graph_id:
        return json_error("Missing graph ID, please ensure graph is built", status=400)

    simulation_requirement = project.simulation_requirement
    if not simulation_requirement:
        return json_error("Missing simulation requirement description", status=400)

    report_id = f"report_{uuid.uuid4().hex[:12]}"

    task_manager = TaskManager()
    run_record = run_registry.create_run(
        run_type="report_generate",
        entity_id=report_id,
        status="pending",
        progress=0,
        message="Report generation queued",
        linked_ids={
            "simulation_id": simulation_id,
            "report_id": report_id,
            "project_id": state.project_id,
        },
        artifacts=ArtifactLocator.existing_paths({
            "report": ArtifactLocator.report_artifacts(report_id),
            "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
        }),
        resume_capability={"available": True, "action": "resume", "label": "Continue report generation"},
        branch_label=state.branch_name,
        metadata={
            "graph_id": graph_id,
            "source_simulation_id": state.source_simulation_id,
            "root_simulation_id": state.root_simulation_id,
            "branch_name": state.branch_name,
            "branch_depth": state.branch_depth,
        },
    )
    task_id = task_manager.create_task(
        task_type="report_generate",
        metadata={"simulation_id": simulation_id, "graph_id": graph_id, "report_id": report_id, "run_id": run_record["run_id"]}
    )

    # Initialize graph_tools in Flask context BEFORE spawning thread
    # (current_app is not available inside background threads)
    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        return json_error("GraphStorage not initialized — check Neo4j connection", status=500)
    graph_tools = GraphToolsService(storage=storage)

    def run_generate():
        try:
            task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=0, message="Initializing Report Agent...")
            agent = ReportAgent(
                graph_id=graph_id,
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                graph_tools=graph_tools,
                model_name=llm_model_override,
            )
            def progress_callback(stage, progress, message):
                task_manager.update_task(task_id, progress=progress, message=f"[{stage}] {message}")
            report = agent.generate_report(progress_callback=progress_callback, report_id=report_id)
            ReportManager.save_report(report)
            if report.status == ReportStatus.COMPLETED:
                run_registry.update_run(
                    run_record["run_id"],
                    status="completed",
                    progress=100,
                    message="Report generated",
                    artifacts=ArtifactLocator.existing_paths({
                        "report": ArtifactLocator.report_artifacts(report_id),
                        "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
                    }),
                    resume_capability={"available": False, "action": None, "label": None},
                )
                task_manager.complete_task(task_id, result={"report_id": report.report_id, "simulation_id": simulation_id, "status": "completed"})
            else:
                run_registry.update_run(
                    run_record["run_id"],
                    status="failed",
                    message=report.error or "Report generation failed",
                    error=report.error or "Report generation failed",
                    artifacts=ArtifactLocator.existing_paths({
                        "report": ArtifactLocator.report_artifacts(report_id),
                        "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
                    }),
                    resume_capability={"available": True, "action": "resume", "label": "Continue report generation"},
                )
                task_manager.fail_task(task_id, report.error or "Report generation failed")
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            run_registry.update_run(
                run_record["run_id"],
                status="failed",
                message=str(e),
                error=str(e),
                artifacts=ArtifactLocator.existing_paths({
                    "report": ArtifactLocator.report_artifacts(report_id),
                    "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
                }),
            )
            task_manager.fail_task(task_id, str(e))

    thread = threading.Thread(target=run_generate, daemon=True)
    thread.start()

    return json_success({
        "simulation_id": simulation_id,
        "report_id": report_id,
        "task_id": task_id,
        "run_id": run_record["run_id"],
        "status": "generating",
        "message": "Report generation task started. Query progress via /api/report/generate/status",
        "already_generated": False
    })


@report_bp.route('/generate/status', methods=['POST'])
@handle_api_errors(log_prefix="Failed to query task status")
def get_generate_status():
    """
    Query report-generation progress.
    """
    data = request.get_json() or {}
    task_id = data.get('task_id')
    simulation_id = data.get('simulation_id')
    report_id = data.get('report_id')

    if task_id and not validate_task_id(task_id):
        return json_error("Invalid task_id format", status=400)
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)
    if report_id and not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)
    task_manager = TaskManager()

    # ── 0) Prefer persisted run-registry status for report-specific polls ──
    if report_id:
        run = run_registry.get_latest_by_linked_id("report_id", report_id, run_type="report_generate")
        if run:
            progress_state = ReportManager.get_progress(report_id) or {}
            report_obj = ReportManager.get_report(report_id)
            generated_sections = {}
            for section in ReportManager.get_generated_sections(report_id):
                generated_sections[section.get("section_index")] = {"content": section.get("content", "")}
            data = {
                "simulation_id": run.get("linked_ids", {}).get("simulation_id") or simulation_id,
                "report_id": report_id,
                "run_id": run.get("run_id"),
                "status": run.get("status"),
                "progress": run.get("progress", 0),
                "message": progress_state.get("message") or run.get("message", ""),
                "error": run.get("error"),
                "outline": report_obj.outline.to_dict() if report_obj and report_obj.outline else None,
                "sections": generated_sections,
                "current_section_index": len(progress_state.get("completed_sections") or []),
            }
            if run.get("status") in {"completed", "failed", "paused", "stopped", "processing", "pending"}:
                return json_success(data)

    # ── 1) Resolve task_id + simulation_id from report_id if needed ────
    if report_id and not task_id:
        existing_report = ReportManager.get_report(report_id)
        if existing_report:
            # Already persisted — use its definitive status.
            sim_id = existing_report.simulation_id or simulation_id
            if existing_report.status == ReportStatus.COMPLETED:
                return json_success({
                    "simulation_id": sim_id,
                    "report_id": report_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "Report generated",
                    "already_completed": True,
                })
            if existing_report.status == ReportStatus.FAILED:
                return json_success({
                    "simulation_id": sim_id,
                    "report_id": report_id,
                    "status": "failed",
                    "progress": 0,
                    "message": "Report generation failed",
                    "error": getattr(existing_report, "error", "") or "",
                })
            simulation_id = sim_id
        # Either way, try to find the live task by metadata.
        try:
            for t in task_manager.list_tasks(task_type="report_generate") or []:
                # list_tasks returns dicts, not Task objects.
                meta = (t.get("metadata") if isinstance(t, dict) else getattr(t, "metadata", {})) or {}
                if meta.get("report_id") == report_id:
                    task_id = t.get("task_id") if isinstance(t, dict) else getattr(t, "task_id", None)
                    if not simulation_id:
                        simulation_id = meta.get("simulation_id")
                    break
        except Exception as lookup_exc:
            logger.warning(f"report_id → task lookup failed: {lookup_exc}")

    # ── 2) If we have a task, that's authoritative ─────────────────────
    if task_id:
        task = task_manager.get_task(task_id)
        if task:
            payload = task.to_dict()
            if simulation_id and "simulation_id" not in payload:
                payload["simulation_id"] = simulation_id
            if report_id:
                payload["report_id"] = report_id
            return json_success(payload)
        # Task id was provided but stale (e.g. server restart) — fall through.
        logger.info(f"task_id {task_id} not found, falling back")

    # ── 3) Only simulation_id known — look up *any* completed report ───
    if simulation_id and not report_id:
        existing_report = ReportManager.get_report_by_simulation(simulation_id)
        if existing_report and existing_report.status == ReportStatus.COMPLETED:
            return json_success({
                "simulation_id": simulation_id,
                "report_id": existing_report.report_id,
                "status": "completed",
                "progress": 100,
                "message": "Report generated",
                "already_completed": True
            })

    # ── 4) Fallback — caller keeps polling, we acknowledge ─────────────
    if report_id or simulation_id:
        return json_success({
            "simulation_id": simulation_id,
            "report_id": report_id,
            "status": "generating",
            "progress": 0,
            "message": "Task handle unknown — waiting for report completion",
        })
    return json_error("Please provide task_id, simulation_id or report_id", status=400)


# ============== Report Retrieval Interface ==============

@report_bp.route('/<report_id>', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get report")
def get_report(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    report = ReportManager.get_report(report_id)
    if not report:
        return json_error(f"Report does not exist: {report_id}", status=404)
    return json_success(report.to_dict())


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get report")
def get_report_by_simulation(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    report = ReportManager.get_report_by_simulation(simulation_id)
    if not report:
        return json_error(f"No report available for this simulation: {simulation_id}", status=404, has_report=False)
    return json_success(report.to_dict())


@report_bp.route('/list', methods=['GET'])
@handle_api_errors(log_prefix="Failed to list reports")
def list_reports():
    simulation_id = request.args.get('simulation_id')
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)
    limit = request.args.get('limit', 50, type=int)
    reports = ReportManager.list_reports(simulation_id=simulation_id, limit=limit)
    return json_success([r.to_dict() for r in reports], count=len(reports))


@report_bp.route('/<report_id>/evidence', methods=['GET'])
@handle_api_errors
def get_report_evidence(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)
    evidence_map = ReportManager.get_evidence_map(report_id)
    if not evidence_map:
        return json_error(f"No evidence map available for report: {report_id}", status=404)
    return json_success(evidence_map)


@report_bp.route('/<report_id>/evidence/<int:section_index>', methods=['GET'])
@handle_api_errors
def get_report_evidence_section(report_id: str, section_index: int):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)
    evidence_map = ReportManager.get_evidence_map(report_id)
    if not evidence_map:
        return json_error(f"No evidence map available for report: {report_id}", status=404)
    section = next((item for item in evidence_map.get("sections", []) if item.get("section_index") == section_index), None)
    if not section:
        return json_error(f"Evidence section not found: {section_index}", status=404)
    return json_success(section)


@report_bp.route('/<report_id>/evidence/<int:section_index>/<claim_id>', methods=['GET'])
@handle_api_errors
def get_report_evidence_claim(report_id: str, section_index: int, claim_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)
    evidence_map = ReportManager.get_evidence_map(report_id)
    if not evidence_map:
        return json_error(f"No evidence map available for report: {report_id}", status=404)
    section = next((item for item in evidence_map.get("sections", []) if item.get("section_index") == section_index), None)
    if not section:
        return json_error(f"Evidence section not found: {section_index}", status=404)
    claim = next((item for item in section.get("claims", []) if item.get("claim_id") == claim_id), None)
    if not claim:
        return json_error(f"Claim not found: {claim_id}", status=404)
    return json_success(claim)


@report_bp.route('/<report_id>/download', methods=['GET'])
@handle_api_errors(log_prefix="Failed to download report")
def download_report(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    report = ReportManager.get_report(report_id)
    if not report:
        return json_error(f"Report does not exist: {report_id}", status=404)

    md_path = ReportManager._get_report_markdown_path(report_id)
    if not os.path.exists(md_path):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(report.markdown_content)
            temp_path = f.name
        return send_file(temp_path, as_attachment=True, download_name=f"{report_id}.md")

    return send_file(md_path, as_attachment=True, download_name=f"{report_id}.md")


@report_bp.route('/<report_id>', methods=['DELETE'])
@handle_api_errors(log_prefix="Failed to delete report")
def delete_report(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    success = ReportManager.delete_report(report_id)
    if not success:
        return json_error(f"Report does not exist: {report_id}", status=404)
    return json_success(message=f"Report deleted: {report_id}")


# ============== Report Agent Chat Interface ==============

@report_bp.route('/chat', methods=['POST'])
@handle_api_errors(log_prefix="Chat failed")
def chat_with_report_agent():
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    message = data.get('message')
    chat_history = data.get('chat_history', [])
    llm_model_override = (data.get('llm_model') or '').strip() or None

    if not simulation_id:
        return json_error("Please provide simulation_id", status=400)

    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)
    if not message:
        return json_error("Please provide message", status=400)

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

    project = ProjectManager.get_project(state.project_id)
    if not project:
        return json_error(f"Project does not exist: {state.project_id}", status=404)

    graph_id = state.graph_id or project.graph_id
    if not graph_id:
        return json_error("Missing graph ID", status=400)

    simulation_requirement = project.simulation_requirement or ""

    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        raise ValueError("GraphStorage not initialized — check Neo4j connection")
    graph_tools = GraphToolsService(storage=storage)

    agent = ReportAgent(
        graph_id=graph_id,
        simulation_id=simulation_id,
        simulation_requirement=simulation_requirement,
        graph_tools=graph_tools,
        model_name=llm_model_override,
    )

    result = agent.chat(message=message, chat_history=chat_history)
    return json_success({"response": result, "simulation_id": simulation_id})


# ============== Report Progress and Section Retrieval Interface ==============

@report_bp.route('/<report_id>/progress', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get report progress")
def get_report_progress(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    progress = ReportManager.get_progress(report_id)
    if not progress:
        return json_error(f"Report does not exist or progress info unavailable: {report_id}", status=404)
    return json_success(progress)


@report_bp.route('/<report_id>/sections', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get section list")
def get_report_sections(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    sections = ReportManager.get_generated_sections(report_id)
    report = ReportManager.get_report(report_id)
    is_complete = report is not None and report.status == ReportStatus.COMPLETED
    return json_success({
        "report_id": report_id,
        "sections": sections,
        "total": len(sections),
        "is_complete": is_complete
    })


@report_bp.route('/<report_id>/section/<int:section_index>', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get section content")
def get_single_section(report_id: str, section_index: int):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    section_path = ReportManager._get_section_path(report_id, section_index)
    if not os.path.exists(section_path):
        return json_error(f"Section does not exist: section_{section_index:02d}.md", status=404)
    with open(section_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return json_success({"filename": f"section_{section_index:02d}.md", "content": content})


# ============== Report Status Check Interface ==============

@report_bp.route('/check/<simulation_id>', methods=['GET'])
@handle_api_errors(log_prefix="Failed to check report status")
def check_report_status(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    report = ReportManager.get_report_by_simulation(simulation_id)
    has_report = report is not None
    report_status = report.status.value if report and hasattr(report.status, 'value') else (report.status if report else None)
    report_id = report.report_id if report else None
    interview_unlocked = has_report and report.status == ReportStatus.COMPLETED
    return json_success({
        "simulation_id": simulation_id,
        "has_report": has_report,
        "report_id": report_id,
        "report_status": report_status,
        "interview_unlocked": interview_unlocked
    })


# ============== Agent Log Interface ==============

@report_bp.route('/<report_id>/agent-log', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get agent log")
def get_agent_log(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    from_line = request.args.get('from_line', 0, type=int)
    log_data = ReportManager.get_agent_log(report_id, from_line=from_line)
    return json_success(log_data)


@report_bp.route('/<report_id>/agent-log/stream', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get agent log")
def stream_agent_log(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    logs = ReportManager.get_agent_log_stream(report_id)
    return json_success({"logs": logs, "count": len(logs)})


# ============== Console Log Interface ==============

@report_bp.route('/<report_id>/console-log', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get console log")
def get_console_log(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    from_line = request.args.get('from_line', 0, type=int)
    log_data = ReportManager.get_console_log(report_id, from_line=from_line)
    return json_success(log_data)


@report_bp.route('/<report_id>/console-log/stream', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get console log")
def stream_console_log(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    logs = ReportManager.get_console_log_stream(report_id)
    return json_success({"logs": logs, "count": len(logs)})


# ============== Tool Call Interface (For Debugging) ==============

@report_bp.route('/tools/search', methods=['POST'])
@handle_api_errors(log_prefix="Graph search failed")
def search_graph_tool():
    data = request.get_json() or {}
    graph_id = data.get('graph_id')
    query = data.get('query')
    limit = data.get('limit', 10)
    if not graph_id or not query:
        return json_error("Please provide graph_id and query", status=400)
    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        raise ValueError("GraphStorage not initialized — check Neo4j connection")
    tools = GraphToolsService(storage=storage)
    result = tools.search_graph(graph_id=graph_id, query=query, limit=limit)
    return json_success(result.to_dict())


@report_bp.route('/tools/statistics', methods=['POST'])
@handle_api_errors(log_prefix="Failed to get graph statistics")
def get_graph_statistics_tool():
    data = request.get_json() or {}
    graph_id = data.get('graph_id')
    if not graph_id:
        return json_error("Please provide graph_id", status=400)
    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        raise ValueError("GraphStorage not initialized — check Neo4j connection")
    tools = GraphToolsService(storage=storage)
    result = tools.get_graph_statistics(graph_id)
    return json_success(result)
