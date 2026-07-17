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
    PROVIDER_MINIMAX,
    PROVIDER_OLLAMA_CLOUD,
    PROVIDER_OPENAI,
    PROVIDER_OPENAI_COMPATIBLE,
)
from ..llm.providers.registry import detect_provider
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, StageId
from ..contracts.ai_provider_contract import AiRoute
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


def _publish_json_once_atomic(path: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Atomically publish JSON without replacing an existing winner."""
    target_dir = os.path.dirname(path)
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=target_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_path, path)
        except FileExistsError:
            pass
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
    "minimax": PROVIDER_MINIMAX,
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

    def save_stage_snapshot(self, stage_id: StageId, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Persist stage-specific LLM route snapshot as a write-once lock."""
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")
        data = self._sanitize_deep(snapshot)
        return _publish_json_once_atomic(path, data)

    def load_ai_route_snapshot(self, stage_id: StageId) -> Optional[AiRoute]:
        """Read canonical snapshots and project legacy ResolvedRoute snapshots."""
        canonical_path = os.path.join(
            self.stages_dir, f"{stage_id}_ai_route_snapshot.json"
        )
        if os.path.exists(canonical_path):
            with open(canonical_path, "r", encoding="utf-8") as handle:
                return AiRoute.model_validate(json.load(handle))

        snapshot = self.load_stage_snapshot(stage_id)
        if snapshot is None:
            return None
        try:
            return AiRoute.model_validate(snapshot)
        except ValueError:
            return AiRoute(
                stage=snapshot.get("stage", stage_id),
                provider_connection_id=snapshot.get("provider_id"),
                model_id=snapshot.get("model"),
                source="legacy",
            )

    def save_ai_route_snapshot(self, stage_id: StageId, route: AiRoute) -> AiRoute:
        """Publish a canonical route and return the stored first-writer winner.

        The full field set is persisted (incl. ``fallback_reason: null`` and
        ``resolved_at``) so the snapshot is self-describing and stays aligned
        with the routing audit. Secrets stay out via ``_sanitize_deep``
        (secret keys dropped, URLs credential-stripped); only public
        provider options such as ``base_url``/``num_ctx`` survive. The
        first-writer-wins publish stays atomic.
        """
        path = os.path.join(self.stages_dir, f"{stage_id}_ai_route_snapshot.json")
        winner = _publish_json_once_atomic(
            path,
            self._sanitize_deep(route.model_dump(mode="json")),
        )
        return AiRoute.model_validate(winner)

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
