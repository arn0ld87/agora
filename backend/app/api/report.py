"""
Report API Routes
Provides interfaces for simulation report generation, retrieval, and conversation
"""

import os

from flask import Response, request, send_file, current_app

from . import report_bp
from ..contracts import (
    DEFAULT_REPORT_MODE,
    EvidenceMapModel,
    ReportMode,
)
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..services.graph_tools import GraphToolsService
from ..services.llm_runtime import parse_runtime_llm_config
from ..utils.auth import allow_ticket_auth
from ..utils.scopes import require_scope
from ..utils.api_errors import ApiErrorCode
from ..utils.logger import get_logger
from ..utils.validation import validate_report_id, validate_simulation_id, validate_task_id
from ..utils.api_responses import (
    handle_api_errors,
    json_error,
    json_error_from_exception,
    json_success,
)
from ..utils.rate_limit import build_rate_limit_key, report_rate_limiter

from ..services.report_generation import ReportGenerationService
from ..services.report_status import ReportStatusService
from ..services.report_export import (
    ReportExportService,
    ZIP_STREAM_THRESHOLD_BYTES,
    ZIP_HARD_CAP_BYTES,
    CSV_TABLES
)

logger = get_logger(__name__)

# Compatibility aliases for tests patching app.api.report
_ZIP_STREAM_THRESHOLD_BYTES = ZIP_STREAM_THRESHOLD_BYTES
_ZIP_HARD_CAP_BYTES = ZIP_HARD_CAP_BYTES
_can_reuse_existing_report = ReportGenerationService.can_reuse_existing_report
_estimate_zip_size = ReportExportService.estimate_zip_size
_build_zip_bundle = ReportExportService.build_zip_bundle
_stream_zip_bundle = ReportExportService.stream_zip_bundle
_build_csv_export = ReportExportService.build_csv_export
_build_export_envelope = ReportExportService.build_export_envelope
_map_outline_for_contract = ReportExportService.map_outline_for_contract


_REPORT_RATE_LIMIT_ENDPOINTS = {
    "report.generate_report",
    "report.chat_with_report_agent",
}


def _report_rate_limit_key() -> str:
    return build_rate_limit_key("report-llm-trigger", include_endpoint=True)


@report_bp.before_request
def _limit_report_llm_endpoints():
    if request.method != "POST" or request.endpoint not in _REPORT_RATE_LIMIT_ENDPOINTS:
        return None

    result = report_rate_limiter.check(
        _report_rate_limit_key(),
        max_requests=current_app.config["AGORA_REPORT_RATE_LIMIT_MAX"],
        window_seconds=current_app.config["AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS"],
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


_VALID_REPORT_MODES: tuple[str, ...] = ("strict", "balanced", "explorative")


def _resolve_report_mode() -> ReportMode:
    raw = request.args.get("mode")
    if raw is None:
        return DEFAULT_REPORT_MODE
    if raw not in _VALID_REPORT_MODES:
        raise ValueError(
            f"Ungültiger mode-Wert: {raw!r}. Erlaubt: {', '.join(_VALID_REPORT_MODES)}."
        )
    return raw  # type: ignore[return-value]


# ============== Report Generation Interface ==============

@report_bp.route('/generate', methods=['POST'])
@require_scope("report:write")
@handle_api_errors(log_prefix="Failed to start report generation task")
def generate_report():
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error("Please provide simulation_id", status=400)

    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    try:
        report_mode = _resolve_report_mode()
    except ValueError as mode_exc:
        return json_error(str(mode_exc), status=400)

    force_regenerate = data.get('force_regenerate', False)

    # Explizite UI-Auswahl (AiModelRef) ist die autoritative Report-Route und
    # darf nicht still mit Legacy-Feldern kombiniert werden (Issue #817).
    ai_model_ref = None
    raw_ref = data.get('ai_model_ref')
    if raw_ref is not None:
        from pydantic import ValidationError
        from ..contracts.ai_provider_contract import AiModelRef
        try:
            ai_model_ref = AiModelRef.model_validate(raw_ref)
        except ValidationError:
            return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="ai_model_ref ist ungültig")
        conflicting = [key for key in ('llm_profile_id', 'llm_model', 'llm_provider') if data.get(key)]
        if conflicting:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=f"ai_model_ref darf nicht mit {', '.join(conflicting)} kombiniert werden",
            )

    if ai_model_ref is None:
        from ..utils.llm_profile_resolver import expand_profile_in_data
        expand_profile_in_data(data)
        llm_model_override = (data.get('llm_model') or '').strip() or None
        try:
            llm_runtime = parse_runtime_llm_config(data)
        except ValueError as exc:
            return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message=str(exc))
        llm_profile_id = (data.get('llm_profile_id') or '').strip() or None
    else:
        llm_model_override = None
        llm_runtime = parse_runtime_llm_config({})
        llm_profile_id = None

    try:
        result = ReportGenerationService.start_generation(
            simulation_id=simulation_id,
            report_mode=report_mode,
            force_regenerate=force_regenerate,
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
            llm_profile_id=llm_profile_id,
            ai_model_ref=ai_model_ref,
        )
        return json_success(result)
    except ValueError as exc:
        return json_error_from_exception(exc)
    except RuntimeError as exc:
        return json_error_from_exception(exc, fallback_status=500)


@report_bp.route('/generate/status', methods=['POST'])
@handle_api_errors(log_prefix="Failed to query task status")
def get_generate_status():
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

    try:
        result = ReportStatusService.get_status(task_id, simulation_id, report_id)
        return json_success(result)
    except ValueError as exc:
        return json_error_from_exception(exc)


