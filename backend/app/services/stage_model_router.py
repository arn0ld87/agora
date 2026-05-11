"""
Stage Model Router.
Resolve(run_id, stage_id, runtime_cfg) -> ResolvedRoute.
"""

from datetime import datetime
from typing import Optional
from ..contracts.llm_routing_contract import (
    RuntimeLlmRouting,
    ResolvedRoute,
    StageId,
    StageLLMRoute,
)
from .runtime_run_config import RuntimeRunConfig
from .llm_runtime import RuntimeLlmConfig
from ..utils.logger import get_logger

logger = get_logger("agora.stage_model_router")


def build_default_route(
    llm_runtime: RuntimeLlmConfig,
    model: str,
    fallback_base_url: Optional[str],
) -> StageLLMRoute:
    """Map a UI-provided ``RuntimeLlmConfig`` to a ``StageLLMRoute``.

    Called from the API boundary (graph/report/simulation) to wire the
    frontend's optional provider override into the routing contract.
    ``model`` is the already-resolved model string (override → project
    default → server default); ``fallback_base_url`` is used when
    ``llm_runtime`` is not enabled (typically ``Config.LLM_BASE_URL``).
    """
    if llm_runtime.enabled:
        return StageLLMRoute(
            provider_id=llm_runtime.provider,
            model=model,
            base_url=llm_runtime.base_url,
        )
    return StageLLMRoute(
        provider_id="ollama_local",
        model=model,
        base_url=fallback_base_url,
    )


def update_default_route(
    run_id: str,
    llm_runtime: RuntimeLlmConfig,
    llm_model_override: Optional[str],
) -> None:
    """Bump ``default_route`` of a persisted runtime config (incrementing version).

    No-op when neither a provider payload nor a model override is supplied.
    Used by the graph-build endpoint to re-apply the frontend's per-request
    LLM choice to an existing project routing config.
    """
    if not (llm_runtime.enabled or llm_model_override):
        return

    config_service = RuntimeRunConfig(run_id)
    config = config_service.load_config()
    if llm_runtime.enabled:
        config.default_route = build_default_route(
            llm_runtime,
            model=llm_model_override or config.default_route.model,
            fallback_base_url=config.default_route.base_url,
        )
    elif llm_model_override:
        config.default_route.model = llm_model_override

    config.routing_version += 1
    config_service.save_config(config)

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
        route = cfg.stage_overrides.get(stage_id) or cfg.default_route

        # 3. Create new snapshot (but don't persist yet - caller should do that on stage start).
        # ``base_url`` carries the runtime URL untouched; sanitization happens when the
        # snapshot is written to disk or emitted via the observability logger.
        resolved = ResolvedRoute(
            stage=stage_id,
            provider_id=route.provider_id,
            model=route.model,
            base_url=route.base_url,
            reasoning_effort=route.reasoning_effort,
            routing_version=cfg.routing_version,
            provider_options=route.provider_options,
            started_at=datetime.now().isoformat()
        )
        return resolved

    def lock_stage(self, stage_id: StageId, resolved_route: ResolvedRoute) -> None:
        """Lock the route for a stage by persisting the snapshot."""
        self.config_service.save_stage_snapshot(stage_id, resolved_route.model_dump(mode="json"))
