"""Background-job helpers for simulation preparation."""

from __future__ import annotations

from typing import Any, Callable

from ..services.degradation_collector import DegradationCollector
from ..services.simulation_manager import SimulationStatus
from .simulation_common import logger
from .simulation_prepare_contracts import PrepareInputs

def build_progress_callback(task_manager, task_id: str) -> "Callable[..., None]":
    """Fortschritts-Callback über die vier Vorbereitungs-Stages."""
    stage_details: "dict[str, dict[str, Any]]" = {}

    def progress_callback(stage, progress, message, **kwargs):
        stage_weights = {
            "reading": (0, 20),
            "generating_profiles": (20, 70),
            "generating_config": (70, 90),
            "copying_scripts": (90, 100),
        }

        start, end = stage_weights.get(stage, (0, 100))
        current_progress = int(start + (end - start) * progress / 100)

        stage_names = {
            "reading": "Read knowledge graph entities",
            "generating_profiles": "GenerateAgentpersona",
            "generating_config": "Generate simulation configuration",
            "copying_scripts": "Prepare simulation scripts",
        }

        stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
        total_stages = len(stage_weights)

        stage_details[stage] = {
            "stage_name": stage_names.get(stage, stage),
            "stage_progress": progress,
            "current": kwargs.get("current", 0),
            "total": kwargs.get("total", 0),
            "item_name": kwargs.get("item_name", ""),
        }

        detail = stage_details[stage]
        progress_detail_data = {
            "current_stage": stage,
            "current_stage_name": stage_names.get(stage, stage),
            "stage_index": stage_index,
            "total_stages": total_stages,
            "stage_progress": progress,
            "current_item": detail["current"],
            "total_items": detail["total"],
            "item_description": message,
        }

        if detail["total"] > 0:
            detailed_message = (
                f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                f"{detail['current']}/{detail['total']} - {message}"
            )
        else:
            detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"

        task_manager.update_task(
            task_id,
            progress=current_progress,
            message=detailed_message,
            progress_detail=progress_detail_data,
        )

    return progress_callback


