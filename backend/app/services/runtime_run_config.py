"""
Runtime Run Configuration Service.
Handle persistence of runtime_llm_routing.json and stage snapshots.
"""

import os
import json
import tempfile
from typing import Optional, Dict, Any
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, StageId
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from .secret_resolver import SecretResolver

logger = get_logger("agora.runtime_run_config")


def _write_json_atomic(path: str, payload: Any) -> None:
    """Write JSON atomically without depending on adapter-only json_io."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-runtime-routing-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

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
        default_route = StageLLMRoute(
            provider_id="ollama_local",
            model=Config.LLM_MODEL_NAME,
            base_url=Config.LLM_BASE_URL
        )
        return RuntimeLlmRouting(default_route=default_route)

    def load_stage_snapshot(self, stage_id: StageId) -> Optional[Dict[str, Any]]:
        """Load stage-specific LLM route snapshot."""
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return None

    def save_stage_snapshot(self, stage_id: StageId, snapshot: Dict[str, Any]) -> None:
        """Persist stage-specific LLM route snapshot once.

        Stage snapshots are execution locks. They are created atomically and
        never overwritten, so a later routing update cannot alter a stage that
        has already started.
        """
        os.makedirs(self.stages_dir, exist_ok=True)
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")
        if os.path.exists(path):
            return

        # Ensure no secrets in snapshot
        snapshot = self._sanitize_deep(snapshot)

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            return
        with os.fdopen(fd, "w") as f:
            json.dump(snapshot, f, indent=2)
            f.write("\n")

    def _sanitize_deep(self, data: Any) -> Any:
        """Recursively remove keys that might contain secrets."""
        if isinstance(data, dict):
            return {
                k: self._sanitize_deep(v)
                for k, v in data.items()
                if k.lower() not in ("api_key", "apikey", "secret", "password", "token")
            }
        if isinstance(data, list):
            return [self._sanitize_deep(v) for v in data]
        return data

    def _sanitize_urls(self, data: Any) -> Any:
        """Strip credentials/query data from persisted URL fields."""
        if isinstance(data, dict):
            sanitized = {}
            resolver = SecretResolver()
            for key, value in data.items():
                if key in {"base_url", "base_url_sanitized"} and isinstance(value, str):
                    sanitized[key] = resolver.sanitize_url(value)
                else:
                    sanitized[key] = self._sanitize_urls(value)
            return sanitized
        if isinstance(data, list):
            return [self._sanitize_urls(v) for v in data]
        return data

    def save_config(self, config: RuntimeLlmRouting) -> None:
        """Persist runtime configuration."""
        os.makedirs(self.run_dir, exist_ok=True)
        # Monotonicity check for routing_version should happen in service/api layer

        # Sanitize deep before saving
        data = self._sanitize_deep(self._sanitize_urls(config.model_dump(mode="json")))

        _write_json_atomic(self.config_path, data)
