"""
Service for building graphs and generating ontologies.
"""

import time

from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.llm_routing_seed import resolve_route_api_key, seed_run_stage_routing
from ..services.stage_model_router import StageModelRouter
from ..services.text_processor import TextProcessor
from ..storage.ner_extractor import NERExtractor
from ..utils.artifact_locator import ArtifactLocator
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus
from ..services.run_registry import RunRegistry
from ..services.secret_resolver import SecretResolver
from ..utils.api_errors import ApiErrorCode

logger = get_logger('agora.graph_build_service')
run_registry = RunRegistry()


class GraphBuildService:
    @classmethod
    def generate_ontology(
        cls,
        project_id,
        simulation_requirement,
        document_texts,
        llm_model_override=None,
        llm_runtime=None,
        llm_profile_id=None,
        additional_context=None
    ):
        """
        Generate an ontology for a project from its documents and simulation requirements.
        
        Parameters:
            project_id: Identifier of the project to update.
            simulation_requirement: Requirements that guide ontology generation.
            document_texts: Source documents used to generate the ontology.
            llm_model_override: Optional model override for the generation run.
            llm_runtime: Optional runtime configuration for the language model.
            llm_profile_id: Optional language model profile identifier recorded on the project.
            additional_context: Optional context supplied to the ontology generator.
        
        Returns:
            The project updated with the generated ontology and analysis summary.
        
        Raises:
            ValueError: If the project does not exist.
        """
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(ApiErrorCode.NOT_FOUND)

        run_record = run_registry.create_run(
            run_type="ontology_generate",
            entity_id=project.project_id,
            status="processing",
            progress=0,
            message="Ontology generation started",
            linked_ids={"project_id": project.project_id},
        )
        run_id = run_record["run_id"]
        for stage_id in ("document_ingest", "ontology_generation"):
            seed_run_stage_routing(
                run_id,
                stage_id,
                llm_model_override=llm_model_override,
                llm_runtime=llm_runtime,
                llm_profile_id=llm_profile_id,
            )
        route_router = StageModelRouter(run_id)
        ingest_route = route_router.resolve("document_ingest")
        route_router.lock_stage("document_ingest", ingest_route)
        ontology_route = route_router.resolve("ontology_generation")
        route_router.lock_stage("ontology_generation", ontology_route)

        # The locked ontology route is authoritative; profile IDs are metadata only.
        llm_client = LLMClient.from_route(
            ontology_route,
            secret_resolver=SecretResolver(),
            api_key_override=resolve_route_api_key(ontology_route, llm_runtime),
            run_id=run_id,
        )
        logger.info(
            "Calling LLM to generate ontology definition (model=%s, provider=%s) [project_id=%s, run_id=%s]",
            llm_client.model,
            ontology_route.provider_id,
            project_id,
            run_id
        )

        generator = OntologyGenerator(llm_client=llm_client)
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context
        )

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.llm_model = llm_model_override
        project.llm_provider = llm_runtime.redacted_metadata() if llm_runtime else None
        project.llm_profile_id = llm_profile_id
        ProjectManager.save_project(project)

        run_registry.update_run(
            run_id,
            status="completed",
            progress=100,
            message="Ontology generation completed",
            linked_ids={"project_id": project.project_id},
        )
        return project

    @classmethod
    def build_graph(
        cls,
        project_id,
        graph_name,
        llm_model_override=None,
        llm_runtime=None,
        llm_profile_id=None,
        force=False,
        chunk_size=None,
        chunk_overlap=None,
        container=None
    ):
        """
        Queue a graph build for a project using its extracted text and ontology.
        
        Parameters:
            project_id: Identifier of the project to build.
            graph_name: Name assigned to the new graph.
            llm_model_override: Optional model override for graph processing.
            llm_runtime: Optional runtime configuration for the language model.
            llm_profile_id: Optional language model profile identifier.
            force: Whether to restart a graph build already in progress.
            chunk_size: Optional text chunk size.
            chunk_overlap: Optional overlap between consecutive text chunks.
            container: Service container used to create the graph builder.
        
        Returns:
            A tuple containing the task identifier and run identifier.
        
        Raises:
            ValueError: If the project, extracted text, or ontology is missing, or if
                the project has not completed ontology generation.
            RuntimeError: If a graph build is already in progress and `force` is false.
        """
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(ApiErrorCode.NOT_FOUND)

        # State check
        if project.status == ProjectStatus.CREATED:
            raise ValueError(ApiErrorCode.ONTOLOGY_MISSING)

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            raise RuntimeError(ApiErrorCode.GRAPH_BUILD_IN_PROGRESS)

        if force:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        effective_profile_id = llm_profile_id or project.llm_profile_id
        if llm_profile_id is not None:
            project.llm_profile_id = llm_profile_id

        # Inputs
        chunk_size = chunk_size or project.chunk_size or Config.DEFAULT_CHUNK_SIZE
        chunk_overlap = chunk_overlap or project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            raise ValueError("Extracted text not found")

        ontology = project.ontology
        if not ontology:
            raise ValueError("Ontology definition not found")

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
            metadata={"project_id": project_id, "run_id": run_record["run_id"]}
        )

        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        seed_run_stage_routing(
            run_record["run_id"],
            "graph_build",
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
            llm_profile_id=effective_profile_id,
        )
        route_router = StageModelRouter(run_record["run_id"])
        resolved_route = route_router.resolve("graph_build")
        route_router.lock_stage("graph_build", resolved_route)

        # The locked route is authoritative; legacy profile IDs must not replace it.
        ner_llm_client = LLMClient.from_route(
            resolved_route,
            secret_resolver=SecretResolver(),
            api_key_override=resolve_route_api_key(resolved_route, llm_runtime),
            run_id=run_record["run_id"],
        )
        logger.info(
            "Build-Pfad nutzt Route-Snapshot: model=%s provider=%s [project_id=%s, run_id=%s]",
            ner_llm_client.model,
            resolved_route.provider_id,
            project_id,
            run_record["run_id"]
        )
        ner_override = NERExtractor(llm_client=ner_llm_client)

        def build_task():
            """
            Builds the project's graph and records its completion or failure state.
            
            On failure, marks the project, task, and run as failed and attempts to clean up any
            partially created graph.
            """
            build_logger = get_logger('agora.build')
            graph_id = None
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Initializing graph build service...")
                builder = container.graph_builder()

                task_manager.update_task(task_id, message="Chunking text...", progress=5)
                chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)

                task_manager.update_task(task_id, message="Creating graph...", progress=10)
                graph_id = builder.create_graph(name=graph_name)

                run_registry.update_run(
                    run_record["run_id"],
                    entity_id=project_id,
                    linked_ids={"graph_id": graph_id, "project_id": project_id, "task_id": task_id},
                    message=f"Graph created: {graph_id}",
                )

                task_manager.update_task(task_id, message="Setting ontology definition...", progress=15)
                builder.set_ontology(graph_id, ontology)

                def add_progress_callback(msg, progress_ratio, completed, total):
                    progress = 15 + int(progress_ratio * 40)
                    task_manager.update_task(
                        task_id, message=msg, progress=progress,
                        progress_detail={"batch_count": completed, "total_batches": total, "batch_at": time.time()}
                    )

                builder.add_text_batches(graph_id, chunks, batch_size=3, progress_callback=add_progress_callback, ner_extractor=ner_override)

                task_manager.update_task(task_id, message="Retrieving graph data...", progress=95)
                graph_data = builder.get_graph_data(graph_id)

                builder.mark_graph_completed(graph_id)
                project.graph_id = graph_id
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id, status=TaskStatus.COMPLETED, message="Graph build completed", progress=100,
                    result={"project_id": project_id, "graph_id": graph_id, "node_count": graph_data.get("node_count", 0), "edge_count": graph_data.get("edge_count", 0)}
                )
                run_registry.update_run(run_record["run_id"], status="completed", progress=100, message="Graph build completed")

            except Exception as exc:
                build_logger.exception("Graph build failed [project_id=%s, run_id=%s]", project_id, run_record["run_id"])
                if graph_id is not None:
                    try:
                        builder.delete_graph(graph_id)
                    except Exception:  # noqa: BLE001 — best-effort cleanup; primary exception already propagated
                        try:
                            builder.mark_graph_failed(graph_id, reason=str(exc))
                        except Exception as err:  # noqa: BLE001 — best-effort cleanup; primary exception already propagated
                            logger.debug("graph_build: mark_graph_failed also failed, ignoring: %s", err)

                project.status = ProjectStatus.FAILED
                project.error = str(exc)
                ProjectManager.save_project(project)

                import traceback
                task_manager.update_task(task_id, status=TaskStatus.FAILED, message=f"Build failed: {str(exc)}", error=traceback.format_exc())
                run_registry.update_run(run_record["run_id"], status="failed", message=str(exc), error=str(exc))

        from ..jobs import enqueue
        enqueue("graph_build", build_task)
        return task_id, run_record["run_id"]
