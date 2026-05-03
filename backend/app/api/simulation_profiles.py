"""
Profile, config, branch, and script-download routes split from the main simulation API module.
"""

import os
from datetime import datetime, timezone

from flask import request, send_file

from . import simulation_bp
from ..config import Config
from ..services.persona_library import PersonaLibrary
from ..services.persona_quality_service import PersonaQualityService
from ..services.persona_review_service import (
    InvalidReviewStatusError,
    PersonaNotFoundError,
    PersonaReviewService,
)
from ..services.simulation_manager import SimulationManager
from ..utils.auth import allow_ticket_auth
from ..utils.validation import validate_simulation_id
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from .simulation_common import get_artifact_store, logger


def _persona_review_service() -> PersonaReviewService:
    return PersonaReviewService(get_artifact_store())


@simulation_bp.route('/<simulation_id>/branch', methods=['POST'])
@handle_api_errors(log_prefix="Failed to create simulation branch")
def create_simulation_branch(simulation_id: str):
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    data = request.get_json() or {}
    branch_name = (data.get("branch_name") or "").strip()
    if not branch_name:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="branch_name is required",
        )

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
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    manager = SimulationManager()
    branches = manager.list_branches(simulation_id)
    return json_success([branch.to_dict() for branch in branches], count=len(branches))


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
@handle_api_errors(log_prefix="GetProfileFailed")
def get_simulation_profiles(simulation_id: str):
    """Get stored simulation profiles."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    platform = request.args.get('platform', 'reddit')
    manager = SimulationManager()
    if platform == 'reddit':
        # Validate the simulation exists, then read normalized review state
        # directly from the artifact store via the review service.
        manager.get_profiles(simulation_id, platform=platform)
        profiles = _persona_review_service().list_profiles(simulation_id)
    else:
        profiles = manager.get_profiles(simulation_id, platform=platform)
    return json_success({
        "platform": platform,
        "count": len(profiles),
        "profiles": profiles,
        "review_enabled": Config.PERSONA_REVIEW_ENABLED,
    })


@simulation_bp.route('/persona-library', methods=['GET'])
@handle_api_errors(log_prefix="Failed to list persona templates")
def list_persona_templates():
    """List reusable persona templates stored on this machine."""
    templates = PersonaLibrary().list_templates()
    return json_success({"count": len(templates), "templates": templates})


@simulation_bp.route('/persona-library', methods=['POST'])
@handle_api_errors(log_prefix="Failed to save persona template")
def save_persona_template():
    """Persist a generated or manually authored persona for later simulations."""
    data = request.get_json() or {}
    if not (data.get("username") or data.get("name") or data.get("persona")):
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Provide at least username, name, or persona",
        )
    template = PersonaLibrary().save_template(data)
    return json_success({"template": template})


@simulation_bp.route('/persona-library/<template_id>', methods=['DELETE'])
@handle_api_errors(log_prefix="Failed to delete persona template")
def delete_persona_template(template_id: str):
    """Remove a reusable persona template."""
    if not PersonaLibrary().delete_template(template_id):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Persona template not found: {template_id}",
        )
    return json_success({"removed": template_id})


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
@handle_api_errors(log_prefix="Real-time getProfileFailed")
def get_simulation_profiles_realtime(simulation_id: str):
    """Read profile files directly for realtime generation feedback."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    import csv
    from datetime import datetime

    platform = request.args.get('platform', 'reddit')
    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    store = get_artifact_store()
    profiles = []
    file_modified_at = None

    if platform == "reddit":
        file_exists = store.exists(simulation_id, "reddit_profiles")
        if file_exists:
            # mtime kommt weiter vom Filesystem; der Store-Port modelliert keine Metadaten.
            profiles_path = os.path.join(sim_dir, "reddit_profiles.json")
            if os.path.exists(profiles_path):
                file_modified_at = datetime.fromtimestamp(
                    os.stat(profiles_path).st_mtime
                ).isoformat()
            profiles = store.read_json(simulation_id, "reddit_profiles", default=[]) or []
    else:
        # CSV liegt außerhalb des JSON-Stores (out of scope für Issue #13).
        profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")
        file_exists = os.path.exists(profiles_file)
        if file_exists:
            file_modified_at = datetime.fromtimestamp(
                os.stat(profiles_file).st_mtime
            ).isoformat()
            try:
                with open(profiles_file, 'r', encoding='utf-8') as handle:
                    profiles = list(csv.DictReader(handle))
            except OSError as exc:
                logger.warning(f"Failed to read profiles file: {exc}")
                profiles = []

    is_generating = False
    total_expected = None
    state_data = store.read_json(simulation_id, "state", default=None)
    if state_data:
        status = state_data.get("status", "")
        is_generating = status == "preparing"
        total_expected = state_data.get("entities_count")

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


