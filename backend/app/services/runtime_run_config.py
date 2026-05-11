"""
Runtime Run Configuration Service.
Handle persistence of runtime_llm_routing.json and stage snapshots.
"""

import os
import json
from typing import Optional, Dict, Any
from ..contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, StageId
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from .secret_resolver import SecretResolver

logger = get_logger("agora.runtime_run_config")

_SECRET_RESOLVER = SecretResolver()
_SECRET_KEYS = frozenset(("api_key", "apikey", "secret", "password", "token"))

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
        """Persist stage-specific LLM route snapshot with defensive sanitization."""
        os.makedirs(self.stages_dir, exist_ok=True)
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")

        snapshot = self._sanitize_deep(snapshot)

        with open(path, "w") as f:
            json.dump(snapshot, f, indent=2)

    def _sanitize_deep(self, data: Any) -> Any:
        """Recursively strip secret-bearing keys and sanitize URLs in snapshots.

        The ``SecretResolver`` is reused from a module-level singleton — the
        previous implementation instantiated it per recursive call, which was
        wasteful for nested provider_options dicts.
        """
        if isinstance(data, dict):
            cleaned: Dict[str, Any] = {}
            for k, v in data.items():
                if k.lower() in _SECRET_KEYS:
                    continue
                if k == "base_url" and isinstance(v, str):
                    cleaned[k] = _SECRET_RESOLVER.sanitize_url(v)
                    continue
                cleaned[k] = self._sanitize_deep(v)
            return cleaned
        if isinstance(data, list):
            return [self._sanitize_deep(v) for v in data]
        return data

    def save_config(self, config: RuntimeLlmRouting) -> None:
        """Persist runtime configuration with defensive sanitization."""
        os.makedirs(self.run_dir, exist_ok=True)

        data = self._sanitize_deep(config.model_dump(mode="json"))

        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)
