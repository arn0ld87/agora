"""
Graph-related API Routes
Uses project context mechanism with server-side state persistence
"""

import io
import json
import os
import time
import threading
from flask import Response, request, current_app

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.llm_routing_seed import resolve_route_api_key, seed_run_stage_routing
from ..services.llm_runtime import parse_runtime_llm_config
from ..container import get_container
from ..services.graph_builder import GraphBuilderService  # noqa: F401  (kept for type re-exports)
from ..services.stage_model_router import StageModelRouter
from ..services.text_processor import TextProcessor
from ..storage.ner_extractor import NERExtractor
from ..utils.file_parser import FileParser
from ..utils.artifact_locator import ArtifactLocator
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..utils.validation import validate_project_id, validate_graph_id, validate_task_id
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus
from ..models.graph import GraphDataDTO
from ..services.run_registry import RunRegistry
from ..services.secret_resolver import SecretResolver
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.graph_diff_helpers import build_pydantic_graph_diff
from ..utils.rate_limit import build_rate_limit_key, upload_rate_limiter

# Get logger
logger = get_logger('agora.api')
run_registry = RunRegistry()


def _get_storage():
    """Get Neo4jStorage from Flask app extensions."""
    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        raise ValueError("GraphStorage not initialized — check Neo4j connection")
    return storage


def allowed_file(file_storage) -> bool:
    """Check if file extension and content are allowed"""
    filename = file_storage.filename
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    if ext not in Config.ALLOWED_EXTENSIONS:
        return False

    # Basic content verification for PDF
    if ext == 'pdf':
        try:
            header = file_storage.stream.read(4)
            file_storage.stream.seek(0)
            return header == b'%PDF'
        except Exception:
            return False

    return True


def _upload_rate_limit_key() -> str:
    return build_rate_limit_key("graph-ontology-upload")