def _load_profiles_file(simulation_id: str, sim_dir: str, platform: str):
    """Read reddit_profiles.json or twitter_profiles.csv into a list."""
    import csv

    if platform == 'reddit':
        store = get_artifact_store()
        profiles = store.read_json(simulation_id, 'reddit_profiles', default=[]) or []
        return None, profiles

    path = os.path.join(sim_dir, 'twitter_profiles.csv')
    if not os.path.exists(path):
        return path, []
    with open(path, 'r', encoding='utf-8') as handle:
        return path, list(csv.DictReader(handle))


def _save_profiles_file(simulation_id: str, path: str, profiles: list, platform: str):
    import csv

    if platform == 'reddit':
        get_artifact_store().write_json(simulation_id, 'reddit_profiles', profiles)
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
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    data = request.get_json() or {}
    platform = data.get('platform', 'reddit')
    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    path, profiles = _load_profiles_file(simulation_id, sim_dir, platform)
    existing_ids = [int(profile.get('user_id', 0) or 0) for profile in profiles]
    # When profiles exist, always max+1 to avoid collision with generated user_id=0.
    # When no profiles exist start at 1 (not 0) to keep 0 reserved for generated profiles.
    next_id = (max(existing_ids) + 1) if existing_ids else 1
    username = (data.get('username') or f'user_{next_id}').strip()
    existing_names = {str(profile.get('username', '')).lower() for profile in profiles}
    if username.lower() in existing_names:
        base = username
        suffix = 1
        while f"{base}_{suffix}".lower() in existing_names:
            suffix += 1
        username = f"{base}_{suffix}"

    display_name = data.get('name') or username
    # Defaults match _save_reddit_json so OASIS can process manual personas identically
    # to generated ones (Issue #210).
    bio = (data.get('bio') or '').strip() or display_name
    persona = (data.get('persona') or '').strip() or (
        f"{display_name} is a participant in social discussions."
    )
    # karma defensiv casten — Frontend-Forms liefern leere Strings oft als
    # falsy. int('') würde ValueError werfen. (Gemini-Code-Assist Finding,
    # PR #226.)
    karma_raw = data.get('karma')
    if karma_raw in (None, '', 'null'):
        karma = 1000
    else:
        try:
            karma = int(karma_raw)
        except (ValueError, TypeError):
            karma = 1000

    # created_at-Format spiegelt OasisAgentProfile (oasis_profile_generator.py:66)
    # — '%Y-%m-%d', kein Zeit-Anteil. Schema-Parity zwischen manuellen und
    # generierten Profilen. (Gemini-Code-Assist Finding, PR #226.)
    new_profile = {
        'user_id': next_id,
        'username': username,
        'name': display_name,
        'bio': bio,
        'persona': persona,
        'karma': karma,
        'created_at': (data.get('created_at') or '').strip()
            or datetime.now(timezone.utc).strftime('%Y-%m-%d'),
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
    _save_profiles_file(simulation_id, path, profiles, platform)
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
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    platform = request.args.get('platform', 'reddit')
    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    path, profiles = _load_profiles_file(simulation_id, sim_dir, platform)
    before = len(profiles)
    profiles = [profile for profile in profiles if str(profile.get('username', '')) != username]
    if len(profiles) == before:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Persona not found: {username}",
        )

    _save_profiles_file(simulation_id, path, profiles, platform)
    return json_success({
        "platform": platform,
        "count": len(profiles),
        "removed": username,
    })


