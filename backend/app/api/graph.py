"""
Graph-related API Routes
Uses project context mechanism with server-side state persistence
"""

import os
import threading
from flask import request, current_app

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from ..utils.validation import validate_project_id, validate_graph_id, validate_task_id
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus
from ..services.run_registry import RunRegistry
from ..utils.api_responses import handle_api_errors, json_success, json_error

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


# ============== Project Management Interface ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
@handle_api_errors
def get_project(project_id: str):
    """
    Get project details
    """
    if not validate_project_id(project_id):
        return json_error("Invalid project_id format", status=400)

    project = ProjectManager.get_project(project_id)
    
    if not project:
        return json_error(f"Project does not exist: {project_id}", status=404)
    
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
        return json_error("Invalid project_id format", status=400)

    success = ProjectManager.delete_project(project_id)

    if not success:
        return json_error(f"Project does not exist or deletion failed: {project_id}", status=404)

    return json_success(message=f"Project deleted: {project_id}")


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
@handle_api_errors
def reset_project(project_id: str):
    """
    Reset project status (for rebuilding graph)
    """
    if not validate_project_id(project_id):
        return json_error("Invalid project_id format", status=400)

    project = ProjectManager.get_project(project_id)

    if not project:
        return json_error(f"Project does not exist: {project_id}", status=404)

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
        return json_error("Please provide simulation requirement description (simulation_requirement)", status=400)

    # Get uploaded files
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or all(not f.filename for f in uploaded_files):
        return json_error("Please upload at least one document file", status=400)

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
        return json_error("No documents successfully processed. Please check file format", status=400)

    # Save extracted text
    project.total_text_length = len(all_text)
    ProjectManager.save_extracted_text(project.project_id, all_text)
    logger.info(f"Text extraction completed, total {len(all_text)} characters")

    # Generate ontology
    logger.info("Calling LLM to generate ontology definition...")
    generator = OntologyGenerator()
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
    ProjectManager.save_project(project)
    logger.info(f"=== Ontology generation completed === Project ID: {project.project_id}")

    return json_success({
        "project_id": project.project_id,
        "project_name": project.name,
        "ontology": project.ontology,
        "analysis_summary": project.analysis_summary,
        "files": project.files,
        "total_text_length": project.total_text_length
    })


# ============== Interface 2: Build Graph ==============

@graph_bp.route('/build', methods=['POST'])
@handle_api_errors(log_prefix="Graph build initiation failed")
def build_graph():
    """
    Interface 2: Build graph based on project_id
    """
    logger.info("=== Starting graph build ===")

    # Parse request
    data = request.get_json() or {}
    project_id = data.get('project_id')
    logger.debug(f"Request parameters: project_id={project_id}")

    if not project_id:
        return json_error("Please provide project_id", status=400)

    if not validate_project_id(project_id):
        return json_error("Invalid project_id format", status=400)

    # Get project
    project = ProjectManager.get_project(project_id)
    if not project:
        return json_error(f"Project does not exist: {project_id}", status=404)

    # Check project status
    force = data.get('force', False)  # Force rebuild

    if project.status == ProjectStatus.CREATED:
        return json_error("Project has not generated ontology yet. Please call /ontology/generate first", status=400)

    if project.status == ProjectStatus.GRAPH_BUILDING and not force:
        return json_error(
            "Graph is being built. Do not submit repeatedly. To force rebuild, add force: true",
            status=400,
            task_id=project.graph_build_task_id
        )

    # If force rebuild, reset status
    if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.graph_id = None
        project.graph_build_task_id = None
        project.error = None

    # Get configuration
    graph_name = data.get('graph_name', project.name or 'Agora Graph')
    chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
    chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

    # Update project configuration
    project.chunk_size = chunk_size
    project.chunk_overlap = chunk_overlap

    # Get extracted text
    text = ProjectManager.get_extracted_text(project_id)
    if not text:
        return json_error("Extracted text not found", status=400)

    # Get ontology
    ontology = project.ontology
    if not ontology:
        return json_error("Ontology definition not found", status=400)

    # Get storage in request context (background thread cannot access current_app)
    storage = _get_storage()

    # Create async task
    task_manager = TaskManager()
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

    # Update project status
    project.status = ProjectStatus.GRAPH_BUILDING
    project.graph_build_task_id = task_id
    ProjectManager.save_project(project)

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

            # Create graph builder service (storage passed from outer closure)
            builder = GraphBuilderService(storage=storage)

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

            # Add text (progress_callback signature is (msg, progress_ratio))
            def add_progress_callback(msg, progress_ratio):
                progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                task_manager.update_task(
                    task_id,
                    message=msg,
                    progress=progress
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
                progress_callback=add_progress_callback
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
        return json_error("Invalid task_id format", status=400)

    task = TaskManager().get_task(task_id)

    if not task:
        return json_error(f"Task does not exist: {task_id}", status=404)

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
    Get graph data (nodes and edges)
    """
    if not validate_graph_id(graph_id):
        return json_error("Invalid graph_id format", status=400)

    storage = _get_storage()
    builder = GraphBuilderService(storage=storage)
    graph_data = builder.get_graph_data(graph_id)

    return json_success(graph_data)


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
@handle_api_errors
def delete_graph(graph_id: str):
    """
    Delete graph
    """
    if not validate_graph_id(graph_id):
        return json_error("Invalid graph_id format", status=400)

    storage = _get_storage()
    builder = GraphBuilderService(storage=storage)
    builder.delete_graph(graph_id)

    return json_success(message=f"Graph deleted: {graph_id}")