# ============== Report Retrieval Interface ==============

@report_bp.route('/<report_id>', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get report")
def get_report(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    report = ReportManager.get_report(report_id)
    if not report:
        return json_error(f"Report does not exist: {report_id}", status=404)
    return json_success(ReportExportService.build_report_contract_model(report).model_dump(mode="json"))


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get report")
def get_report_by_simulation(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    report = ReportManager.get_report_by_simulation(simulation_id)
    if not report:
        return json_error(
            f"No report available for this simulation: {simulation_id}",
            status=404,
            extra={"has_report": False},
        )
    return json_success(ReportExportService.build_report_contract_model(report).model_dump(mode="json"))


@report_bp.route('/list', methods=['GET'])
@handle_api_errors(log_prefix="Failed to list reports")
def list_reports():
    simulation_id = request.args.get('simulation_id')
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)
    limit = request.args.get('limit', 50, type=int)
    reports = ReportManager.list_reports(simulation_id=simulation_id, limit=limit)
    return json_success(
        [ReportExportService.build_report_contract_model(r).model_dump(mode="json") for r in reports],
        count=len(reports),
    )


@report_bp.route('/<report_id>/evidence', methods=['GET'])
@handle_api_errors
def get_report_evidence(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)
    evidence_map = ReportManager.get_evidence_map(report_id)
    if not evidence_map:
        return json_error(f"No evidence map available for report: {report_id}", status=404)
    from ..services.evidence_migrations import migrate_v1_to_v2
    migrated = migrate_v1_to_v2(evidence_map)
    return json_success(EvidenceMapModel.model_validate(migrated).model_dump(mode="json"))


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


@report_bp.route('/<report_id>/export', methods=['GET'])
@require_scope("report:read")
@allow_ticket_auth(lambda report_id: f"download:report:{report_id}")
@handle_api_errors(log_prefix="Failed to export report")
def export_report(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    fmt = (request.args.get('format') or 'md').strip().lower()
    if fmt not in ('md', 'json', 'csv', 'zip'):
        return json_error("format must be 'md', 'json', 'csv', or 'zip'", status=400)

    if fmt == 'zip':
        report = ReportManager.get_report(report_id)
        if not report:
            return json_error(f"Report does not exist: {report_id}", status=404)
        v3_path = ReportManager._get_report_v3_path(report_id)
        if not os.path.exists(v3_path) and not getattr(report, "markdown_content", None):
            return json_error("report_not_finalised", status=404)

        filename = f"agora-report-{report_id}-bundle.zip"
        estimated_size = _estimate_zip_size(report_id, report)

        if estimated_size > _ZIP_HARD_CAP_BYTES:
            return json_error(f"Export exceeds size limit ({_ZIP_HARD_CAP_BYTES // (1024 * 1024)} MB)", status=413)

        if estimated_size > _ZIP_STREAM_THRESHOLD_BYTES:
            from flask import stream_with_context
            gen = stream_with_context(_stream_zip_bundle(report_id, report))
            response = Response(gen, mimetype="application/zip")
            response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        zip_bytes = _build_zip_bundle(report_id, report)
        response = Response(zip_bytes, mimetype="application/zip")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    if fmt == 'csv':
        table = (request.args.get('table') or '').strip().lower()
        if table not in CSV_TABLES:
            return json_error(f"table must be one of: {', '.join(sorted(CSV_TABLES))}", status=400)

        report = ReportManager.get_report(report_id)
        if not report:
            return json_error(f"Report does not exist: {report_id}", status=404)

        csv_body = _build_csv_export(report_id, table)
        filename = f"agora-report-{report_id}-{table}.csv"
        response = Response(csv_body, mimetype="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    report = ReportManager.get_report(report_id)
    if not report:
        return json_error(f"Report does not exist: {report_id}", status=404)

    if fmt == 'md':
        download_name = f"agora-report-{report_id}.md"
        md_text = ReportManager.build_report_v3_markdown(report_id)
        if md_text is None:
            md_text = report.markdown_content or ""
        response = Response(md_text, mimetype='text/markdown; charset=utf-8')
        response.headers['Content-Disposition'] = f'attachment; filename="{download_name}"'
        return response

    envelope = _build_export_envelope(report, ReportManager.get_evidence_map(report_id))
    body = envelope.model_dump_json(indent=2)
    response = Response(body, mimetype='application/json; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="agora-report-{report_id}.json"'
    return response


@report_bp.route('/<report_id>/download', methods=['GET'])
@require_scope("report:read")
@allow_ticket_auth(lambda report_id: f"download:report:{report_id}")
@handle_api_errors(log_prefix="Failed to download report")
def download_report(report_id: str):
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    report = ReportManager.get_report(report_id)
    if not report:
        return json_error(f"Report does not exist: {report_id}", status=404)

    md_path = ReportManager._get_report_markdown_path(report_id)
    if not os.path.exists(md_path):
        return Response(
            report.markdown_content or "",
            mimetype="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{report_id}.md"',
                "Content-Type": "text/markdown; charset=utf-8",
            },
        )

    return send_file(
        md_path,
        as_attachment=True,
        download_name=f"{report_id}.md",
        mimetype="text/markdown; charset=utf-8",
    )


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
@require_scope("report:write")
@handle_api_errors(log_prefix="Chat failed")
def chat_with_report_agent():
    data = request.get_json() or {}
    from ..utils.llm_profile_resolver import expand_profile_in_data
    expand_profile_in_data(data)
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
