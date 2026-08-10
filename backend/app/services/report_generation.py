"""
Service for generating simulation reports.
"""

import uuid
from flask import current_app

from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.report_agent.output_contract import is_deliverable_report_status
from ..services.run_lifecycle import RunLifecycle
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
    def start_generation(cls, simulation_id, report_mode, force_regenerate, llm_model_override, llm_runtime, llm_profile_id=None, ai_model_ref=None, budget=None):
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            raise ValueError(ApiErrorCode.NOT_FOUND)

        if cls.can_reuse_existing_report(
            force_regenerate,
            llm_model_override,
            llm_runtime.enabled or ai_model_ref is not None,
        ):
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
            and ai_model_ref is None
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
        # Issue #1183: Anlage-Fenster (create_run bis enqueue) hinter
        # RunLifecycle — jeder Abbruch bis zur Übergabe an den Job-Worker
        # markiert Run und Task als failed statt sie pending zu verwaisen.
        with RunLifecycle.begin(
            run_registry,
            "report_generate",
            report_id,
            failure_message="Report generation start failed: {exc_type}",
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
        ) as lifecycle:
            run_record = lifecycle.record
            task_id = task_manager.create_task(
                task_type="report_generate",
                metadata={"simulation_id": simulation_id, "graph_id": graph_id, "report_id": report_id, "run_id": run_record["run_id"]}
            )
            lifecycle.attach_task(task_manager, task_id)
            cls._wire_and_enqueue_generation(
                simulation_requirement=simulation_requirement,
                task_manager=task_manager,
                task_id=task_id,
                simulation_id=simulation_id,
                report_id=report_id,
                report_mode=report_mode,
                run_record=run_record,
                graph_id=graph_id,
                state=state,
                llm_model_override=llm_model_override,
                llm_runtime=llm_runtime,
                llm_profile_id=llm_profile_id,
                ai_model_ref=ai_model_ref,
                budget=budget,
            )

        return {
            "simulation_id": simulation_id,
            "report_id": report_id,
            "task_id": task_id,
            "run_id": run_record["run_id"],
            "status": "generating",
            "message": "Report generation task started. Query progress via /api/report/generate/status",
            "already_generated": False
        }

    @classmethod
    def _wire_and_enqueue_generation(
        cls,
        *,
        simulation_requirement,
        task_manager,
        task_id,
        simulation_id,
        report_id,
        report_mode,
        run_record,
        graph_id,
        state,
        llm_model_override,
        llm_runtime,
        llm_profile_id,
        ai_model_ref,
        budget,
    ):
        """Routing, Budget und Worker-Closure des Reports verdrahten.

        Läuft vollständig innerhalb des RunLifecycle-Fensters von
        :meth:`start_generation` — jede Exception hier markiert Run und
        Task als failed (#1183).
        """
        # Issue #764: Budget des Simulationslaufs auf den Report-Run vererben.
        try:
            from .run_budget import inherit_budget_from_simulation

            inherit_budget_from_simulation(run_record["run_id"], simulation_id)
        except Exception:  # noqa: BLE001 — Vererbung ist best-effort
            logger.debug("budget inheritance skipped", exc_info=True)
        # Explizit mitgesendetes Budget schlägt die Vererbung (#764).
        if budget is not None:
            from .run_budget import set_run_budget_config

            set_run_budget_config(run_record["run_id"], budget)
        # Single Source of Truth: das (ggf. aus dem Projekt geerbte) Profil ist nur
        # ein Eingang zur Routenerzeugung — es darf keinen zweiten Client-Pfad neben
        # der gelockten Route öffnen. seed → resolve → lock bestimmen die Route; der
        # Client wird ausschließlich aus dieser Route gebaut (Issue #817).
        seed_run_stage_routing(
            run_record["run_id"],
            "report_generation",
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
            llm_profile_id=llm_profile_id,
            ai_model_ref=ai_model_ref,
        )
        route_router = StageModelRouter(run_record["run_id"])
        resolved_route = route_router.resolve("report_generation")
        route_router.lock_stage("report_generation", resolved_route)

        # Model-Attribution und Run-Metadaten stammen aus der gelockten Route (SSoT),
        # nicht aus den rohen Request-Feldern — sonst zeigte llm_model bei Profil-/
        # AiModelRef-Auswahl None an, während die Route ein anderes Modell trägt
        # (Issue #817). Nur Secret-freie Metadaten.
        run_registry.update_run(
            run_record["run_id"],
            metadata={
                "llm_model": resolved_route.model,
                "llm_provider": {
                    "provider_id": resolved_route.provider_id,
                    "base_url": resolved_route.base_url_sanitized,
                },
            },
        )

        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            raise RuntimeError("GraphStorage not initialized — check Neo4j connection")

        shared_llm_client = LLMClient.from_route(
            resolved_route,
            secret_resolver=SecretResolver(),
            api_key_override=resolve_route_api_key(resolved_route, llm_runtime),
            run_id=run_record["run_id"],
        )
        logger.info(
            "Report LLM route locked provider_id=%s model=%s "
            "[simulation_id=%s, report_id=%s, project_id=%s, run_id=%s, llm_profile_id=%s]",
            resolved_route.provider_id,
            resolved_route.model,
            simulation_id,
            report_id,
            state.project_id,
            run_record["run_id"],
            llm_profile_id,
        )
        graph_tools = GraphToolsService(storage=storage, llm_client=shared_llm_client)

        def run_generate():
            from .run_budget import BudgetExceededError, mark_budget_abort

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
                # Issue #1006: INCOMPLETE ist ein Teilergebnis, kein Fehlschlag.
                # Der Report existiert, ist lesbar und exportierbar — nur
                # einzelne Claims wurden lokal abgestuft oder eine Section ist
                # fehlgeschlagen. Ihn in den failed-Zweig zu schicken hiesse:
                # der Nutzer liest "Report generation failed", obwohl das
                # Ergebnis vorliegt, und bekommt ein Resume angeboten, das
                # bereits fertige Sections ohnehin ueberspringt. Genau diese
                # Zustellungsluecke haette den Fix aus #1006 in der Oberflaeche
                # wirkungslos gemacht.
                if is_deliverable_report_status(report.status):
                    _incomplete = report.status == ReportStatus.INCOMPLETE
                    run_registry.update_run(
                        run_record["run_id"],
                        status="completed",
                        progress=100,
                        message=(
                            "Report generated with degraded claims"
                            if _incomplete
                            else "Report generated"
                        ),
                        artifacts=ArtifactLocator.existing_paths({
                            "report": ArtifactLocator.report_artifacts(report_id),
                            "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
                        }),
                        resume_capability={"available": False, "action": None, "label": None},
                    )
                    task_manager.complete_task(task_id, result={"report_id": report.report_id, "simulation_id": simulation_id, "status": report.status.value})
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
            except BudgetExceededError as exc:
                # Budgetabbruch (#764): Teilresultate bleiben erhalten, Status
                # "stopped" + termination_reason statt technischem "failed".
                logger.warning(
                    "Report generation budget-aborted (run_id=%s, report_id=%s): %s",
                    run_record["run_id"], report_id, exc,
                )
                # Reihenfolge ist bindend (Issue #978, gleiche Falle wie #841 in
                # api/simulation_prepare.py): fail_task() spiegelt den Task per
                # TaskManager.update_task -> RunRegistry.sync_task auf den Run
                # zurueck und setzt dabei status="failed" + message="Task failed".
                # Liefe es nach mark_budget_abort(), wuerde es den soeben
                # gesetzten "stopped"-Status samt Budgetbegruendung wieder
                # ueberschreiben — genau das Symptom im E2E-Smoke
                # frontend/tests/e2e/run-budget.spec.ts. Der detaillierte
                # Run-Update muss deshalb zuletzt laufen.
                task_manager.fail_task(task_id, str(exc))
                mark_budget_abort(
                    run_record["run_id"], exc.dimension, exc.observed, exc.threshold
                )
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
