"""
Simulation-related API routes
Step2: Entity reading and filtering, OASIS simulation preparation and execution (fully automated)
"""

import os
import traceback
from flask import request, jsonify, send_file, current_app

from . import simulation_bp
from ..config import Config
from ..services.entity_reader import EntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.artifact_locator import ArtifactLocator
from ..utils.validation import validate_simulation_id, validate_project_id, validate_graph_id, validate_task_id
from ..models.project import ProjectManager
from .simulation_common import (
    logger,
    optimize_interview_prompt,
    run_registry,
    simulation_resume_capability as _simulation_resume_capability,
    simulation_run_artifacts as _simulation_run_artifacts,
)
from .simulation_prepare import _check_simulation_prepared


# The routes for /available-models, /entities/*, /create, /<simulation_id>, and /list
# were split into dedicated modules to reduce the size of this file while keeping
# the existing blueprint and URL structure unchanged.


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """
    Get simulation Corresponding latest report_id
    
    Traverse reports directory and find the report matching the simulation_id.
    If multiple exist, return the latest one (by created_at timestamp).
    
    Args:
        simulation_id: Simulation ID
        
    Returns:
        report_id Or None
    """
    import json
    from datetime import datetime
    
    # reports Directory path：backend/uploads/reports
    # __file__ Is app/api/simulation.py，Need to go up two levels to backend/
    reports_dir = os.path.join(os.path.dirname(__file__), '../../uploads/reports')
    if not os.path.exists(reports_dir):
        return None
    
    matching_reports = []
    
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue
            
            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue
            
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                if meta.get("simulation_id") == simulation_id:
                    matching_reports.append({
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", "")
                    })
            except Exception:
                continue
        
        if not matching_reports:
            return None
        
        # Sort by creation time descending，ReturnLatest
        matching_reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")
        
    except Exception as e:
        logger.warning(f"Failed to find report for simulation {simulation_id}: {e}")
        return None


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """
    Get historical simulation list（With project details）
    
    For homepage historical project display. Returns project name and other information about the simulation.
    
    Query parameters:
        limit: Return count limit（Default20）
    
    Returns:
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "WDU Opinion Analysis",
                    "simulation_requirement": "If Wuhan University publishes...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]
        
        # Enhance simulation data，Only from Simulation FileRead
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()
            
            # Get simulation configuration information（From simulation_config.json Read simulation_requirement）
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # Recommended rounds（Fallback value）
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60 / 
                    max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0
            
            # Get running status (from run_state.json)
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # Use user-set total_rounds，If not, thenUseRecommended rounds
                sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds
            
            # Get associated project file list（At most3items）
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "Unknown file")} 
                    for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []
            
            # Get associated report_id（FindThis simulation Latest report）
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)
            sim_dict["source_simulation_id"] = sim.source_simulation_id
            sim_dict["root_simulation_id"] = sim.root_simulation_id or sim.simulation_id
            sim_dict["branch_name"] = sim.branch_name
            sim_dict["branch_depth"] = sim.branch_depth

            # Add version number
            sim_dict["version"] = "v1.0.2"
            
            # Format date
            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except:
                sim_dict["created_date"] = ""
            
            enriched_simulations.append(sim_dict)
        
        return jsonify({
            "success": True,
            "data": enriched_simulations,
            "count": len(enriched_simulations)
        })
        
    except Exception as e:
        logger.error(f"Failed to get historical simulations: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


# ============== ProfileGeneration interface（StandaloneUse） ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    Generate directly from knowledge graphOASIS Agent Profile（Do not createSimulation）
    
    Request (JSON):
        {
            "graph_id": "agora_xxxx",     // Required
            "entity_types": ["Student"],      // Optional
            "use_llm": true,                  // Optional
            "platform": "reddit"              // Optional
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Please provide graph_id"
            }), 400
        
        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')
        
        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized")
        reader = EntityReader(storage)
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )
        
        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": "No matching entities found"
            }), 400
        
        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        
        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(f"GenerateProfileFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


# ============== Simulation execution control interface ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    Start running simulation

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",          // Required，Simulation ID
            "platform": "parallel",                // Optional: twitter / reddit / parallel (Default)
            "max_rounds": 100,                     // Optional: Maximum simulation rounds, default unlimited
            "enable_graph_memory_update": false,   // Optional: Whether to enable knowledge graph memory updates for agents
            "force": false                         // Optional: Force restart (stop running simulation and clean runtime files)
        }

    About force Parameters:
        - After enabling, if simulation is running or completed, clean runtime logs
        - Cleanup includes：run_state.json, actions.jsonl, simulation.log And so on
        - Will not clean configuration files（simulation_config.json）And profile File
        - For scenarios that need to rerun simulation

    About enable_graph_memory_update:
        - After enabling, all agents in the simulation will update the knowledge graph with their actions (posts, comments, follows, etc.)
        - This allows the knowledge graph to "remember" the simulation, improving context understanding and AI decision-making
        - Requires associated project to have valid graph_id
        - Uses batch update mechanism to reduce API overhead

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // Whether knowledge graph memory update enabled
                "force_restarted": true               // Whether is forced restart
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  # Optional: Maximum simulation rounds
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # Optional：IsFalseEnable knowledge graph memory update
        force = data.get('force', False)  # Optional：Force restart

        # Verify max_rounds Parameters
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "max_rounds Must be positive integer"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "max_rounds Must be valid integer"
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel']:
            return jsonify({
                "success": False,
                "error": f"Invalid platform type: {platform}，Optional: twitter/reddit/parallel"
            }), 400

        # Check if simulation is ready
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation does not exist: {simulation_id}"
            }), 404

        force_restarted = False
        
        # Intelligently handle status: if preparation work is complete, reset status to ready
        if state.status != SimulationStatus.READY:
            # Check if preparation is complete
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # Preparation work complete, verify if simulation is not already running
                if state.status == SimulationStatus.RUNNING:
                    # Check if simulation process is really running
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # Process is indeed running
                        if force:
                            # Force mode：Stop runningSimulation
                            logger.info(f"Force mode：Stop runningSimulation {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"Warning when stopping simulation: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": f"Simulation is running. Please call /stop first or use force=true to force restart."
                            }), 400

                # If force mode，Clean runtime logs
                if force:
                    logger.info(f"Force mode: cleaning simulation runtime files for {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"Warning when cleaning logs: {cleanup_result.get('errors')}")
                    force_restarted = True

                # Process does not exist or has ended，Reset status to ready
                logger.info(f"Simulation {simulation_id} preparation complete, resetting status to ready (previous status: {state.status.value})")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # Preparation not complete
                return jsonify({
                    "success": False,
                    "error": f"Simulation not ready. Current status: {state.status.value}. Please call /prepare first"
                }), 400
        
        # Get knowledge graphID（For knowledge graph memory update）
        graph_id = None
        if enable_graph_memory_update:
            # Get from simulation status or project graph_id
            graph_id = state.graph_id
            if not graph_id:
                # Try to get from project
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id
            
            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "Enable knowledge graph memory update requires valid graph_id，Please ensure project graph built"
                }), 400
            
            logger.info(
                f"Enable knowledge graph memory update: simulation_id={simulation_id}, graph_id={graph_id}",
                extra={'simulation_id': simulation_id},
            )
        
        # Start simulation
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )
        
        # Update simulation status
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)

        run_record = run_registry.create_run(
            run_type="simulation_run",
            entity_id=simulation_id,
            status="processing",
            progress=0,
            message="Simulation run started",
            linked_ids={
                "simulation_id": simulation_id,
                "project_id": state.project_id,
            },
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability=_simulation_resume_capability(simulation_id, state),
            branch_label=state.branch_name,
            metadata={
                "graph_id": state.graph_id,
                "platform": platform,
                "source_simulation_id": state.source_simulation_id,
                "root_simulation_id": state.root_simulation_id,
                "branch_name": state.branch_name,
                "branch_depth": state.branch_depth,
            },
        )
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        response_data['run_id'] = run_record["run_id"]
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to start simulation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    Stop simulation
    
    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // Required，Simulation ID
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        run_state = SimulationRunner.stop_simulation(simulation_id)
        
        # Update simulation status
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
            run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
            if run:
                run_registry.update_run(
                    run["run_id"],
                    status="stopped",
                    progress=run_state.to_dict().get("progress_percent", 0),
                    message="Simulation stopped",
                    artifacts=_simulation_run_artifacts(simulation_id),
                    resume_capability=_simulation_resume_capability(simulation_id, state),
                )
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to stop simulation: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


# ============== Pause / Resume (Phase 4 — soft-pause between rounds) ==============

def _simulation_dir(simulation_id: str) -> str:
    return os.path.join(SimulationRunner.RUN_STATE_DIR, simulation_id)


@simulation_bp.route('/<simulation_id>/pause', methods=['POST'])
def pause_simulation(simulation_id: str):
    """Set the soft-pause flag — OASIS halts after the current round ends."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    from ..services.simulation_ipc import set_pause_state
    sim_dir = _simulation_dir(simulation_id)
    if not os.path.isdir(sim_dir):
        return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404
    state = set_pause_state(sim_dir, True)
    logger.info(f"Pause requested for {simulation_id}")
    run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        sim_state = SimulationManager().get_simulation(simulation_id)
        run_registry.update_run(
            run["run_id"],
            status="paused",
            message="Pause requested",
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability=_simulation_resume_capability(simulation_id, sim_state),
        )
    return jsonify({"success": True, "data": {"simulation_id": simulation_id, "control_state": state}})


