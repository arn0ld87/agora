"""
Status monitoring endpoint — unified health check for all system components.
Returns backend version, Neo4j reachability, Ollama availability, and disk usage in a single request.
"""

import os
import shutil
from datetime import datetime, timezone
from flask import current_app, jsonify
import requests

from . import status_bp
from ..config import Config
from ..utils.gpu_probe import detect_gpu
from ..utils.logger import get_logger

logger = get_logger('agora.api.status')


def _get_backend_status():
    """Get backend health and version."""
    return {
        "ok": True,
        "version": "0.4.0",
    }


def _get_neo4j_status():
    """Check Neo4j connectivity."""
    storage = current_app.extensions.get('neo4j_storage')

    if storage is None:
        return {
            "reachable": False,
            "error": "Storage not initialized",
            "uri": Config.NEO4J_URI,
        }

    try:
        # Verify connectivity using the driver's verify_connectivity method
        storage._driver.verify_connectivity()
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

    return jsonify({
        "backend": _get_backend_status(),
        "neo4j": _get_neo4j_status(),
        "ollama": _get_ollama_status(),
        "disk": _get_disk_status(),
        "gpu": gpu,
        "timestamp": timestamp,
    }), 200
