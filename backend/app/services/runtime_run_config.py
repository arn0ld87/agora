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

logger = get_logger("agora.runtime_run_config")

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
        provider_options: Dict[str, Any] = {}
        if Config.LLM_BASE_URL:
            provider_options["base_url"] = Config.LLM_BASE_URL

        global_default = StageLLMRoute(
            provider_id="ollama_local",
            model=Config.LLM_MODEL_NAME,
            provider_options=provider_options,
        )
        return RuntimeLlmRouting(global_default=global_default)

    def save_config(self, config: RuntimeLlmRouting) -> None:
        """Persist runtime configuration."""
        os.makedirs(self.run_dir, exist_ok=True)
        # Monotonicity check for routing_version should happen in service/api layer
        with open(self.config_path, "w") as f:
            f.write(config.model_dump_json(indent=2))

    def load_stage_snapshot(self, stage_id: StageId) -> Optional[Dict[str, Any]]:
        """Load stage-specific LLM route snapshot."""
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return None

    def save_stage_snapshot(self, stage_id: StageId, snapshot: Dict[str, Any]) -> None:
        """Persist stage-specific LLM route snapshot."""
        os.makedirs(self.stages_dir, exist_ok=True)
        path = os.path.join(self.stages_dir, f"{stage_id}_llm_route_snapshot.json")
        # Ensure no secrets in snapshot
        if "api_key" in snapshot:
            snapshot = dict(snapshot)
            del snapshot["api_key"]

        with open(path, "w") as f:
            json.dump(snapshot, f, indent=2)