@simulation_bp.route('/<simulation_id>/resume', methods=['POST'])
def resume_simulation(simulation_id: str):
    """Clear the pause flag so the OASIS subprocess continues with the next round."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    from ..services.simulation_ipc import set_pause_state
    sim_dir = _simulation_dir(simulation_id)
    if not os.path.isdir(sim_dir):
        return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404
    state = set_pause_state(sim_dir, False)
    logger.info(f"Resume requested for {simulation_id}")
    run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        sim_state = SimulationManager().get_simulation(simulation_id)
        run_registry.update_run(
            run["run_id"],
            status="processing",
            message="Run resumed",
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability=_simulation_resume_capability(simulation_id, sim_state),
        )
    return jsonify({"success": True, "data": {"simulation_id": simulation_id, "control_state": state}})


# ============== Real-time status monitoring interface ==============

@simulation_bp.route('/<simulation_id>/console-log', methods=['GET'])
def get_simulation_console_log(simulation_id: str):
    """
    Stream raw stdout/stderr of the OASIS subprocess for this simulation.

    Query params:
        from_line: skip lines before this index (for incremental polling)

    Returns:
        { "success": true, "data": { "lines": [...], "total_lines": N, "from_line": K, "next_line": N, "has_more": false } }
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        from_line = request.args.get('from_line', 0, type=int)
        data = SimulationRunner.get_console_log(simulation_id, from_line=from_line)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"Failed to read simulation console log: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """
    Get simulation real-time running status (For frontend polling)

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        from ..services.simulation_ipc import read_control_state
        run_state = SimulationRunner.get_run_state(simulation_id)
        control = read_control_state(_simulation_dir(simulation_id))

        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                    "paused": bool(control.get("paused")),
                }
            })

        data = run_state.to_dict()
        data["paused"] = bool(control.get("paused"))
        return jsonify({"success": True, "data": data})

    except Exception as e:
        logger.error(f"Failed to get running status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """
    Get simulation detailed running status (Include all actions)

    For frontend to display real-time dynamics

    Query parameters:
        platform: Filter platform (twitter/reddit, Optional)

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # Twitter All actions of platform
                "reddit_actions": [...]    # Reddit All actions of platform
            }
        }
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": []
                }
            })
        
        # Get complete action list
        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter
        )
        
        # Get actions by platform
        twitter_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="twitter"
        ) if not platform_filter or platform_filter == "twitter" else []
        
        reddit_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="reddit"
        ) if not platform_filter or platform_filter == "reddit" else []
        
        # Get current round actions（recent_actions Only show latest round）
        current_round = run_state.current_round
        recent_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
            round_num=current_round
        ) if current_round > 0 else []
        
        # Get basic status information
        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        # recent_actions Only show latest round content of two platforms
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Failed to get detailed status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """
    Get from simulation Agent Action history

    Query parameters:
        limit: Return count (Default 100)
        offset: Offset (Default 0)
        platform: Filter platform (twitter/reddit)
        agent_id: Filter Agent ID
        round_num: Filter round

    Returns:
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)
        
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get action history: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """
    Get simulation timeline (Summarized by round)

    For frontend to display progress bar and timeline view

    Query parameters:
        start_round: Start round (Default 0)
        end_round: End round (Default all)

    Return summary information per round
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)
        
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )
        
        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get timeline: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """
    Get each Agent Statistics

    For frontend display of agent activity ranking and statistics.
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        
        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get agent statistics: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


# ============== Database query interface ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """
    Get posts in simulation

    Query parameters:
        platform: Platform type (twitter/reddit)
        limit: Return count (Default 50)
        offset: Offset

    Return post list (read from SQLite database)
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "Database does not exist，SimulationMay not have run yet"
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            posts = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
            
        except sqlite3.OperationalError:
            posts = []
            total = 0
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get posts: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """
    Get comments in simulation (Only Reddit)

    Query parameters:
        post_id: Filter posts ID (Optional)
        limit: Return count
        offset: Offset
    """
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_path = os.path.join(sim_dir, "reddit_simulation.db")
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            
            comments = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.OperationalError:
            comments = []
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get comments: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