def make_prepare_job(
    *,
    manager,
    task_manager,
    task_id: str,
    simulation_id: str,
    inputs: PrepareInputs,
    storage,
    llm_model: str,
    effective_llm_runtime,
    run_record: "dict[str, Any]",
    progress_callback_factory: "Callable[..., Callable[..., None]]",
    finish_cancelled_prepare_run: "Callable[..., None]",
) -> "Callable[[], None]":
    """Phase 9 — den Hintergrund-Job bauen, der die Vorbereitung ausführt."""
    from ..models.task import TaskStatus
    from ..services.prepare_service import PrepareCancelledError
    from ..services.run_budget import BudgetExceededError, mark_budget_abort

    def run_prepare() -> None:
        # Issue #1034: Der Collector gehört dem Task, nicht dem Service —
        # gleiches Muster wie im Graph-Build (``services/graph_build.py``).
        # Nur so überlebt ein stiller Teilausfall bis ins Task-Ergebnis;
        # ein im Service erzeugter Sammler wäre nach der Rückkehr weg.
        degradations = DegradationCollector()
        try:
            task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=0,
                message="Start preparing simulation environment...",
            )

            result_state = manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=inputs.simulation_requirement,
                document_text=inputs.document_text,
                defined_entity_types=inputs.entity_types,
                use_llm_for_profiles=inputs.use_llm_for_profiles,
                progress_callback=progress_callback_factory(task_manager, task_id),
                parallel_profile_count=inputs.parallel_profile_count,
                storage=storage,
                llm_model=llm_model,
                llm_runtime=effective_llm_runtime,
                language=inputs.agent_language_override,
                max_agents=inputs.max_agents,
                quota_plan=inputs.quota_plan,
                # Budget-Enforcement (#984): dieselbe persistierte run_id wie
                # der Prepare-Run — Persona- und Config-Generierung bauen ihre
                # LLM-Clients damit run-gebunden statt budgetfrei.
                run_id=run_record["run_id"],
                degradations=degradations,
            )

            task_manager.complete_task(
                task_id,
                result={
                    **result_state.to_simple_dict(),
                    # Leere Liste heißt „nichts ist still ausgefallen“.
                    "degradations": degradations.report().model_dump(mode="json"),
                },
            )

        except PrepareCancelledError:
            # Issue B2: Nutzerabbruch über POST /api/runs/<id>/cancel.
            # Reihenfolge bindend (gleiche Falle wie #978/#841): complete_task()
            # zuerst — sync_task() setzt sonst generisch "completed" — dann der
            # detaillierte Run-Update mit status="stopped" zuletzt, sonst
            # überschreibt sync_task() ihn wieder.
            logger.info(
                "Simulation prepare cancelled by user (run_id=%s, simulation_id=%s)",
                run_record["run_id"], simulation_id,
            )
            task_manager.complete_task(
                task_id,
                result={
                    "simulation_id": simulation_id,
                    "status": "cancelled",
                    "cancelled": True,
                    "degradations": degradations.report().model_dump(mode="json"),
                },
            )
            finish_cancelled_prepare_run(
                run_record["run_id"],
                simulation_id=simulation_id,
            )
        except BudgetExceededError as exc:
            # Budgetabbruch (#984): Teilresultate bleiben erhalten, der Run
            # endet "stopped" + termination_reason statt technischem "failed".
            # Reihenfolge bindend (#978/#841): fail_task() zuerst — sync_task
            # setzt generisch "failed" —, mark_budget_abort() zuletzt.
            logger.warning(
                "Simulation prepare budget-aborted (run_id=%s, simulation_id=%s): %s",
                run_record["run_id"], simulation_id, exc,
            )
            task_manager.fail_task(task_id, str(exc))
            task_manager.update_task(
                task_id,
                result={"degradations": degradations.report().model_dump(mode="json")},
            )
            mark_budget_abort(
                run_record["run_id"], exc.dimension, exc.observed, exc.threshold
            )
            failed_state = manager.get_simulation(simulation_id)
            if failed_state:
                failed_state.error = str(exc)
                manager._set_status(failed_state, SimulationStatus.FAILED)
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error(f"Failed to prepare simulation: {str(exc)}")
            task_manager.fail_task(task_id, str(exc))
            # Auch der Fehlerfall trägt die Befunde: sie nennen oft die
            # Ursache, die die Exception-Message selbst nicht mehr kennt
            # (etwa "alle Entitäten waren ungeeignet" statt "kein Graph").
            task_manager.update_task(
                task_id,
                result={"degradations": degradations.report().model_dump(mode="json")},
            )

            failed_state = manager.get_simulation(simulation_id)
            if failed_state:
                failed_state.error = str(exc)
                manager._set_status(failed_state, SimulationStatus.FAILED)
        finally:
            # Review-Finding (PR #1371, Befund 7): ohne diesen finally-Block
            # räumte nur der PrepareCancelledError-Zweig das Flag über
            # _finish_cancelled_prepare_run auf. Kommt die Cancel-Anfrage
            # NACH dem letzten Checkpoint (z. B. während _phase_generate_config,
            # die keinen eigenen Check hat), läuft der Job normal zu Ende —
            # die Nachricht springt für den Nutzer von "Cancel requested —
            # finishing current stage" auf "completed", und das
            # threading.Event bliebe für die restliche Prozesslaufzeit im
            # globalen Dict von cancel_flag.py liegen (kleines, aber echtes
            # Leck über viele Läufe). ``clear_cancel`` ist idempotent, ein
            # zweiter Aufruf im Cancel-Zweig oben ist folgenlos.
            from ..services.sim.cancel_flag import clear_cancel, is_cancel_requested

            if is_cancel_requested(run_record["run_id"]):
                logger.info(
                    "Simulation prepare: Cancel-Flag war gesetzt, aber der "
                    "letzte Checkpoint war bereits passiert (run_id=%s, "
                    "simulation_id=%s) — Abbruch kam zu spät, Endzustand "
                    "bleibt wie oben bestimmt.",
                    run_record["run_id"], simulation_id,
                )
            clear_cancel(run_record["run_id"])

    return run_prepare