@graph_bp.before_request
def _limit_upload_endpoint():
    if request.endpoint != "graph.generate_ontology" or request.method != "POST":
        return None

    result = upload_rate_limiter.check(
        _upload_rate_limit_key(),
        max_requests=current_app.config["AGORA_UPLOAD_RATE_LIMIT_MAX"],
        window_seconds=current_app.config["AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS"],
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


# ============== Project Management Interface ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
@handle_api_errors
def get_project(project_id: str):
    """
    Get project details
    """
    if not validate_project_id(project_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    project = ProjectManager.get_project(project_id)
    
    if not project:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Project does not exist: {project_id}",
        )
    
    return json_success(project.to_dict())


@graph_bp.route('/project/list', methods=['GET'])
@handle_api_errors
def list_projects():
    """
    List all projects
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return json_success([p.to_dict() for p in projects], count=len(projects))


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
@handle_api_errors
def delete_project(project_id: str):
    """
    Delete project
    """
    if not validate_project_id(project_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    success = ProjectManager.delete_project(project_id)

    if not success:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Project does not exist or deletion failed: {project_id}",
        )

    return json_success(message=f"Project deleted: {project_id}")


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
@handle_api_errors
def reset_project(project_id: str):
    """
    Reset project status (for rebuilding graph)
    """
    if not validate_project_id(project_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    project = ProjectManager.get_project(project_id)

    if not project:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Project does not exist: {project_id}",
        )

    # Reset to ontology generated state
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED

    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)

    return json_success(project.to_dict(), message=f"Project reset: {project_id}")


# ============== Interface 1: Upload Files and Generate Ontology ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
@handle_api_errors(log_prefix="Ontology generation failed")
def generate_ontology():
    """
    Interface 1: Upload files and analyze to generate ontology definition
    """
    logger.info("=== Starting ontology generation ===")

    # Get parameters
    simulation_requirement = request.form.get('simulation_requirement', '')
    project_name = request.form.get('project_name', 'Unnamed Project')
    additional_context = request.form.get('additional_context', '')

    logger.debug(f"Project name: {project_name}")
    logger.debug(f"Simulation requirement: {simulation_requirement[:100]}...")

    if not simulation_requirement:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Please provide simulation requirement description (simulation_requirement)",
        )

    # LLM-Override aus dem Frontend (Modell + optionaler Runtime-Provider).
    # `MainView.handleNewProject` hängt `llm_model` und `llm_provider` (als
    # JSON-String) ans FormData; ohne diese Felder fällt der LLMClient auf
    # den Server-Default zurück.
    llm_model_override = (request.form.get('llm_model') or '').strip() or None
    llm_provider_raw = request.form.get('llm_provider')
    if llm_provider_raw:
        try:
            llm_provider_payload = json.loads(llm_provider_raw)
        except json.JSONDecodeError:
            return json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="llm_provider must be a valid JSON object",
            )
    else:
        llm_provider_payload = None
    try:
        llm_runtime = parse_runtime_llm_config({"llm_provider": llm_provider_payload})
    except ValueError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )

    # P5.3: Optional llm_profile_id aus Form-Data — überschreibt Stage-Routing für diesen Run.
    llm_profile_id = (request.form.get('llm_profile_id') or '').strip() or None
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

    # Get uploaded files
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or all(not f.filename for f in uploaded_files):
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Please upload at least one document file",
        )

    # Create project
    project = ProjectManager.create_project(name=project_name)
    project.simulation_requirement = simulation_requirement
    logger.info(f"Project created: {project.project_id}")

    # Save files and extract text
    document_texts = []
    all_text = ""

    for file in uploaded_files:
        if file and file.filename:
            if not allowed_file(file):
                logger.warning(f"File rejected by allowed_file: {file.filename}")
                continue

            # Save file to project directory
            file_info = ProjectManager.save_file_to_project(
                project.project_id,
                file,
                file.filename
            )
            project.files.append({
                "filename": file_info["original_filename"],
                "size": file_info["size"]
            })

            # Extract text
            text = FileParser.extract_text(file_info["path"])
            text = TextProcessor.preprocess_text(text)
            document_texts.append(text)
            all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

    if not document_texts:
        ProjectManager.delete_project(project.project_id)
        return json_error(
            ApiErrorCode.UNSUPPORTED_FORMAT,
            status=400,
            message="No documents successfully processed. Please check file format",
        )

    # Save extracted text
    project.total_text_length = len(all_text)
    ProjectManager.save_extracted_text(project.project_id, all_text)
    logger.info(f"Text extraction completed, total {len(all_text)} characters")

    # Generate ontology
    run_record = run_registry.create_run(
        run_type="ontology_generate",
        entity_id=project.project_id,
        status="processing",
        progress=0,
        message="Ontology generation started",
        linked_ids={"project_id": project.project_id},
    )
    run_id = run_record["run_id"]
    seed_run_stage_routing(
        run_id,
        "ontology_generation",
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
    )
    route_router = StageModelRouter(run_id)
    ingest_route = route_router.resolve("document_ingest")
    route_router.lock_stage("document_ingest", ingest_route)
    ontology_route = route_router.resolve("ontology_generation")
    route_router.lock_stage("ontology_generation", ontology_route)

    if _resolved_profile is not None:
        # P5.3: Profil-Override — Stage-Routing wird für diesen Run ignoriert.
        from ..utils.llm_client import build_client_from_profile as _build_from_profile
        llm_client = _build_from_profile(_resolved_profile, run_id=run_id)
        logger.info(
            "Using LLM profile %r for ontology (provider=%s, model=%s)",
            llm_profile_id,
            _resolved_profile.provider,
            _resolved_profile.model_name,
        )
    else:
        llm_client = LLMClient.from_route(
            ontology_route,
            secret_resolver=SecretResolver(),
            api_key_override=resolve_route_api_key(ontology_route, llm_runtime),
            run_id=run_id,
        )
        logger.info(
            "Calling LLM to generate ontology definition (model=%s, provider=%s, version=%d)",
            llm_client.model,
            ontology_route.provider_id,
            ontology_route.routing_version,
        )
    generator = OntologyGenerator(llm_client=llm_client)
    ontology = generator.generate(
        document_texts=document_texts,
        simulation_requirement=simulation_requirement,
        additional_context=additional_context if additional_context else None
    )

    # Save ontology to project
    entity_count = len(ontology.get("entity_types", []))
    edge_count = len(ontology.get("edge_types", []))
    logger.info(f"Ontology generation completed: {entity_count} entity types, {edge_count} relation types")

    project.ontology = {
        "entity_types": ontology.get("entity_types", []),
        "edge_types": ontology.get("edge_types", [])
    }
    project.analysis_summary = ontology.get("analysis_summary", "")
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    # Modellauswahl pro Projekt persistieren — Folgestufen (Build/Persona/
    # Report) können sie als Default verwenden, wenn der jeweilige Request
    # keinen Override mitschickt. Secrets bleiben ausserhalb (redacted_metadata).
    project.llm_model = llm_model_override
    project.llm_provider = llm_runtime.redacted_metadata() or None
    ProjectManager.save_project(project)
    run_registry.update_run(
        run_id,
        status="completed",
        progress=100,
        message="Ontology generation completed",
        linked_ids={"project_id": project.project_id},
    )
    logger.info(f"=== Ontology generation completed === Project ID: {project.project_id}")

    return json_success({
        "project_id": project.project_id,
        "project_name": project.name,
        "ontology": project.ontology,
        "analysis_summary": project.analysis_summary,
        "files": project.files,
        "total_text_length": project.total_text_length
    })


# ============== Private helpers for build_graph ==============


def _validate_build_request(data: dict):
    """Validate project_id from request data and look up the project.

    Returns ``(project_id, project, error_response)`` where *error_response*
    is ``None`` on success.
    """
    project_id = data.get('project_id')
    logger.debug(f"Request parameters: project_id={project_id}")

    if not project_id:
        return None, None, json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Please provide project_id",
        )

    if not validate_project_id(project_id):
        return None, None, json_error(ApiErrorCode.INVALID_ID, status=400)

    project = ProjectManager.get_project(project_id)
    if not project:
        return None, None, json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Project does not exist: {project_id}",
        )

    return project_id, project, None


def _resolve_llm_overrides(data: dict, project):
    """Parse llm_model / llm_provider from *data* and build RuntimeLlmConfig.

    Returns ``(llm_runtime, llm_model_override, error_response)`` where
    *error_response* is ``None`` on success.
    """
    # Reihenfolge: explizit im Request > persistiert am Projekt aus dem
    # Ontology-Schritt > Server-Default. Secrets (api_key) sind im Projekt
    # nicht persistiert (redacted_metadata) — daher kann der Build den
    # Provider-Override nur dann rekonstruieren, wenn der Request ihn
    # erneut mitschickt.
    llm_model_override = (data.get('llm_model') or '').strip() or project.llm_model or None
    llm_provider_payload = data.get('llm_provider')
    try:
        llm_runtime = parse_runtime_llm_config({"llm_provider": llm_provider_payload})
    except ValueError as exc:
        return None, None, json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )

    return llm_runtime, llm_model_override, None


def _check_project_state_for_build(project, force: bool):
    """Check and optionally reset project status before a build.

    Returns ``error_response`` (a tuple ready for Flask return) or ``None``
    when the project state is acceptable for starting a build.  Mutates
    *project* in-place when a force-reset is performed.
    """
    if project.status == ProjectStatus.CREATED:
        return json_error(
            ApiErrorCode.ONTOLOGY_MISSING,
            status=400,
            message="Project has not generated ontology yet. Please call /ontology/generate first",
        )

    if project.status == ProjectStatus.GRAPH_BUILDING and not force:
        return json_error(
            ApiErrorCode.GRAPH_BUILD_IN_PROGRESS,
            status=409,
            message="Graph is being built. Do not submit repeatedly. To force rebuild, add force: true",
            extra={"task_id": project.graph_build_task_id},
        )

    if force and project.status in [
        ProjectStatus.GRAPH_BUILDING,
        ProjectStatus.FAILED,
        ProjectStatus.GRAPH_COMPLETED,
    ]:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.graph_id = None
        project.graph_build_task_id = None
        project.error = None

    return None


def _load_build_inputs(project_id: str, project, data: dict):
    """Read configuration, extracted text and ontology for the build.

    Returns ``(graph_name, text, ontology, chunk_size, chunk_overlap, error_response)``
    where *error_response* is ``None`` on success.  Also persists chunk
    params back onto *project*.
    """
    graph_name = data.get('graph_name', project.name or 'Agora Graph')
    chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
    chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

    project.chunk_size = chunk_size
    project.chunk_overlap = chunk_overlap

    text = ProjectManager.get_extracted_text(project_id)
    if not text:
        return None, None, None, None, None, json_error(
            ApiErrorCode.NOT_FOUND,
            status=400,
            message="Extracted text not found",
        )

    ontology = project.ontology
    if not ontology:
        return None, None, None, None, None, json_error(
            ApiErrorCode.ONTOLOGY_MISSING,
            status=400,
            message="Ontology definition not found",
        )

    return graph_name, text, ontology, chunk_size, chunk_overlap, None


def _create_build_run_record(project_id: str, project, graph_name: str, task_manager: TaskManager):
    """Register run + task records and transition project to GRAPH_BUILDING.

    Returns ``(run_record, task_id)``.
    """
    run_record = run_registry.create_run(
        run_type="graph_build",
        entity_id=project_id,
        status="pending",
        progress=0,
        message="Graph build queued",
        linked_ids={"project_id": project_id},
        artifacts=ArtifactLocator.existing_paths({
            "project_dir": ProjectManager._get_project_dir(project_id),
        }),
        resume_capability={"available": True, "action": "restart", "label": "Restart graph build"},
        metadata={"graph_name": graph_name},
    )
    task_id = task_manager.create_task(
        f"Build graph: {graph_name}",
        metadata={"project_id": project_id, "run_id": run_record["run_id"]},
    )
    logger.info(f"Graph build task created: task_id={task_id}, project_id={project_id}")

    project.status = ProjectStatus.GRAPH_BUILDING
    project.graph_build_task_id = task_id
    ProjectManager.save_project(project)

    return run_record, task_id


def _make_ner_override_from_route(run_id: str, resolved_route, llm_runtime) -> NERExtractor:
    """Build a dedicated NERExtractor from the resolved per-run route."""
    ner_llm_client = LLMClient.from_route(
        resolved_route,
        secret_resolver=SecretResolver(),
        api_key_override=resolve_route_api_key(resolved_route, llm_runtime),
        run_id=run_id,
    )
    logger.info(
        "Build-Pfad nutzt Route-Snapshot: model=%s provider=%s",
        ner_llm_client.model,
        resolved_route.provider_id,
    )
    return NERExtractor(llm_client=ner_llm_client)


# ============== Interface 2: Build Graph ==============

@graph_bp.route('/build', methods=['POST'])
@handle_api_errors(log_prefix="Graph build initiation failed")
def build_graph():
    """
    Interface 2: Build graph based on project_id
    """
    logger.info("=== Starting graph build ===")

    data = request.get_json() or {}

    project_id, project, err = _validate_build_request(data)
    if err is not None:
        return err

    llm_runtime, llm_model_override, err = _resolve_llm_overrides(data, project)
    if err is not None:
        return err

    force = data.get('force', False)
    err = _check_project_state_for_build(project, force)
    if err is not None:
        return err

    graph_name, text, ontology, chunk_size, chunk_overlap, err = _load_build_inputs(
        project_id, project, data
    )
    if err is not None:
        return err

    # Capture container in the request thread so the background closure
    # below can resolve services without a live Flask app context.
    container = get_container()
    if container.neo4j_storage is None:
        return json_error(
            ApiErrorCode.NEO4J_UNAVAILABLE,
            status=503,
            message="GraphStorage not initialized",
        )

    task_manager = TaskManager()
    run_record, task_id = _create_build_run_record(project_id, project, graph_name, task_manager)
    seed_run_stage_routing(
        run_record["run_id"],
        "graph_build",
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
    )
    route_router = StageModelRouter(run_record["run_id"])
    resolved_route = route_router.resolve("graph_build")
    route_router.lock_stage("graph_build", resolved_route)

    ner_override: NERExtractor = _make_ner_override_from_route(
        run_record["run_id"],
        resolved_route,
        llm_runtime,
    )

    # Start background task
    def build_task():
        build_logger = get_logger('agora.build')
        try:
            build_logger.info(f"[{task_id}] Starting graph build...")
            task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                message="Initializing graph build service..."
            )

            # Resolve via container captured in the outer closure (Issue #14).
            builder = container.graph_builder()

            # Chunk text
            task_manager.update_task(
                task_id,
                message="Chunking text...",
                progress=5
            )
            chunks = TextProcessor.split_text(
                text,
                chunk_size=chunk_size,
                overlap=chunk_overlap
            )
            total_chunks = len(chunks)

            # Create graph
            task_manager.update_task(
                task_id,
                message="Creating Zep graph...",
                progress=10
            )
            graph_id = builder.create_graph(name=graph_name)

            # Update project graph_id
            project.graph_id = graph_id
            ProjectManager.save_project(project)
            run_registry.update_run(
                run_record["run_id"],
                entity_id=project.graph_id or project_id,
                linked_ids={"graph_id": graph_id, "project_id": project_id, "task_id": task_id},
                message=f"Graph created: {graph_id}",
            )

            # Set ontology
            task_manager.update_task(
                task_id,
                message="Setting ontology definition...",
                progress=15
            )
            builder.set_ontology(graph_id, ontology)

            # Add text (progress_callback signature is (msg, progress_ratio, completed, total))
            def add_progress_callback(msg, progress_ratio, completed, total):
                progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                task_manager.update_task(
                    task_id,
                    message=msg,
                    progress=progress,
                    progress_detail={
                        "batch_count": completed,
                        "total_batches": total,
                        "batch_at": time.time(),
                    },
                )

            task_manager.update_task(
                task_id,
                message=f"Starting to add {total_chunks} text chunks...",
                progress=15
            )

            builder.add_text_batches(
                graph_id,
                chunks,
                batch_size=3,
                progress_callback=add_progress_callback,
                ner_extractor=ner_override,
            )

            # Neo4j processing is synchronous, no need to wait
            task_manager.update_task(
                task_id,
                message="Text processing completed, generating graph data...",
                progress=90
            )

            # Get graph data
            task_manager.update_task(
                task_id,
                message="Retrieving graph data...",
                progress=95
            )
            graph_data = builder.get_graph_data(graph_id)

            # Update project status
            project.status = ProjectStatus.GRAPH_COMPLETED
            ProjectManager.save_project(project)

            node_count = graph_data.get("node_count", 0)
            edge_count = graph_data.get("edge_count", 0)
            build_logger.info(f"[{task_id}] Graph build completed: graph_id={graph_id}, nodes={node_count}, edges={edge_count}")

            # Complete
            task_manager.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                message="Graph build completed",
                progress=100,
                result={
                    "project_id": project_id,
                    "graph_id": graph_id,
                    "node_count": node_count,
                    "edge_count": edge_count,
                    "chunk_count": total_chunks
                }
            )
            run_registry.update_run(
                run_record["run_id"],
                status="completed",
                progress=100,
                message="Graph build completed",
                artifacts=ArtifactLocator.existing_paths({
                    "project_dir": ProjectManager._get_project_dir(project_id),
                }),
            )

        except Exception as e:
            # Update project status to failed
            import traceback
            build_logger.error(f"[{task_id}] Graph build failed: {str(e)}")
            build_logger.debug(traceback.format_exc())

            project.status = ProjectStatus.FAILED
            project.error = str(e)
            ProjectManager.save_project(project)

            task_manager.update_task(
                task_id,
                status=TaskStatus.FAILED,
                message=f"Build failed: {str(e)}",
                error=traceback.format_exc()
            )
            run_registry.update_run(
                run_record["run_id"],
                status="failed",
                message=f"Build failed: {str(e)}",
                error=str(e),
            )

    # Start background thread
    thread = threading.Thread(target=build_task, daemon=True)
    thread.start()

    return json_success({
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_record["run_id"],
        "message": "Graph build task started. Query progress via /task/{task_id}"
    })


# ============== Task Query Interface ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
@handle_api_errors
def get_task(task_id: str):
    """
    Query task status
    """
    if not validate_task_id(task_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    task = TaskManager().get_task(task_id)

    if not task:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Task does not exist: {task_id}",
        )

    return json_success(task.to_dict())


@graph_bp.route('/tasks', methods=['GET'])
@handle_api_errors
def list_tasks():
    """
    List all tasks
    """
    tasks = TaskManager().list_tasks()
    
    return json_success([t.to_dict() for t in tasks], count=len(tasks))


# ============== Graph Data Interface ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
@handle_api_errors
def get_graph_data(graph_id: str):
    """
    Get graph data (nodes and edges).

    Issue #52: Response geht durch ``GraphDataDTO``, damit das Wire-Format
    explizit dokumentiert und gegen Storage-Drift abgesichert ist.
    """
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    builder = get_container().graph_builder()
    graph_data = builder.get_graph_data(graph_id)
    dto = GraphDataDTO.from_storage_dict(graph_data)

    return json_success(dto.to_dict())


@graph_bp.route('/snapshot/<graph_id>/<int:round_num>', methods=['GET'])
@handle_api_errors
def get_graph_snapshot(graph_id: str, round_num: int):
    """Return the set of RELATION edges valid at ``round_num`` (Issue #10)."""
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)
    if round_num < 0:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="round_num must be >= 0",
        )

    service = get_container().temporal_graph()
    snapshot = service.get_snapshot(graph_id, round_num)
    return json_success(snapshot.to_dict())


