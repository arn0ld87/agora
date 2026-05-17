"""
Status monitoring endpoint — unified health check for all system components.
Returns backend version, Neo4j reachability, Ollama availability, and disk usage in a single request.
"""

import os
import shutil
from datetime import datetime, timezone
from flask import current_app
import requests

from . import status_bp
from .. import __version__
from ..config import Config
from ..utils.gpu_probe import detect_gpu
from ..utils.logger import get_logger
from ..utils.api_responses import handle_api_errors, json_success

logger = get_logger('agora.api.status')


def _get_auth_mode():
    """Classify which auth posture the API runs under right now.

    Values:
    - ``"single_user_token"``: ``AGORA_AUTH_TOKEN`` is set; ``/api/*``
      requires it. The ``single_user_`` prefix reflects ADR-0001
      (``docs/decisions/0001-auth-model.md``): v1.0 is a Single-User-only
      simulator, the shared bearer token is the only auth principal.
      Renamed from ``"token"`` 2026-05-04 so operators reading
      ``/api/status`` see immediately that the app does not have a
      multi-user model.
    - ``"anonymous"``: ``AGORA_ALLOW_ANONYMOUS=true`` opt-out is active.
    - ``"open"``: no token, no opt-out, but ``FLASK_DEBUG=true`` (dev).
    - ``"misconfigured"``: no token, no opt-out, no debug — `Config.validate()`
      should have blocked this; we surface it loudly so an operator notices.

    Operators monitor this via backend.auth_mode to confirm
    that production is on ``"single_user_token"`` and not silently in one
    of the open modes.
    """
    if os.environ.get("AGORA_AUTH_TOKEN", "").strip():
        return "single_user_token"
    if os.environ.get("AGORA_ALLOW_ANONYMOUS", "false").lower() in ("true", "1", "yes"):
        return "anonymous"
    if os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes"):
        return "open"
    return "misconfigured"


def _get_backend_status():
    """Get backend health, version, and active auth mode.

    ``allow_small_sim`` mirrors the ``AGORA_ALLOW_SMALL_SIM`` env-var so the
    frontend can adjust the persona-slider lower bound dynamically instead of
    letting the user submit a run that the simulation_config_generator's
    persona-quota validator rejects with a hard 422.
    """
    return {
        "ok": True,
        "version": __version__,
        "auth_mode": _get_auth_mode(),
        # Exakter Vergleich gegen "1" — kein .strip() — damit die UI das
        # gleiche Bit sieht wie der Validator in simulation_config_generator
        # (_validate_persona_quota nutzt ebenfalls `!= "1"` ohne strip).
        "allow_small_sim": os.environ.get("AGORA_ALLOW_SMALL_SIM") == "1",
    }


def _get_neo4j_status():
    """Check Neo4j connectivity."""
    storage = current_app.extensions.get('neo4j_storage')

    if storage is None:
        return {
            "reachable": False,
            "error": current_app.extensions.get('neo4j_storage_error') or "Storage not initialized",
            "uri": Config.NEO4J_URI,
        }

    try:
        # Go through the storage's public probe so the fork-reset
        # lazy-reconnect path is honored. Reaching into ``storage._driver``
        # directly would crash with "'NoneType' object has no attribute
        # 'verify_connectivity'" right after a gunicorn worker fork.
        storage.verify_connectivity()
        last_success = getattr(storage, 'last_success_ts', None)
        return {
            "reachable": True,
            "error": None,
            "uri": Config.NEO4J_URI,
            "is_connected": getattr(storage, 'is_connected', True),
            "last_success_ts": last_success.isoformat() if last_success else None,
        }
    except Exception as e:
        last_error = getattr(storage, 'last_error', None) or e
        return {
            "reachable": False,
            "error": str(last_error),
            "uri": Config.NEO4J_URI,
            "is_connected": getattr(storage, 'is_connected', False),
            "last_success_ts": (storage.last_success_ts.isoformat()
                                if getattr(storage, 'last_success_ts', None) else None),
        }


def _get_ollama_status():
    """Check Ollama availability and list models."""
    # Derive the Ollama base URL from the OpenAI-style LLM_BASE_URL
    # ("http://host:11434/v1" → "http://host:11434"); fall back to env if odd.
    base = (Config.LLM_BASE_URL or '').rstrip('/')
    if base.endswith('/v1'):
        base = base[:-3]
    if not base:
        base = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')

    result = {
        "reachable": False,
        "base_url": base,
        "models_available": [],
        "default_model": Config.LLM_MODEL_NAME,
        "error": None,
    }

    try:
        resp = requests.get(f"{base}/api/tags", timeout=2.5)
        resp.raise_for_status()
        payload = resp.json() or {}

        models = []
        for m in payload.get('models', []) or []:
            name = m.get('name')
            if name:
                models.append(name)

        result["reachable"] = True
        result["models_available"] = models
    except Exception as e:
        result["error"] = str(e)
        logger.debug(f"Could not reach Ollama at {base}: {e}")

    return result


def _get_disk_status():
    """Check disk usage for uploads directory."""
    uploads_path = os.path.join(os.path.dirname(__file__), '../../uploads')
    uploads_path = os.path.abspath(uploads_path)

    try:
        usage = shutil.disk_usage(uploads_path)
        return {
            "uploads": {
                "path": uploads_path,
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "used_pct": round((usage.used / usage.total * 100), 2) if usage.total > 0 else 0,
            }
        }
    except Exception as e:
        logger.warning(f"Could not check disk usage: {e}")
        return {
            "uploads": {
                "path": uploads_path,
                "total_bytes": None,
                "free_bytes": None,
                "used_pct": None,
                "error": str(e),
            }
        }


@status_bp.route('', methods=['GET'])
@handle_api_errors
def get_status():
    """
    Unified status endpoint.

    Returns health information for all system components in a single request:
    - backend: version and operational status
    - neo4j: connectivity and URI
    - ollama: reachability, available models, and default model
    - disk: usage statistics for the uploads directory
    - timestamp: ISO-8601 UTC timestamp

    No component failure causes a 5xx error — all checks are defensive.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        gpu = detect_gpu()
    except Exception as e:  # detect_gpu is documented to never raise, but be defensive.
        logger.debug(f"GPU probe failed unexpectedly: {e}")
        gpu = {"nvidia_smi_available": False, "ollama_uses_gpu": None, "hints": [f"probe error: {e}"]}

    # json_success normally wraps data in "data" field.
    # The original endpoint returned the dict directly at top level.
    # To preserve this, we can pass the dict as extra arguments or just use json_success's behavior
    # Actually, original return was:
    # return jsonify({
    #     "backend": _get_backend_status(),
    #     ...
    # }), 200

    # json_success(data=None, **extra) -> {"success": True, **extra}

    return json_success(
        backend=_get_backend_status(),
        neo4j=_get_neo4j_status(),
        ollama=_get_ollama_status(),
        disk=_get_disk_status(),
        gpu=gpu,
        timestamp=timestamp
    )
