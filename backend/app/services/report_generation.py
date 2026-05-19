"""
Service for generating simulation reports.
"""

import uuid
from flask import current_app

from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.run_registry import RunRegistry
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..services.graph_tools import GraphToolsService
from ..services.secret_resolver import SecretResolver
from ..services.llm_routing_seed import resolve_route_api_key, seed_run_stage_routing
from ..services.stage_model_router import StageModelRouter
from ..utils.artifact_locator import ArtifactLocator
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..utils.api_errors import ApiErrorCode

logger = get_logger(__name__)
run_registry = RunRegistry()


class ReportGenerationService:
    @staticmethod
    def can_reuse_existing_report(
        force_regenerate: bool,
        llm_model_override: str | None,
        runtime_provider_override: bool = False,
    ) -> bool:
        """Reuse only when the caller did not request concrete LLM runtime settings."""
        return not force_regenerate and not llm_model_override and not runtime_provider_override

    @classmethod
    def start_generation(cls, simulation_id, report_mode, force_regenerate, llm_model_override, llm_runtime, llm_profile_id=None):
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            raise ValueError(ApiErrorCode.NOT_FOUND)

        if cls.can_reuse_existing_report(force_regenerate, llm_model_override, llm_runtime.enabled):
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return {
                    "simulation_id": simulation_id,
                    "report_id": existing_report.report_id,
                    "status": "completed",
                    "message": "Report already exists",
                    "already_generated": True
                }

        project = ProjectManager.get_project(state.project_id)
        if not project:
            raise ValueError(ApiErrorCode.NOT_FOUND)

        _resolved_profile = None
        if llm_profile_id:
            from ..services.llm_profiles_store import get_llm_profiles_store
            _resolved_profile = get_llm_profiles_store().get(llm_profile_id, include_api_key=True)
            if _resolved_profile is None:
                raise ValueError(ApiErrorCode.NOT_FOUND)

        if (
            _resolved_profile is None
            and not llm_profile_id
            and (not llm_model_override or llm_model_override.lower() == 'default')
            and getattr(project, 'llm_profile_id', None)
        ):
            from ..services.llm_profiles_store import get_llm_profiles_store
            llm_profile_id = project.llm_profile_id
            _resolved_profile = get_llm_profiles_store().get(llm_profile_id, include_api_key=True)
            if _resolved_profile is None:
                logger.warning(
                    "Project %s referenziert unbekanntes LLM-Profil %r — Fallback auf Stage-Routing",
                    state.project_id, llm_profile_id,
                )
                llm_profile_id = None

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            raise ValueError("Missing graph ID, please ensure graph is built")

        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            raise ValueError("Missing simulation requirement description")

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

        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            raise RuntimeError("GraphStorage not initialized — check Neo4j connection")

        if _resolved_profile is not None:
            from ..utils.llm_client import build_client_from_profile as _build_from_profile
            shared_llm_client = _build_from_profile(_resolved_profile, run_id=run_record["run_id"])
            logger.info(
                "Using LLM profile %r for report (provider=%s, model=%s) [simulation_id=%s, report_id=%s, project_id=%s, run_id=%s]",
                llm_profile_id,
                _resolved_profile.provider,
                _resolved_profile.model_name,
                simulation_id,
                report_id,
                state.project_id,
                run_record["run_id"]
            )
        else:
            shared_llm_client = LLMClient.from_route(
                resolved_route,
                secret_resolver=SecretResolver(),
                api_key_override=resolve_route_api_key(resolved_route, llm_runtime),
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
            except Exception:
                logger.exception("Report generation failed (run_id=%s, report_id=%s)", run_record["run_id"], report_id)
                import traceback
                error_msg = traceback.format_exc()
                run_registry.update_run(
                    run_record["run_id"],
                    status="failed",
                    message=error_msg,
                    error=error_msg,
                    artifacts=ArtifactLocator.existing_paths({
                        "report": ArtifactLocator.report_artifacts(report_id),
                        "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
                    }),
                )
                task_manager.fail_task(task_id, error_msg)

        from ..jobs import enqueue
        enqueue("report_generate", run_generate)

        return {
            "simulation_id": simulation_id,
            "report_id": report_id,
            "task_id": task_id,
            "run_id": run_record["run_id"],
            "status": "generating",
            "message": "Report generation task started. Query progress via /api/report/generate/status",
            "already_generated": False
        }