@graph_bp.route('/<graph_id>/diff', methods=['GET'])
@handle_api_errors
def get_graph_diff(graph_id: str):
    """Return added / removed / reinforced edges between two rounds (Sub-Slice 22, Closes #74).

    Query params: ``start_round``, ``end_round`` (both required, ints >= 0).
    Response is validated against the Layer-0 ``GraphDiff`` Pydantic contract
    before serialisation.
    """
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    raw_start = request.args.get('start_round')
    raw_end = request.args.get('end_round')

    if raw_start is None or raw_end is None:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Pflichtparameter: start_round und end_round (int)",
        )

    try:
        start_round = int(raw_start)
        end_round = int(raw_end)
    except (TypeError, ValueError):
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="start_round und end_round müssen ganze Zahlen sein",
        )

    if start_round < 0 or end_round < 0:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="start_round und end_round müssen >= 0 sein",
        )

    if end_round < start_round:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="end_round muss >= start_round sein",
        )

    svc = get_container().temporal_graph()
    service_diff = svc.compute_diff(graph_id, start_round, end_round)
    snap_a = svc.get_snapshot(graph_id, start_round)
    snap_b = svc.get_snapshot(graph_id, end_round)

    graph_diff = build_pydantic_graph_diff(
        service_diff=service_diff,
        snap_a=snap_a,
        snap_b=snap_b,
        graph_id=graph_id,
        start_round=start_round,
        end_round=end_round,
    )
    return json_success(graph_diff.model_dump(mode="json"))


