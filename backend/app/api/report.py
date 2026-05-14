"""
Report API Routes
Provides interfaces for simulation report generation, retrieval, and conversation
"""

import io
import json
import os
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Literal, Optional, cast

from flask import Response, request, send_file, current_app
from pydantic import ValidationError

from . import report_bp
from ..contracts import (
    DEFAULT_REPORT_MODE,
    EvidenceMapModel,
    ReportContractModel,
    ReportMode,
    ReportModel,
)
from ..services.evidence_migrations import CURRENT_SCHEMA_VERSION, migrate_v1_to_v2
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.report_agent.csv_export import claims_to_csv, personas_to_csv, segments_to_csv
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..services.graph_tools import GraphToolsService
from ..services.llm_routing_seed import resolve_route_api_key, seed_run_stage_routing
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.stage_model_router import StageModelRouter
from ..utils.artifact_locator import ArtifactLocator
from ..utils.llm_client import LLMClient
from ..utils.auth import allow_ticket_auth
from ..utils.api_errors import ApiErrorCode
from ..utils.logger import get_logger
from ..utils.validation import validate_report_id, validate_simulation_id, validate_task_id
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.rate_limit import build_rate_limit_key, report_rate_limiter

logger = get_logger(__name__)
run_registry = RunRegistry()


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
    """Liest den optionalen ``?mode=``-Query-Parameter und validiert ihn.

    - Kein Parameter → ``DEFAULT_REPORT_MODE`` ('balanced').
    - Gültiger Literal-Wert → wird als ``ReportMode`` zurückgegeben.
    - Ungültiger Wert → ``ValueError`` (wird im Caller zu HTTP 400).

    Muss innerhalb eines Request-Kontexts aufgerufen werden.
    """
    raw = request.args.get("mode")
    if raw is None:
        return DEFAULT_REPORT_MODE
    if raw not in _VALID_REPORT_MODES:
        raise ValueError(
            f"Ungültiger mode-Wert: {raw!r}. "
            f"Erlaubt: {', '.join(_VALID_REPORT_MODES)}."
        )
    return raw  # type: ignore[return-value]


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

    try:
        report_mode = _resolve_report_mode()
    except ValueError as mode_exc:
        return json_error(str(mode_exc), status=400)

    force_regenerate = data.get('force_regenerate', False)
    llm_model_override = (data.get('llm_model') or '').strip() or None
    try:
        llm_runtime = parse_runtime_llm_config(data)
    except ValueError as exc:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message=str(exc))

    # P5.3: Optional llm_profile_id aus Request-Body — überschreibt Stage-Routing für diesen Run.
    llm_profile_id = (data.get('llm_profile_id') or '').strip() or None
    _resolved_profile = None
    if llm_profile_id:
        from ..services.llm_profiles_store import get_llm_profiles_store
        _resolved_profile = get_llm_profiles_store().get(llm_profile_id, include_api_key=True)
        if _resolved_profile is None:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=404,
                message=f"LLM profile {llm_profile_id!r} not found",
            )

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

    if _can_reuse_existing_report(force_regenerate, llm_model_override, llm_runtime.enabled):
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
            # Persist the model override so _resume_report_generate in runs.py
            # can reconstruct the same ReportAgent when the run is resumed. (Sub-Slice C)
            "llm_model": llm_model_override,
            "llm_provider": llm_runtime.redacted_metadata() or None,
        },
    )
    task_id = task_manager.create_task(
        task_type="report_generate",
        metadata={"simulation_id": simulation_id, "graph_id": graph_id, "report_id": report_id, "run_id": run_record["run_id"]}
    )
    seed_run_stage_routing(
        run_record["run_id"],
        "report_generation",
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
    )
    route_router = StageModelRouter(run_record["run_id"])
    resolved_route = route_router.resolve("report_generation")
    route_router.lock_stage("report_generation", resolved_route)

    # Initialize graph_tools in Flask context BEFORE spawning thread
    # (current_app is not available inside background threads)
    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        return json_error("GraphStorage not initialized — check Neo4j connection", status=500)

    # Bug-Fix: ReportAgent und GraphToolsService müssen denselben LLMClient
    # teilen, sonst nutzt GraphToolsService.llm beim Lazy-Init ``LLMClient()``
    # mit Config-Default — egal welches Modell der User für den Report gewählt
    # hat. Wir bauen den Client hier einmal und reichen ihn in beide rein.
    if _resolved_profile is not None:
        # P5.3: Profil-Override — Stage-Routing wird für diesen Run ignoriert.
        from ..utils.llm_client import build_client_from_profile as _build_from_profile
        shared_llm_client = _build_from_profile(_resolved_profile, run_id=run_record["run_id"])
        logger.info(
            "Using LLM profile %r for report (provider=%s, model=%s)",
            llm_profile_id,
            _resolved_profile.provider,
            _resolved_profile.model_name,
        )
    else:
        shared_llm_client = LLMClient.from_route(
            resolved_route,
            api_key=resolve_route_api_key(resolved_route, llm_runtime),
            run_id=run_record["run_id"],
        )
    graph_tools = GraphToolsService(storage=storage, llm_client=shared_llm_client)

    def run_generate():
        try:
            task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=0, message="Initializing Report Agent...")
            agent = ReportAgent(
                graph_id=graph_id,
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                graph_tools=graph_tools,
                llm_client=shared_llm_client,
                model_name=resolved_route.model,
            )
            def progress_callback(stage, progress, message):
                task_manager.update_task(task_id, progress=progress, message=f"[{stage}] {message}")
            report = agent.generate_report(progress_callback=progress_callback, report_id=report_id, report_mode=report_mode)
            ReportManager.save_report(report, report_mode=report_mode)
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
                "missing_sections": list(getattr(report_obj, "missing_sections", []) or []),
                "outline": _map_outline_for_contract(report_obj.outline.to_dict()) if report_obj and report_obj.outline else None,
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
    return json_success(_build_report_contract_model(report).model_dump(mode="json"))


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
    return json_success(_build_report_contract_model(report).model_dump(mode="json"))


