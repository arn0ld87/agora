"""
Graph API: Ontology and graph building endpoints.
"""

import os
import json
from collections.abc import Mapping

from flask import current_app, request
from pydantic import ValidationError

from . import graph_bp
from ..config import Config
from ..contracts.ai_provider_contract import AiModelRef
from ..models.project import ProjectManager, ProjectStatus
from ..services.llm_routing_seed import prevalidate_ai_model_ref_with_discovery
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.graph_build import (
    AI_MODEL_REF_ROUTING_FAILURE_MESSAGE,
    AiModelRefPostValidationError,
    AiModelRefRoutingInputError,
    GraphBuildService,
)
from ..utils.file_parser import FileParser
from ..services.text_processor import TextProcessor
from ..utils.logger import get_logger
from ..utils.validation import validate_project_id
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import (
    handle_api_errors,
    json_error,
    json_error_from_exception,
    json_success,
)
from ..utils.rate_limit import build_rate_limit_key, upload_rate_limiter
from ..utils.scopes import require_scope
from ..container import get_container

logger = get_logger('agora.api.graph_build')


_LEGACY_ROUTE_FIELDS = ("llm_model", "llm_profile_id", "llm_provider", "llm_runtime")


def _validate_ai_model_ref_payload(
    raw_ref: object, payload: Mapping[str, object]
) -> AiModelRef:
    if isinstance(raw_ref, str):
        try:
            raw_ref = json.loads(raw_ref)
        except json.JSONDecodeError as exc:
            raise ValueError("ai_model_ref ist ungültig") from exc

    try:
        ai_model_ref = AiModelRef.model_validate(raw_ref)
    except ValidationError as exc:
        raise ValueError("ai_model_ref ist ungültig") from exc

    conflicting = [key for key in _LEGACY_ROUTE_FIELDS if key in payload]
    if conflicting:
        raise ValueError(
            f"ai_model_ref darf nicht mit {', '.join(conflicting)} kombiniert werden"
        )

    prevalidate_ai_model_ref_with_discovery(ai_model_ref)
    return ai_model_ref


def allowed_file(file_storage) -> bool:
    """Check if file extension and content are allowed"""
    filename = file_storage.filename
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    if ext not in Config.ALLOWED_EXTENSIONS:
        return False

    if ext == 'pdf':
        try:
            header = file_storage.stream.read(4)
            file_storage.stream.seek(0)
            return header == b'%PDF'
        except Exception:  # noqa: BLE001 — best-effort cleanup; primary exception already propagated
            return False

    return True

def _upload_rate_limit_key() -> str:
    return build_rate_limit_key("graph-ontology-upload")