# ============== Interview Interview interface ==============

@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """
    Interview individualAgent

    Note: This feature requires simulation to be in a running or completed state (run the simulation and wait for it to progress).

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // Required，Simulation ID
            "agent_id": 0,                     // Required，Agent ID
            "prompt": "What do you think about this？",  // Required，Interview question
            "platform": "twitter",             // Optional，Specified platform（twitter/reddit）
                                               // When not specified: Both platforms in dual-platform simulations
            "timeout": 60                      // Optional, timeout in seconds, default 60
        }

    Return (when platform not specified, returns results from both platforms):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "What do you think about this？",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    Return（Specifiedplatform）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "What do you think about this？",
                "result": {
                    "agent_id": 0,
                    "response": "I think...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # Optional：twitter/reddit/None
        timeout = data.get('timeout', 60)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        if agent_id is None:
            return jsonify({
                "success": False,
                "error": "Please provide agent_id"
            }), 400
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": "Please provide prompt（Interview question）"
            }), 400
        
        # VerifyplatformParameters
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform Parameter can only be 'twitter' Or 'reddit'"
            }), 400
        
        # Check environment status
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress."
            }), 400
        
        # Optimizeprompt，Add prefix to avoidAgent call tools
        optimized_prompt = optimize_interview_prompt(prompt)
        
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"WaitInterviewResponse timeout: {str(e)}"
        }), 504
        
    except Exception as e:
        logger.error(f"InterviewFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """
    Batch interview multipleAgent

    Note: This feature requires simulation to be in a running or completed state.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // Required，Simulation ID
            "interviews": [                    // Required，Interview list
                {
                    "agent_id": 0,
                    "prompt": "Your opinion onAWhat do you think？",
                    "platform": "twitter"      // Optional, interview this agent on specified platform
                },
                {
                    "agent_id": 1,
                    "prompt": "Your opinion onBWhat do you think？"  // Not specifiedplatform[then]UseDefaultValue
                }
            ],
            "platform": "reddit",              // Optional, Default platform (overridden by each item's platform)
                                               // When not specified: Both platforms in dual-platform simulations, single platform in single-platform simulations
            "timeout": 120                     // Optional, timeout in seconds, default 120
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        interviews = data.get('interviews')
        platform = data.get('platform')  # Optional：twitter/reddit/None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": "Please provide interviews（Interview list）"
            }), 400

        # VerifyplatformParameters
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform Parameter can only be 'twitter' Or 'reddit'"
            }), 400

        # Verify each interview item
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"Interview list item{i+1}Missing agent_id"
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"Interview list item{i+1}Missing prompt"
                }), 400
            # Verify each item'splatform（IfHas）
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": f"Interview list item {i+1}: platform must be 'twitter' or 'reddit'"
                }), 400

        # Check environment status
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress."
            }), 400

        # OptimizeEachInterview itemprompt，Add prefix to avoidAgent call tools
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Wait for batchInterviewResponse timeout: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"BatchInterviewFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """
    Global interview - UseInterview all with same questionAgent

    Note: This feature requires simulation to be in a running or completed state.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",            // Required，Simulation ID
            "prompt": "What is your overall view on this?",  // Required, interview question (avoid enabling agent to use tools)
            "platform": "reddit",                   // Optional, Specified platform (twitter/reddit)
                                                    // When not specified: Both platforms in dual-platform simulations, single platform in single-platform simulations
            "timeout": 180                          // Optional, timeout in seconds, default 180
        }

    Returns:
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        prompt = data.get('prompt')
        platform = data.get('platform')  # Optional：twitter/reddit/None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "Please provide prompt（Interview question）"
            }), 400

        # VerifyplatformParameters
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "platform Parameter can only be 'twitter' Or 'reddit'"
            }), 400

        # Check environment status
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress."
            }), 400

        # Optimizeprompt，Add prefix to avoidAgent call tools
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"Wait for globalInterviewResponse timeout: {str(e)}"
        }), 504

    except Exception as e:
        logger.error(f"GlobalInterviewFailed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """
    GetInterviewHistorical records

    Read all from simulation databaseInterviewRecord

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // Required，Simulation ID
            "platform": "reddit",          // Optional，Platform type（reddit/twitter）
                                           // If not specified, return all history of both platforms
            "agent_id": 0,                 // Optional, Get interview history for only this agent
            "limit": 100                   // Optional，Return count，Default100
        }

    Returns:
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "I think...",
                        "prompt": "What do you think about this？",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        platform = data.get('platform')  # If not specified, return history of both platforms
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(f"Failed to get interview history: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """
    Get simulation environment status

    Check if simulation environment is alive (can receive interview requests).

    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // Required，Simulation ID
        }

    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "Environment running, ready to receive interview requests"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400

        if not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        env_alive = SimulationRunner.check_env_alive(simulation_id)
        
        # Get more detailed status information
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "Environment running, ready to receive interview requests"
        else:
            message = "Environment not running or closed"

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message
            }
        })

    except Exception as e:
        logger.error(f"Failed to get environment status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """
    Close simulation environment
    
    Send close environment command to simulation to gracefully exit and wait for completion.

    Note: This is different from /stop. /stop terminates the simulation abruptly.
    This interface lets the simulation gracefully close the environment and exit.
    
    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // Required，Simulation ID
            "timeout": 30                  // Optional, timeout in seconds, default 30
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "message": "Environment close command sent",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
        timeout = data.get('timeout', 30)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        # Update simulation status
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Failed to close environment: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc() if Config.DEBUG else None
        }), 500
