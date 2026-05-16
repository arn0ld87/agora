"""Active LLM Config API.

Persistiert die aktiv ausgewaehlte Provider/Modell-Kombination in
``backend/instance/active_llm_config.json``. Wird von ``LLMClient``
mit ``use_active_config=True`` gelesen, wenn kein expliziter Provider
gesetzt ist.

Endpoints:
- GET /api/llm/active-config -> aktuelle Auswahl (oder leeres dict)
- PUT /api/llm/active-config {"provider_id": "...", "model": "..."}
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from flask import request

from . import llm_bp
from ..services.llm_provider_registry import LlmProviderRegistry
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

logger = get_logger("agora.api.llm_active")

_provider_registry = LlmProviderRegistry()


def _instance_dir() -> Path:
    here = Path(__file__).resolve()
    # backend/app/api/ -> backend/instance/
    return here.parents[2] / "instance"


def _config_path() -> Path:
    return _instance_dir() / "active_llm_config.json"


def load_active_config() -> Dict[str, Any]:
    """Read the persisted active config; returns {} if not set."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read active LLM config: %s", exc)
        return {}


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".active_llm_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_active_config(provider_id: str, model: str, base_url: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "provider_id": provider_id,
        "model": model,
    }
    if base_url:
        payload["base_url"] = base_url
    _atomic_write(_config_path(), payload)
    return payload


@llm_bp.route("/active-config", methods=["GET"])
@handle_api_errors(logger=logger)
def get_active_config():
    """Return the active provider/model selection."""
    cfg = load_active_config()
    return json_success(cfg)


@llm_bp.route("/active-config", methods=["PUT"])
@handle_api_errors(logger=logger)
def put_active_config():
    """Set the active provider/model selection.

    Sicherheits-Hinweis: ``base_url`` wird NICHT aus dem Request-Body gelesen.
    Sie wird ausschliesslich aus der server-seitigen Provider-Registry
    abgeleitet, damit ein authentifizierter, aber boeswilliger Client die
    LLM-Aufrufe nicht via SSRF-Vektor auf einen kontrollierten Host umlenken
    kann (Gemini-Code-Assist Review PR #478).
    """
    payload = request.get_json(silent=True) or {}
    provider_id = (payload.get("provider_id") or "").strip()
    model = (payload.get("model") or "").strip()

    if not provider_id:
        return json_error("provider_id is required", status=400, code="invalid_request")
    if not model:
        return json_error("model is required", status=400, code="invalid_request")

    providers = _provider_registry.get_providers()
    provider = next((p for p in providers if p.id == provider_id), None)
    if not provider:
        return json_error(f"Unknown provider: {provider_id}", status=404, code="provider_not_found")

    saved = save_active_config(provider_id, model, provider.base_url)
    logger.info("Active LLM config updated: provider=%s model=%s", provider_id, model)
    return json_success(saved)
