"""
Profile, config, branch, and script-download routes split from the main simulation API module.
"""

import os

from flask import request, send_file

from . import simulation_bp
from ..config import Config
from ..services.simulation_manager import SimulationManager
from ..utils.json_io import read_json_file, write_json_atomic
from ..utils.validation import validate_simulation_id
from ..utils.api_responses import handle_api_errors, json_success, json_error
from .simulation_common import logger


@simulation_bp.route('/<simulation_id>/branch', methods=['POST'])
@handle_api_errors(log_prefix="Failed to create simulation branch")
def create_simulation_branch(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    data = request.get_json() or {}
    branch_name = (data.get("branch_name") or "").strip()
    if not branch_name:
        return json_error("branch_name is required", status=400)

    manager = SimulationManager()
    branch = manager.create_branch(
        simulation_id=simulation_id,
        branch_name=branch_name,
        copy_profiles=data.get("copy_profiles", True),
        copy_report_artifacts=data.get("copy_report_artifacts", False),
        overrides=data.get("overrides") or {},
    )

    return json_success(branch.to_dict())


@simulation_bp.route('/<simulation_id>/branches', methods=['GET'])
@handle_api_errors(log_prefix="Failed to list simulation branches")
def list_simulation_branches(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    manager = SimulationManager()
    branches = manager.list_branches(simulation_id)
    return json_success([branch.to_dict() for branch in branches], count=len(branches))


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
@handle_api_errors(log_prefix="GetProfileFailed")
def get_simulation_profiles(simulation_id: str):
    """Get stored simulation profiles."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    platform = request.args.get('platform', 'reddit')
    manager = SimulationManager()
    profiles = manager.get_profiles(simulation_id, platform=platform)
    return json_success({
        "platform": platform,
        "count": len(profiles),
        "profiles": profiles,
    })


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
@handle_api_errors(log_prefix="Real-time getProfileFailed")
def get_simulation_profiles_realtime(simulation_id: str):
    """Read profile files directly for realtime generation feedback."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    import csv
    import json
    from datetime import datetime

    platform = request.args.get('platform', 'reddit')
    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

    profiles_file = os.path.join(sim_dir, "reddit_profiles.json" if platform == "reddit" else "twitter_profiles.csv")
    file_exists = os.path.exists(profiles_file)
    profiles = []
    file_modified_at = None

    if file_exists:
        file_stat = os.stat(profiles_file)
        file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
        try:
            if platform == "reddit":
                profiles = read_json_file(profiles_file, default=[], logger=logger, description=profiles_file) or []
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
            state_data = read_json_file(state_file, default=None, logger=logger, description=state_file)
            if state_data:
                status = state_data.get("status", "")
                is_generating = status == "preparing"
                total_expected = state_data.get("entities_count")
        except Exception:
            pass

    return json_success({
        "simulation_id": simulation_id,
        "platform": platform,
        "count": len(profiles),
        "total_expected": total_expected,
        "is_generating": is_generating,
        "file_exists": file_exists,
        "file_modified_at": file_modified_at,
        "profiles": profiles,
    })


def _load_profiles_file(sim_dir: str, platform: str):
    """Read reddit_profiles.json or twitter_profiles.csv into a list."""
    import csv

    if platform == 'reddit':
        path = os.path.join(sim_dir, 'reddit_profiles.json')
        if not os.path.exists(path):
            return path, []
        return path, (read_json_file(path, default=[], logger=logger, description=path) or [])

    path = os.path.join(sim_dir, 'twitter_profiles.csv')
    if not os.path.exists(path):
        return path, []
    with open(path, 'r', encoding='utf-8') as handle:
        return path, list(csv.DictReader(handle))


def _save_profiles_file(path: str, profiles: list, platform: str):
    import csv

    if platform == 'reddit':
        write_json_atomic(path, profiles)
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
@handle_api_errors(log_prefix="Failed to add persona")
def add_simulation_profile(simulation_id: str):
    """Append a manually authored persona to the simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    data = request.get_json() or {}
    platform = data.get('platform', 'reddit')
    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

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
    return json_success({
        "platform": platform,
        "count": len(profiles),
        "profile": new_profile,
    })


@simulation_bp.route('/<simulation_id>/profiles/<username>', methods=['DELETE'])
@handle_api_errors(log_prefix="Failed to delete persona")
def delete_simulation_profile(simulation_id: str, username: str):
    """Remove a persona from reddit_profiles.json / twitter_profiles.csv by username."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    platform = request.args.get('platform', 'reddit')
    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

    path, profiles = _load_profiles_file(sim_dir, platform)
    before = len(profiles)
    profiles = [profile for profile in profiles if str(profile.get('username', '')) != username]
    if len(profiles) == before:
        return json_error(f"Persona not found: {username}", status=404)

    _save_profiles_file(path, profiles, platform)
    return json_success({
        "platform": platform,
        "count": len(profiles),
        "removed": username,
    })


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
@handle_api_errors(log_prefix="Real-time getConfigFailed")
def get_simulation_config_realtime(simulation_id: str):
    """Read simulation configuration directly for realtime generation feedback."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    import json
    from datetime import datetime

    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(f"Simulation does not exist: {simulation_id}", status=404)

    config_file = os.path.join(sim_dir, "simulation_config.json")
    file_exists = os.path.exists(config_file)
    config = None
    file_modified_at = None

    if file_exists:
        file_stat = os.stat(config_file)
        file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
        try:
            config = read_json_file(config_file, default=None, logger=logger, description=config_file)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(f"Failed to read config file: {exc}")
            config = None

    is_generating = False
    generation_stage = None
    config_generated = False
    state_file = os.path.join(sim_dir, "state.json")
    if os.path.exists(state_file):
        try:
            state_data = read_json_file(state_file, default=None, logger=logger, description=state_file)
            if state_data:
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

    return json_success(response_data)


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
@handle_api_errors(log_prefix="Failed to get configuration")
def get_simulation_config(simulation_id: str):
    """Get the generated simulation configuration."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    manager = SimulationManager()
    config = manager.get_simulation_config(simulation_id)
    if not config:
        return json_error("Simulation configuration does not exist. Please call /prepare first", status=404)

    return json_success(config)


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
@handle_api_errors(log_prefix="Failed to download configuration")
def download_simulation_config(simulation_id: str):
    """Download simulation configuration file."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    manager = SimulationManager()
    sim_dir = manager._get_simulation_dir(simulation_id)
    config_path = os.path.join(sim_dir, "simulation_config.json")
    if not os.path.exists(config_path):
        return json_error("Configuration file does not exist. Please call /prepare first", status=404)

    return send_file(config_path, as_attachment=True, download_name="simulation_config.json")


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
@handle_api_errors(log_prefix="Failed to download script")
def download_simulation_script(script_name: str):
    """Download shared simulation script files from backend/scripts/."""
    scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
    allowed_scripts = [
        "run_twitter_simulation.py",
        "run_reddit_simulation.py",
        "run_parallel_simulation.py",
        "action_logger.py",
    ]
    if script_name not in allowed_scripts:
        return json_error(f"Unknown script: {script_name}，Optional: {allowed_scripts}", status=400)

    script_path = os.path.join(scripts_dir, script_name)
    if not os.path.exists(script_path):
        return json_error(f"Script file does not exist: {script_name}", status=404)

    return send_file(script_path, as_attachment=True, download_name=script_name)