@graph_bp.before_request
def _limit_upload_endpoint():
    if request.endpoint != "graph.generate_ontology" or request.method != "POST":
        return None

    # Flask-config overrides allow tests + per-deployment knobs to flip the
    # rate-limit without touching the class default. Explicit None-check
    # instead of ``or`` so an operator-set 0 (= deny-all kill switch)
    # survives the fallback instead of silently reverting to Config.
    max_requests = current_app.config.get("AGORA_UPLOAD_RATE_LIMIT_MAX")
    if max_requests is None:
        max_requests = Config.AGORA_UPLOAD_RATE_LIMIT_MAX
    window_seconds = current_app.config.get("AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS")
    if window_seconds is None:
        window_seconds = Config.AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS
    result = upload_rate_limiter.check(
        _upload_rate_limit_key(),
        max_requests=max_requests,
        window_seconds=window_seconds,
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

@graph_bp.route('/ontology/generate', methods=['POST'])
@require_scope("graph:write")
@handle_api_errors(log_prefix="Ontology generation failed")
def generate_ontology():
    """Interface 1: Upload files and analyze to generate ontology definition"""
    simulation_requirement = request.form.get('simulation_requirement', '')
    project_name = request.form.get('project_name', 'Unnamed Project')
    additional_context = request.form.get('additional_context', '')

    if not simulation_requirement:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="Please provide simulation requirement description")

    ai_model_ref = None
    if "ai_model_ref" in request.form:
        try:
            ai_model_ref = _validate_ai_model_ref_payload(
                request.form.get("ai_model_ref"), request.form
            )
        except ValueError as exc:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=str(exc),
            )

        llm_model_override = None
        llm_runtime = None
        llm_profile_id = None
    else:
        llm_model_override = (request.form.get('llm_model') or '').strip() or None
        llm_provider_raw = request.form.get('llm_provider')
        llm_provider_payload = None
        if llm_provider_raw:
            try:
                llm_provider_payload = json.loads(llm_provider_raw)
            except json.JSONDecodeError:
                return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="llm_provider must be a valid JSON object")

        try:
            llm_runtime = parse_runtime_llm_config({"llm_provider": llm_provider_payload})
        except ValueError as exc:
            return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message=str(exc))

        llm_profile_id = (request.form.get('llm_profile_id') or '').strip() or None

    uploaded_files = request.files.getlist('files')
    if not uploaded_files or all(not f.filename for f in uploaded_files):
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="Please upload at least one document file")

    project = ProjectManager.create_project(name=project_name)
    project.simulation_requirement = simulation_requirement

    document_texts = []
    all_text = ""

    for file in uploaded_files:
        if file and file.filename:
            if not allowed_file(file):
                continue

            # Size check
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)
            max_upload_bytes = Config.AGORA_MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if size > max_upload_bytes:
                ProjectManager.delete_project(project.project_id)
                return json_error(
                    ApiErrorCode.UPLOAD_TOO_LARGE,
                    status=413,
                    message=f"File {file.filename} exceeds {Config.AGORA_MAX_UPLOAD_SIZE_MB}MB limit",
                )

            logger.info("Uploading file: %s (size: %d bytes) [project_id=%s]", file.filename, size, project.project_id)

            file_info = ProjectManager.save_file_to_project(project.project_id, file, file.filename)
            project.files.append({"filename": file_info["original_filename"], "size": file_info["size"]})

            text = FileParser.extract_text(file_info["path"])
            text = TextProcessor.preprocess_text(text)
            document_texts.append(text)
            all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

    if not document_texts:
        ProjectManager.delete_project(project.project_id)
        return json_error(ApiErrorCode.UNSUPPORTED_FORMAT, status=400, message="No documents successfully processed")

    project.total_text_length = len(all_text)
    ProjectManager.save_extracted_text(project.project_id, all_text)

    # Persistieren, BEVOR der Service das Projekt frisch von Platte lädt —
    # create_project() hat bereits VOR dem Setzen von simulation_requirement,
    # files und total_text_length gespeichert. Ohne dieses save_project gehen
    # die Felder verloren und Report-Generate/Simulation-Prepare lehnen das
    # Projekt mit "Missing simulation requirement description" (400) ab.
    ProjectManager.save_project(project)

    try:
        project = GraphBuildService.generate_ontology(
            project_id=project.project_id,
            simulation_requirement=simulation_requirement,
            document_texts=document_texts,
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
            llm_profile_id=llm_profile_id,
            additional_context=additional_context,
            ai_model_ref=ai_model_ref,
        )
    except AiModelRefRoutingInputError:
        # Nur echte ai_model_ref-Routingfehler werden hier klassifiziert. Der
        # Service hat bereits terminalisiert; die Prüfung läuft gegen den
        # *persistierten* Stand, damit sie tatsächlich idempotent ist und nicht
        # gegen die stale API-Instanz vergleicht.
        persisted = ProjectManager.get_project(project.project_id) or project
        if (
            persisted.status != ProjectStatus.FAILED
            or persisted.error != AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
        ):
            persisted.status = ProjectStatus.FAILED
            persisted.error = AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
            ProjectManager.save_project(persisted)
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=AI_MODEL_REF_ROUTING_FAILURE_MESSAGE,
        )
    except AiModelRefPostValidationError:
        # Betriebsfehler jenseits des Routings: Projekt/Run sind im Service
        # terminalisiert, nach außen darf kein Roh-Fehlertext gelangen.
        return json_error(
            "internal server error",
            status=500,
            code=ApiErrorCode.INTERNAL_ERROR,
        )
    except ValueError as exc:
        ProjectManager.delete_project(project.project_id)
        return json_error_from_exception(exc)

    return json_success({
        "project_id": project.project_id,
        "project_name": project.name,
        "ontology": project.ontology,
        "analysis_summary": project.analysis_summary,
        "files": project.files,
        "total_text_length": project.total_text_length
    })

