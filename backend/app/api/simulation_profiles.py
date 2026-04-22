"""
Profile, config, branch, and script-download routes split from the main simulation API module.
"""

import os
import traceback

from flask import jsonify, request, send_file

from . import simulation_bp
from ..config import Config
from ..services.simulation_manager import SimulationManager
from ..utils.validation import validate_simulation_id
from .simulation_common import logger


@simulation_bp.route('/<simulation_id>/branch', methods=['POST'])
def create_simulation_branch(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        data = request.get_json() or {}
        branch_name = (data.get("branch_name") or "").strip()
        if not branch_name:
            return jsonify({"success": False, "error": "branch_name is required"}), 400

        manager = SimulationManager()
        branch = manager.create_branch(
            simulation_id=simulation_id,
            branch_name=branch_name,
            copy_profiles=data.get("copy_profiles", True),
            copy_report_artifacts=data.get("copy_report_artifacts", False),
            overrides=data.get("overrides") or {},
        )

        return jsonify({"success": True, "data": branch.to_dict()})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error(f"Failed to create simulation branch: {exc}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/branches', methods=['GET'])
def list_simulation_branches(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        manager = SimulationManager()
        branches = manager.list_branches(simulation_id)
        return jsonify({
            "success": True,
            "data": [branch.to_dict() for branch in branches],
            "count": len(branches),
        })
    except Exception as exc:
        logger.error(f"Failed to list simulation branches: {exc}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """Get stored simulation profiles."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        platform = request.args.get('platform', 'reddit')
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles,
            },
        })
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        logger.error(f"GetProfileFailed: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """Read profile files directly for realtime generation feedback."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    import csv
    import json
    from datetime import datetime

    try:
        platform = request.args.get('platform', 'reddit')
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404

        profiles_file = os.path.join(sim_dir, "reddit_profiles.json" if platform == "reddit" else "twitter_profiles.csv")
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None

        if file_exists:
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            try:
                if platform == "reddit":
                    with open(profiles_file, 'r', encoding='utf-8') as handle:
                        profiles = json.load(handle)
                else:
                    with open(profiles_file, 'r', encoding='utf-8') as handle:
                        profiles = list(csv.DictReader(handle))
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning(f"Failed to read profiles file: {exc}")
                profiles = []

        is_generating = False
        total_expected = None
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as handle:
                    state_data = json.load(handle)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles,
            },
        })
    except Exception as exc:
        logger.error(f"Real-time getProfileFailed: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


def _load_profiles_file(sim_dir: str, platform: str):
    """Read reddit_profiles.json or twitter_profiles.csv into a list."""
    import csv
    import json

    if platform == 'reddit':
        path = os.path.join(sim_dir, 'reddit_profiles.json')
        if not os.path.exists(path):
            return path, []
        with open(path, 'r', encoding='utf-8') as handle:
            try:
                return path, json.load(handle)
            except json.JSONDecodeError:
                return path, []

    path = os.path.join(sim_dir, 'twitter_profiles.csv')
    if not os.path.exists(path):
        return path, []
    with open(path, 'r', encoding='utf-8') as handle:
        return path, list(csv.DictReader(handle))


def _save_profiles_file(path: str, profiles: list, platform: str):
    import csv
    import json

    if platform == 'reddit':
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(profiles, handle, ensure_ascii=False, indent=2)
        return

    if not profiles:
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            handle.write('')
        return

    fieldnames = list(profiles[0].keys())
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(profiles)


@simulation_bp.route('/<simulation_id>/profiles', methods=['POST'])
def add_simulation_profile(simulation_id: str):
    """Append a manually authored persona to the simulation."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        data = request.get_json() or {}
        platform = data.get('platform', 'reddit')
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404

        path, profiles = _load_profiles_file(sim_dir, platform)
        existing_ids = [int(profile.get('user_id', 0) or 0) for profile in profiles]
        next_id = (max(existing_ids) + 1) if existing_ids else 0
        username = (data.get('username') or f'user_{next_id}').strip()
        existing_names = {str(profile.get('username', '')).lower() for profile in profiles}
        if username.lower() in existing_names:
            base = username
            suffix = 1
            while f"{base}_{suffix}".lower() in existing_names:
                suffix += 1
            username = f"{base}_{suffix}"

        new_profile = {
            'user_id': next_id,
            'username': username,
            'name': data.get('name') or username,
            'bio': data.get('bio', ''),
            'persona': data.get('persona', ''),
            'age': data.get('age'),
            'gender': data.get('gender', 'other'),
            'mbti': data.get('mbti', ''),
            'country': data.get('country', 'DE'),
            'profession': data.get('profession', ''),
            'interested_topics': data.get('interested_topics', []),
            'source_entity_uuid': data.get('source_entity_uuid'),
            'source_entity_type': data.get('source_entity_type', 'manual'),
            'is_manual': True,
        }

        extra_allowed = {
            'followers_count', 'following_count', 'favourites_count',
            'listed_count', 'verified', 'status', 'location', 'language',
            'activity_level', 'time_zone',
        }
        for key, value in data.items():
            if key in ('platform',) or key in new_profile:
                continue
            if key not in extra_allowed:
                logger.debug(f"add_simulation_profile: ignoring unknown key {key!r}")
                continue
            if isinstance(value, (str, int, float, bool, list)) or value is None:
                new_profile[key] = value
            else:
                logger.debug(f"add_simulation_profile: ignoring non-primitive {key!r}")

        profiles.append(new_profile)
        _save_profiles_file(path, profiles, platform)
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profile": new_profile,
            },
        })
    except Exception as exc:
        logger.error(f"Failed to add persona: {exc}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/<username>', methods=['DELETE'])
def delete_simulation_profile(simulation_id: str, username: str):
    """Remove a persona from reddit_profiles.json / twitter_profiles.csv by username."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        platform = request.args.get('platform', 'reddit')
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404

        path, profiles = _load_profiles_file(sim_dir, platform)
        before = len(profiles)
        profiles = [profile for profile in profiles if str(profile.get('username', '')) != username]
        if len(profiles) == before:
            return jsonify({"success": False, "error": f"Persona not found: {username}"}), 404

        _save_profiles_file(path, profiles, platform)
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "removed": username,
            },
        })
    except Exception as exc:
        logger.error(f"Failed to delete persona: {exc}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """Read simulation configuration directly for realtime generation feedback."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    import json
    from datetime import datetime

    try:
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404

        config_file = os.path.join(sim_dir, "simulation_config.json")
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None

        if file_exists:
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            try:
                with open(config_file, 'r', encoding='utf-8') as handle:
                    config = json.load(handle)
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning(f"Failed to read config file: {exc}")
                config = None

        is_generating = False
        generation_stage = None
        config_generated = False
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as handle:
                    state_data = json.load(handle)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)
                    if is_generating:
                        generation_stage = "generating_config" if state_data.get("profiles_generated", False) else "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
            except Exception:
                pass

        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config,
        }
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model"),
            }

        return jsonify({"success": True, "data": response_data})
    except Exception as exc:
        logger.error(f"Real-time getConfigFailed: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """Get the generated simulation configuration."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        if not config:
            return jsonify({
                "success": False,
                "error": "Simulation configuration does not exist. Please call /prepare first",
            }), 404

        return jsonify({"success": True, "data": config})
    except Exception as exc:
        logger.error(f"Failed to get configuration: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """Download simulation configuration file."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "Configuration file does not exist. Please call /prepare first",
            }), 404

        return send_file(config_path, as_attachment=True, download_name="simulation_config.json")
    except Exception as exc:
        logger.error(f"Failed to download configuration: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """Download shared simulation script files from backend/scripts/."""
    try:
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py",
            "run_parallel_simulation.py",
            "action_logger.py",
        ]
        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": f"Unknown script: {script_name}，Optional: {allowed_scripts}",
            }), 400

        script_path = os.path.join(scripts_dir, script_name)
        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": f"Script file does not exist: {script_name}",
            }), 404

        return send_file(script_path, as_attachment=True, download_name=script_name)
    except Exception as exc:
        logger.error(f"Failed to download script: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500
