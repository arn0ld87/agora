"""
Preparation-related simulation API routes split from the main module.
"""

import os
import threading
import traceback

from flask import jsonify, request

from . import simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.entity_reader import EntityReader
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..utils.validation import validate_simulation_id, validate_task_id
from .simulation_common import (
    get_simulation_storage,
    logger,
    run_registry,
    simulation_run_artifacts as _simulation_run_artifacts,
)


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Check whether a simulation already has all preparation artifacts.
    """
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(simulation_dir):
        return False, {"reason": "Simulation directory does not exist"}

    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv",
    ]

    existing_files = []
    missing_files = []
    for filename in required_files:
        file_path = os.path.join(simulation_dir, filename)
        if os.path.exists(file_path):
            existing_files.append(filename)
        else:
            missing_files.append(filename)

    if missing_files:
        return False, {
            "reason": "Missing required files",
            "missing_files": missing_files,
            "existing_files": existing_files,
        }

    state_file = os.path.join(simulation_dir, "state.json")
    try:
        import json

        with open(state_file, 'r', encoding='utf-8') as handle:
            state_data = json.load(handle)

        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        logger.debug(
            f"Detect simulation preparation status: {simulation_id}, status={status}, config_generated={config_generated}"
        )

        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as handle:
                    profiles_data = json.load(handle)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0

            if status == "preparing":
                try:
                    from datetime import datetime

                    state_data["status"] = "ready"
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as handle:
                        json.dump(state_data, handle, ensure_ascii=False, indent=2)
                    logger.info(f"Auto update simulation status: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as exc:
                    logger.warning(f"Failed to auto update status: {exc}")

            logger.info(
                f"Simulation {simulation_id} Detection result: HasPreparation complete (status={status}, config_generated={config_generated})"
            )
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files,
            }

        logger.warning(
            f"Simulation {simulation_id} Detection result: Has notPreparation complete (status={status}, config_generated={config_generated})"
        )
        return False, {
            "reason": (
                "Status not in prepared list or config_generated is false: "
                f"status={status}, config_generated={config_generated}"
            ),
            "status": status,
            "config_generated": config_generated,
        }

    except Exception as exc:
        return False, {"reason": f"Failed to read state file: {str(exc)}"}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """Prepare a simulation environment as an async task."""
    from ..models.task import TaskManager, TaskStatus

    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        if not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}",
            }), 404

        force_regenerate = data.get('force_regenerate', False)
        logger.info(
            f"Start processing /prepare Request: simulation_id={simulation_id}, force_regenerate={force_regenerate}",
            extra={'simulation_id': simulation_id},
        )

        if not force_regenerate:
            logger.debug(f"Check simulation {simulation_id} Is preparation complete...")
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(f"Check result: is_prepared={is_prepared}, prepare_info={prepare_info}")
            if is_prepared:
                logger.info(f"Simulation {simulation_id} has preparation complete, no need to regenerate")
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": "Preparation already completed，No need to repeatGenerate",
                        "already_prepared": True,
                        "prepare_info": prepare_info,
                    },
                })
            logger.info(f"Simulation {simulation_id} has no preparation complete, preparing now")

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project does not exist: {state.project_id}",
            }), 404

        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Project missing simulation requirement description (simulation_requirement)",
            }), 400

        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)

        max_agents_raw = data.get('max_agents')
        try:
            max_agents = int(max_agents_raw) if max_agents_raw not in (None, '', 0) else None
        except (TypeError, ValueError):
            max_agents = None

        llm_model_override = (data.get('llm_model') or '').strip() or None
        agent_language_override = (data.get('language') or '').strip().lower() or None
        if agent_language_override and agent_language_override not in ('de', 'en'):
            agent_language_override = None

        storage = get_simulation_storage()

        try:
            logger.info(f"Synchronously get entity count: graph_id={state.graph_id}")
            reader = EntityReader(storage)
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False,
            )
            preview_count = filtered_preview.filtered_count
            if max_agents is not None and max_agents > 0:
                preview_count = min(preview_count, max_agents)
            state.entities_count = preview_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(
                f"Expected entity count: {filtered_preview.filtered_count}, [type][model]: {filtered_preview.entity_types}"
            )
        except Exception as exc:
            logger.warning(f"Synchronously get entity countFailed（Will retry in background task）: {exc}")

        task_manager = TaskManager()
        run_record = run_registry.create_run(
            run_type="simulation_prepare",
            entity_id=simulation_id,
            status="pending",
            progress=0,
            message="Simulation preparation queued",
            linked_ids={
                "simulation_id": simulation_id,
                "project_id": state.project_id,
            },
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
            branch_label=state.branch_name,
            metadata={
                "project_id": state.project_id,
                "graph_id": state.graph_id,
                "source_simulation_id": state.source_simulation_id,
                "root_simulation_id": state.root_simulation_id,
                "branch_name": state.branch_name,
                "branch_depth": state.branch_depth,
            },
        )
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id,
                "run_id": run_record["run_id"],
            },
        )

        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)

        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="Start preparing simulation environment...",
                )

                stage_details = {}

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

                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count,
                    storage=storage,
                    llm_model=llm_model_override,
                    language=agent_language_override,
                    max_agents=max_agents,
                )

                task_manager.complete_task(task_id, result=result_state.to_simple_dict())

            except Exception as exc:
                logger.error(f"Failed to prepare simulation: {str(exc)}")
                task_manager.fail_task(task_id, str(exc))

                failed_state = manager.get_simulation(simulation_id)
                if failed_state:
                    failed_state.status = SimulationStatus.FAILED
                    failed_state.error = str(exc)
                    manager._save_simulation_state(failed_state)

        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "run_id": run_record["run_id"],
                "status": "preparing",
                "message": "Preparation task started，Please via /api/simulation/prepare/status Query progress",
                "already_prepared": False,
                "expected_entities_count": state.entities_count,
                "entity_types": state.entity_types,
            },
        })

    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    except Exception as exc:
        logger.error(f"Failed to start preparation task: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """Query preparation progress by task_id or simulation_id."""
    from ..models.task import TaskManager

    try:
        data = request.get_json() or {}
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')

        if task_id and not validate_task_id(task_id):
            return jsonify({"success": False, "error": "Invalid task_id format"}), 400
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "Preparation already completed",
                        "already_prepared": True,
                        "prepare_info": prepare_info,
                    },
                })

        if not task_id:
            if simulation_id:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": "Preparation not started yet, please call /api/simulation/prepare",
                        "already_prepared": False,
                    },
                })
            return jsonify({
                "success": False,
                "error": "Please provide task_id Or simulation_id",
            }), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        if not task:
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "Task complete（PrepareWork already exists）",
                            "already_prepared": True,
                            "prepare_info": prepare_info,
                        },
                    })

            return jsonify({
                "success": False,
                "error": f"Task does not exist: {task_id}",
            }), 404

        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        return jsonify({"success": True, "data": task_dict})

    except Exception as exc:
        logger.error(f"Failed to query task status: {str(exc)}")
        return jsonify({"success": False, "error": str(exc)}), 500
