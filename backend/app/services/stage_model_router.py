"""
Stage Model Router.
Resolve(run_id, stage_id, runtime_cfg) -> ResolvedRoute.
"""

from datetime import datetime
from typing import Optional
from ..contracts.llm_routing_contract import (
    RuntimeLlmRouting,
    ResolvedRoute,
    StageId
)
from .runtime_run_config import RuntimeRunConfig
from .secret_resolver import SecretResolver
from ..utils.logger import get_logger

logger = get_logger("agora.stage_model_router")

class StageModelRouter:
    """Resolves the LLM route for a given stage."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.config_service = RuntimeRunConfig(run_id)

    def resolve(self, stage_id: StageId, runtime_cfg: Optional[RuntimeLlmRouting] = None) -> ResolvedRoute:
        """Resolve route for a stage, using snapshot if it exists."""
        # 1. Check for existing snapshot (locked-for-execution)
        snapshot = self.config_service.load_stage_snapshot(stage_id)
        if snapshot:
            return ResolvedRoute.model_validate(snapshot)

        # 2. Resolve from runtime config
        cfg = runtime_cfg or self.config_service.load_config()
        route = cfg.stage_overrides.get(stage_id) or cfg.global_default
        base_url = route.provider_options.get("base_url") if route.provider_options else None

        # 3. Create new snapshot (but don't persist yet - caller should do that on stage start)
        resolver = SecretResolver()
        resolved = ResolvedRoute(
            stage=stage_id,
            provider_id=route.provider_id,
            model=route.model,
            base_url_sanitized=resolver.sanitize_url(base_url),
            reasoning_effort=route.reasoning_effort,
            routing_version=cfg.routing_version,
            provider_options=route.provider_options,
            started_at=datetime.now().isoformat()
        )
        return resolved

    def lock_stage(self, stage_id: StageId, resolved_route: ResolvedRoute) -> None:
        """Lock the route for a stage by persisting the snapshot."""
        self.config_service.save_stage_snapshot(stage_id, resolved_route.model_dump(mode="json"))
