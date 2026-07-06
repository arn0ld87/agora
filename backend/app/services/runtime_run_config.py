"""
Runtime Run Configuration Service.
Handle persistence of runtime_llm_routing.json and stage snapshots.
"""

import os
import json
import tempfile
from urllib.parse import urlparse, urlunparse
from typing import Optional, Dict, Any
from ..contracts import (
    PROVIDER_GOOGLE,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OPENAI,
    PROVIDER_OPENAI_COMPATIBLE,
)
from ..llm.providers.registry import detect_provider
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, StageId
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger

logger = get_logger("agora.runtime_run_config")

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def _sanitize_url(value: str) -> str:
    """Strip credentials, query params and fragments from persisted URLs."""
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value

    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"

    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


# SSoT (app.llm.providers.registry.detect_provider, mode="http") result ->
# this module's own PROVIDER_* vocabulary. Callers of
# _detect_default_provider_id keep receiving exactly the same four IDs as
# before delegation; only the detection heuristic underneath changed.
_HTTP_DETECTION_TO_PROVIDER_ID = {
    "cloud": PROVIDER_OLLAMA_CLOUD,
    "google": PROVIDER_GOOGLE,
    "openai": PROVIDER_OPENAI,
    # "ollama" (local, e.g. port 11434) and "unknown" both fall back to the
    # generic OpenAI-compatible route, matching this function's previous
    # behavior (it never had a distinct local-Ollama branch).
    "ollama": PROVIDER_OPENAI_COMPATIBLE,
    "unknown": PROVIDER_OPENAI_COMPATIBLE,
}


def _detect_default_provider_id(base_url: Optional[str], model_name: Optional[str]) -> str:
    """Best-effort mapping from legacy server config to routing provider IDs.

    Delegates to the Single Source of Truth (``detect_provider``,
    ``mode="http"``) instead of re-implementing hostname/model heuristics
    here. This fixes two weaknesses of the old inline heuristic (audit
    B6/T4):

    1. Exact hostname equality (``hostname == "ollama.com"``,
       ``hostname == "generativelanguage.googleapis.com"``,
       ``hostname in {"api.openai.com", "openai.com"}``) missed legitimate
       subdomains/variants (e.g. ``eu.api.openai.com``,
       ``some-region.generativelanguage.googleapis.com``); the SSoT's
       substring matching on the base URL recognizes these.
    2. Ollama Cloud tag detection only matched the bare ``:cloud`` suffix
       (``normalized_model.endswith(":cloud")``) and missed size-prefixed
       cloud tags (e.g. ``gpt-oss:20b-cloud``); the SSoT's
       ``_is_ollama_cloud_tag`` recognizes both forms.
    """
    detected = detect_provider(base_url, model_name, mode="http")
    return _HTTP_DETECTION_TO_PROVIDER_ID[detected]


class RuntimeRunConfig:
    """Manages runtime configuration for a run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.run_dir = ArtifactLocator.run_dir(run_id)
        self.config_path = os.path.join(self.run_dir, "runtime_llm_routing.json")
        self.stages_dir = os.path.join(self.run_dir, "stages")

    def load_config(self) -> RuntimeLlmRouting:
        """Load runtime configuration, with legacy fallback."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                data = json.load(f)
                return RuntimeLlmRouting.model_validate(data)

        # Legacy fallback: synthesize from global Config or existing run metadata
        from ..config import Config
        provider_options: Dict[str, Any] = {"base_url": Config.LLM_BASE_URL} if Config.LLM_BASE_URL else {}

        global_default = StageLLMRoute(
            provider_id=_detect_default_provider_id(Config.LLM_BASE_URL, Config.LLM_MODEL_NAME),
            model=Config.LLM_MODEL_NAME,
            provider_options=provider_options,
        )
        return RuntimeLlmRouting(global_default=global_default)

    def save_config(self, config: RuntimeLlmRouting) -> None:
        """Persist runtime configuration."""
        os.makedirs(self.run_dir, exist_ok=True)
        # Monotonicity check for routing_version should happen in service/api layer
        data = self._sanitize_deep(config.model_dump(mode="json", exclude_none=True, exclude_defaults=True))
        self._write_json_atomic(self.config_path, data)

    def load_stage_snapshot(self, stage_id: StageId) -> Optional[Dict[str, Any]]:
        """Load stage-specific LLM route snapshot."""
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return None

    def save_stage_snapshot(self, stage_id: StageId, snapshot: Dict[str, Any]) -> None:
        """Persist stage-specific LLM route snapshot as a write-once lock."""
        os.makedirs(self.stages_dir, exist_ok=True)
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")
        data = self._sanitize_deep(snapshot)
        payload = json.dumps(data, indent=2)

        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")

    def _sanitize_deep(self, data: Any, key: str | None = None) -> Any:
        """Recursively remove secret keys and persisted URL credentials."""
        if isinstance(data, dict):
            sanitized: dict[str, Any] = {}
            for item_key, value in data.items():
                normalized = item_key.lower()
                if normalized in _SECRET_KEYS:
                    continue
                sanitized[item_key] = self._sanitize_deep(value, item_key)
            return sanitized

        if isinstance(data, list):
            return [self._sanitize_deep(value, key) for value in data]

        if isinstance(data, str):
            normalized_key = (key or "").lower()
            if normalized_key.endswith("url") or normalized_key.endswith("_url"):
                return _sanitize_url(data)
            return _sanitize_url(data) if "://" in data else data

        return data

    def _write_json_atomic(self, path: str, data: Any) -> None:
        """Write JSON atomically in the target directory."""
        target_dir = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(prefix=".runtime_llm_routing.", suffix=".tmp", dir=target_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