@simulation_bp.route('/<simulation_id>/profiles/quality', methods=['GET'])
@handle_api_errors(log_prefix="Failed to compute persona quality")
def get_simulation_profiles_quality(simulation_id: str):
    """Quality heuristics over the reddit personas of a simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )
    # No existence check: an empty/unknown simulation surfaces ``no_personas``
    # as a global warning, which is the more useful UX than a hard 404 while
    # the Step 2 UI is still spinning up profiles.
    report = PersonaQualityService(get_artifact_store()).evaluate(simulation_id)
    report["review_enabled"] = Config.PERSONA_REVIEW_ENABLED
    return json_success(report)


def _handle_review_action(
    simulation_id: str,
    username: str,
    action,
):
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )
    try:
        profile = action(_persona_review_service())
    except PersonaNotFoundError as exc:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=str(exc),
        )
    except InvalidReviewStatusError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )
    return json_success({
        "username": username,
        "review_status": profile.get("review_status"),
        "profile": profile,
    })


@simulation_bp.route('/<simulation_id>/profiles/<username>', methods=['PATCH'])
@handle_api_errors(log_prefix="Failed to edit persona")
def edit_simulation_profile(simulation_id: str, username: str):
    """Edit a reddit persona in-place; resets review_status to pending."""
    data = request.get_json(silent=True) or {}
    return _handle_review_action(
        simulation_id,
        username,
        action=lambda service: service.edit(simulation_id, username, data),
    )


@simulation_bp.route('/<simulation_id>/profiles/<username>/approve', methods=['POST'])
@handle_api_errors(log_prefix="Failed to approve persona")
def approve_simulation_profile(simulation_id: str, username: str):
    """Mark a reddit persona as approved for the upcoming simulation run."""
    data = request.get_json(silent=True) or {}
    notes = data.get("notes")
    return _handle_review_action(
        simulation_id,
        username,
        action=lambda service: service.approve(
            simulation_id, username, notes=notes
        ),
    )


@simulation_bp.route('/<simulation_id>/profiles/<username>/reject', methods=['POST'])
@handle_api_errors(log_prefix="Failed to reject persona")
def reject_simulation_profile(simulation_id: str, username: str):
    """Mark a reddit persona as rejected; the gate (Slice 2.3) will skip it."""
    data = request.get_json(silent=True) or {}
    notes = data.get("notes") or data.get("reason")
    return _handle_review_action(
        simulation_id,
        username,
        action=lambda service: service.reject(
            simulation_id, username, notes=notes
        ),
    )


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
@handle_api_errors(log_prefix="Real-time getConfigFailed")
def get_simulation_config_realtime(simulation_id: str):
    """Read simulation configuration directly for realtime generation feedback."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    from datetime import datetime

    sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    store = get_artifact_store()
    file_exists = store.exists(simulation_id, "simulation_config")
    file_modified_at = None
    if file_exists:
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if os.path.exists(config_path):
            file_modified_at = datetime.fromtimestamp(
                os.stat(config_path).st_mtime
            ).isoformat()
    config = store.read_json(simulation_id, "simulation_config", default=None) if file_exists else None

    is_generating = False
    generation_stage = None
    config_generated = False
    state_data = store.read_json(simulation_id, "state", default=None)
    if state_data:
        status = state_data.get("status", "")
        is_generating = status == "preparing"
        config_generated = state_data.get("config_generated", False)
        if is_generating:
            generation_stage = "generating_config" if state_data.get("profiles_generated", False) else "generating_profiles"
        elif status == "ready":
            generation_stage = "completed"

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
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    manager = SimulationManager()
    config = manager.get_simulation_config(simulation_id)
    if not config:
        return json_error(
            ApiErrorCode.SIMULATION_NOT_PREPARED,
            status=404,
            message="Simulation configuration does not exist. Please call /prepare first",
        )

    return json_success(config)


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
@allow_ticket_auth(lambda simulation_id: f"download:simulation_config:{simulation_id}")
@handle_api_errors(log_prefix="Failed to download configuration")
def download_simulation_config(simulation_id: str):
    """Download simulation configuration file."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    manager = SimulationManager()
    sim_dir = manager._get_simulation_dir(simulation_id)
    config_path = os.path.join(sim_dir, "simulation_config.json")
    if not os.path.exists(config_path):
        return json_error(
            ApiErrorCode.SIMULATION_NOT_PREPARED,
            status=404,
            message="Configuration file does not exist. Please call /prepare first",
        )

    return send_file(config_path, as_attachment=True, download_name="simulation_config.json")


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
@allow_ticket_auth(lambda script_name: f"download:simulation_script:{script_name}")
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
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=f"Unknown script: {script_name}. Allowed: {allowed_scripts}",
        )

    script_path = os.path.join(scripts_dir, script_name)
    if not os.path.exists(script_path):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Script file does not exist: {script_name}",
        )

    return send_file(script_path, as_attachment=True, download_name=script_name)