@graph_bp.route('/build', methods=['POST'])
@require_scope("graph:write")
@handle_api_errors(log_prefix="Graph build initiation failed")
def build_graph():
    """Interface 2: Build graph based on project_id"""
    data = request.get_json() or {}
    project_id = data.get('project_id')
    if not project_id:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="Please provide project_id")
    if not validate_project_id(project_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    ai_model_ref = None
    if "ai_model_ref" in data:
        try:
            ai_model_ref = _validate_ai_model_ref_payload(data.get("ai_model_ref"), data)
        except ValueError as exc:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=str(exc),
            )

    project = ProjectManager.get_project(project_id)
    if not project:
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message=f"Project does not exist: {project_id}")

    if ai_model_ref is not None:
        llm_model_override = None
        llm_runtime = None
        llm_profile_id = None
    else:
        from ..utils.llm_profile_resolver import expand_profile_in_data
        expand_profile_in_data(data)

        llm_model_override = (data.get('llm_model') or '').strip() or project.llm_model or None
        llm_provider_payload = data.get('llm_provider')
        try:
            llm_runtime = parse_runtime_llm_config({"llm_provider": llm_provider_payload})
        except ValueError as exc:
            return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message=str(exc))

        llm_profile_id = (data.get('llm_profile_id') or '').strip() or None
    force = data.get('force', False)
    graph_name = data.get('graph_name', project.name or 'Agora Graph')
    chunk_size = data.get('chunk_size')
    chunk_overlap = data.get('chunk_overlap')

    container = get_container()
    if container.neo4j_storage is None:
        return json_error(ApiErrorCode.NEO4J_UNAVAILABLE, status=503, message="GraphStorage not initialized")

    try:
        task_id, run_id = GraphBuildService.build_graph(
            project_id=project_id,
            graph_name=graph_name,
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
            llm_profile_id=llm_profile_id,
            force=force,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            container=container,
            ai_model_ref=ai_model_ref,
        )
        return json_success({
            "project_id": project_id,
            "task_id": task_id,
            "run_id": run_id,
            "message": "Graph build task started. Query progress via /task/{task_id}"
        })
    except AiModelRefRoutingInputError:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=AI_MODEL_REF_ROUTING_FAILURE_MESSAGE,
        )
    except ValueError as exc:
        # Semantische Fehler (ONTOLOGY_MISSING, NOT_FOUND, fehlender Text)
        # behalten ihren Code — sie sind keine Routingprobleme.
        return json_error_from_exception(exc)
    except AiModelRefPostValidationError:
        return json_error(
            "internal server error",
            status=500,
            code=ApiErrorCode.INTERNAL_ERROR,
        )
    except RuntimeError as exc:
        # GRAPH_BUILD_IN_PROGRESS must surface the already-running task_id so
        # the client can poll status instead of starting a parallel run.
        code = exc.args[0] if exc.args else None
        if code == ApiErrorCode.GRAPH_BUILD_IN_PROGRESS and project.graph_build_task_id:
            return json_error(
                code,
                status=409,
                extra={"task_id": project.graph_build_task_id},
            )
        return json_error_from_exception(exc, fallback_status=409)