@report_bp.route('/list', methods=['GET'])
@handle_api_errors(log_prefix="Failed to list reports")
def list_reports():
    simulation_id = request.args.get('simulation_id')
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)
    limit = request.args.get('limit', 50, type=int)
    reports = ReportManager.list_reports(simulation_id=simulation_id, limit=limit)
    return json_success(
        [_build_report_contract_model(r).model_dump(mode="json") for r in reports],
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


EXPORT_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION


def _can_reuse_existing_report(
    force_regenerate: bool,
    llm_model_override: Optional[str],
    runtime_provider_override: bool = False,
) -> bool:
    """Reuse only when the caller did not request concrete LLM runtime settings."""
    return not force_regenerate and not llm_model_override and not runtime_provider_override


def _map_outline_for_contract(outline: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Map the dataclass outline shape onto the v2 contract shape.

    ``ReportSection.to_dict`` emits ``{"title", "content"}``; ``ReportOutlineSectionModel``
    requires ``{"title", "description"}`` with ``extra="forbid"``. Existing reports
    are not rewritten on the storage side (Sub-Slice 02b/02c), so the boundary
    keeps both shapes aligned without mutating persisted data.

    Build the target dict explicitly with fallbacks — defending against extra
    keys (``extra="forbid"``) and ``min_length`` constraints that would
    otherwise reject legacy payloads with empty / None title or description.
    """
    if not outline:
        return None
    sections: list[dict[str, Any]] = []
    for raw in outline.get("sections") or []:
        if not isinstance(raw, dict):
            continue
        sections.append({
            "title": raw.get("title") or "Section",
            "description": raw.get("description") or raw.get("content") or "—",
        })
    return {
        "title": outline.get("title") or "Report",
        "summary": outline.get("summary") or "—",
        "sections": sections,
    }


def _build_report_contract_model(report_obj) -> ReportModel:
    report_dict = report_obj.to_dict()
    report_dict["schema_version"] = CURRENT_SCHEMA_VERSION
    report_dict["missing_sections"] = list(report_dict.get("missing_sections") or [])
    if report_dict.get("status") == ReportStatus.INCOMPLETE.value:
        report_dict["outline"] = None
    else:
        report_dict["outline"] = _map_outline_for_contract(report_dict.get("outline"))
    return ReportModel.model_validate(report_dict)


def _build_export_envelope(report_obj, raw_evidence_map: Optional[dict[str, Any]]) -> ReportContractModel:
    """Build the v2 export envelope.

    The envelope is strictly typed via ``ReportContractModel``. ``ReportModel`` is
    validated; legacy evidence-maps that do not yet satisfy ``EvidenceMapModel``
    fall back gracefully — we drop them from the envelope and log the issue
    rather than 500-ing on persisted v1-shaped payloads. Storage-side reshape
    is tracked under Sub-Slice 02b/02c (#107).
    """
    report = _build_report_contract_model(report_obj)

    evidence: Optional[EvidenceMapModel] = None
    migrated = migrate_v1_to_v2(raw_evidence_map) if raw_evidence_map else None
    if migrated:
        try:
            evidence = EvidenceMapModel.model_validate(migrated)
        except ValidationError as exc:
            logger.warning(
                "Evidence map for report %s is not yet contract-compliant; "
                "dropped from envelope (Sub-Slice 02b/02c follow-up). First errors: %s",
                report_obj.report_id,
                exc.errors(include_url=False)[:3],
            )

    return ReportContractModel(
        schema_version=cast(Literal[2], CURRENT_SCHEMA_VERSION),
        exported_at=datetime.now(timezone.utc),
        report=report,
        evidence=evidence,
    )


_CSV_TABLES = frozenset({"personas", "segments", "claims"})


@report_bp.route('/<report_id>/export', methods=['GET'])
@allow_ticket_auth(lambda report_id: f"download:report:{report_id}")
@handle_api_errors(log_prefix="Failed to export report")
def export_report(report_id: str):
    """Unified report export (Slice 5.1 + P4.2, contract-bound in Sub-Slice 02b).

    Query params:
      * ``format`` — ``md`` (default), ``json``, or ``csv``.
      * ``table``  — required when ``format=csv``: ``personas``, ``segments``, or ``claims``.

    ``md`` returns the rendered markdown as attachment.
    ``json`` returns a ``ReportContractModel``-shaped envelope
    ``{schema_version, exported_at, report, evidence}``. The envelope is built
    from ``app.contracts``; ``schema_version`` is locked to v2 by the contract.
    ``csv`` returns RFC-4180-konformes CSV für die angegebene Tabelle.
    """
    if not validate_report_id(report_id):
        return json_error("Invalid report_id format", status=400)

    fmt = (request.args.get('format') or 'md').strip().lower()
    if fmt not in ('md', 'json', 'csv', 'zip'):
        return json_error("format must be 'md', 'json', 'csv', or 'zip'", status=400)

    # --- ZIP branch (Sub-Slice P4.3) ---
    if fmt == 'zip':
        report = ReportManager.get_report(report_id)
        if not report:
            return json_error(f"Report does not exist: {report_id}", status=404)
        v3_path = ReportManager._get_report_v3_path(report_id)
        md_path = ReportManager._get_report_v3_markdown_path(report_id)
        if not os.path.exists(v3_path) and not os.path.exists(md_path):
            return json_error("report_not_finalised", status=404)
        zip_bytes = _build_zip_bundle(report_id, report)
        filename = f"agora-report-{report_id}-bundle.zip"
        response = Response(zip_bytes, mimetype="application/zip")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    # --- CSV branch (Sub-Slice P4.2) ---
    if fmt == 'csv':
        table = (request.args.get('table') or '').strip().lower()
        if table not in _CSV_TABLES:
            return json_error(
                f"table must be one of: {', '.join(sorted(_CSV_TABLES))}",
                status=400,
            )

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
        # MAI-06: On-demand-Render aus report-v3.json (Single Source of Truth).
        # Kein send_file mehr von full_report.md oder report-v3.md.
        md_text = ReportManager.build_report_v3_markdown(report_id)
        if md_text is None:
            # Fallback für Bestandsreports ohne v3-Artefakt.
            md_text = report.markdown_content or ""
        response = Response(md_text, mimetype='text/markdown; charset=utf-8')
        response.headers['Content-Disposition'] = f'attachment; filename="{download_name}"'
        return response

    envelope = _build_export_envelope(report, ReportManager.get_evidence_map(report_id))
    body = envelope.model_dump_json(indent=2)
    response = Response(body, mimetype='application/json; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="agora-report-{report_id}.json"'
    return response


def _build_csv_export(report_id: str, table: str) -> str:
    """Lädt die passende Datenquelle und gibt RFC-4180-CSV zurück.

    Datenquellen:
    - personas / segments: report-v3.json (falls vorhanden), sonst leere Liste.
    - claims: evidence-map.json sections[].claims[].

    Kein hartes Coupling auf ReportV3 — falls P3.1 später landet,
    kann die Quelle per Folge-Slice umgestellt werden.
    """
    if table in ("personas", "segments"):
        report_v3 = ReportManager.get_report_v3(report_id) or {}
        if table == "personas":
            return personas_to_csv(report_v3.get("personas") or [])
        return segments_to_csv(report_v3.get("segments") or [])

    # table == "claims"
    evidence_map = ReportManager.get_evidence_map(report_id) or {}
    return claims_to_csv(evidence_map.get("sections") or [])


def _build_zip_bundle(report_id: str, report: Any) -> bytes:
    """Baut ein ZIP-Archiv mit allen Report-Artefakten im Speicher.

    Enthält:
    - agora-report-<id>/report-v3.md    (Pflicht, falls vorhanden)
    - agora-report-<id>/report-v3.json  (Pflicht, falls vorhanden)
    - agora-report-<id>/evidence-map.json
    - agora-report-<id>/personas.csv
    - agora-report-<id>/segments.csv
    - agora-report-<id>/claims.csv

    Sub-Slice P4.3 — Refs PLAN.md §5.3
    """
    prefix = f"agora-report-{report_id}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # --- report-v3.md ---
        # MAI-06: On-demand-Render aus report-v3.json (Single Source of Truth).
        # Kein Dateisystem-Read mehr — _get_report_v3_markdown_path() wird nicht mehr geschrieben.
        md_text = ReportManager.build_report_v3_markdown(report_id)
        if md_text is None:
            md_text = getattr(report, "markdown_content", None)
        if md_text:
            zf.writestr(f"{prefix}/report-v3.md", md_text)

        # --- report-v3.json ---
        v3_path = ReportManager._get_report_v3_path(report_id)
        if os.path.exists(v3_path):
            with open(v3_path, encoding="utf-8") as fh:
                zf.writestr(f"{prefix}/report-v3.json", fh.read())

        # --- evidence-map.json ---
        evidence_map = ReportManager.get_evidence_map(report_id) or {}
        zf.writestr(
            f"{prefix}/evidence-map.json",
            json.dumps(evidence_map, ensure_ascii=False, indent=2),
        )

        # --- CSV-Tabellen ---
        report_v3 = ReportManager.get_report_v3(report_id) or {}
        zf.writestr(
            f"{prefix}/personas.csv",
            personas_to_csv(report_v3.get("personas") or []),
        )
        zf.writestr(
            f"{prefix}/segments.csv",
            segments_to_csv(report_v3.get("segments") or []),
        )
        zf.writestr(
            f"{prefix}/claims.csv",
            claims_to_csv(evidence_map.get("sections") or []),
        )

    return buf.getvalue()


@report_bp.route('/<report_id>/download', methods=['GET'])
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
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(report.markdown_content)
            temp_path = f.name
        return send_file(temp_path, as_attachment=True, download_name=f"{report_id}.md")

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