def _stringify(value):
    """GraphML only accepts scalars — coerce lists/dicts to JSON strings."""
    import json as _json
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return _json.dumps(value, ensure_ascii=False, default=str)


def _build_networkx_graph(graph_data: dict):
    import networkx as nx

    g = nx.MultiDiGraph()
    g.graph["graph_id"] = graph_data.get("graph_id", "")

    for node in graph_data.get("nodes", []) or []:
        node_id = node.get("uuid") or node.get("id")
        if not node_id:
            continue
        attrs = {k: _stringify(v) for k, v in node.items() if k != "uuid"}
        g.add_node(node_id, **attrs)

    for edge in graph_data.get("edges", []) or []:
        src = edge.get("source_uuid") or edge.get("source")
        tgt = edge.get("target_uuid") or edge.get("target")
        if not src or not tgt:
            continue
        attrs = {
            k: _stringify(v)
            for k, v in edge.items()
            if k not in ("source_uuid", "target_uuid", "source", "target")
        }
        g.add_edge(src, tgt, **attrs)

    return g


@graph_bp.route('/<graph_id>/export', methods=['GET'])
@handle_api_errors
def export_graph(graph_id: str):
    """Export the full graph as GraphML for downstream graph tooling (Slice 5.3).

    Query params: ``format=graphml`` (only currently supported value).
    """
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    fmt = (request.args.get('format') or 'graphml').strip().lower()
    if fmt != 'graphml':
        return json_error(
            ApiErrorCode.UNSUPPORTED_FORMAT,
            status=400,
            message="format must be 'graphml'",
        )

    builder = get_container().graph_builder()
    graph_data = builder.get_graph_data(graph_id)
    if not graph_data or (not graph_data.get("nodes") and not graph_data.get("edges")):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Graph not found or empty: {graph_id}",
        )

    import networkx as nx

    g = _build_networkx_graph(graph_data)
    buf = io.BytesIO()
    nx.write_graphml(g, buf, named_key_ids=True)
    body = buf.getvalue()

    response = Response(body, mimetype='application/xml; charset=utf-8')
    response.headers['Content-Disposition'] = (
        f'attachment; filename="agora-graph-{graph_id}.graphml"'
    )
    return response


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
@handle_api_errors
def delete_graph(graph_id: str):
    """
    Delete graph
    """
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    builder = get_container().graph_builder()
    builder.delete_graph(graph_id)

    return json_success(message=f"Graph deleted: {graph_id}")
