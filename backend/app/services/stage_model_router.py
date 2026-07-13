"""
Stage Model Router.
Resolve(run_id, stage_id, runtime_cfg) -> ResolvedRoute.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import ValidationError
from ..contracts.ai_provider_contract import AiRoute
from ..contracts.llm_routing_contract import (
    RuntimeLlmRouting,
    ResolvedRoute,
    StageId
)
from .runtime_run_config import RuntimeRunConfig, _detect_default_provider_id
from .secret_resolver import SecretResolver
from .ai_route_audit import AiRouteAudit
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
            return self._resolved_from_snapshot(stage_id, snapshot)
        canonical_snapshot = self.config_service.load_ai_route_snapshot(stage_id)
        if canonical_snapshot is not None:
            return self._resolved_from_snapshot(
                stage_id, canonical_snapshot.model_dump(mode="json")
            )

        # 2. Resolve from runtime config
        cfg = runtime_cfg or self.config_service.load_config()
        route = cfg.stage_overrides.get(stage_id) or cfg.global_default
        base_url = (route.provider_options or {}).get("base_url")

        # 3. Create new snapshot (but don't persist yet - caller should do that on stage start)
        resolver = SecretResolver()
        # Defensive: provider_id darf nicht None sein (ResolvedRoute erwartet str).
        # Fallback auf Best-Effort-Detection aus base_url / model.
        provider_id = route.provider_id or _detect_default_provider_id(base_url, route.model)

        resolved = ResolvedRoute(
            stage=stage_id,
            provider_id=provider_id,
            model=route.model or "",
            base_url_sanitized=resolver.sanitize_url(base_url),
            reasoning_effort=route.reasoning_effort,
            routing_version=cfg.routing_version,
            provider_options=route.provider_options,
            started_at=datetime.now(timezone.utc).isoformat()
        )
        return resolved

    def lock_stage(self, stage_id: StageId, resolved_route: ResolvedRoute) -> ResolvedRoute:
        """Lock the route for a stage by persisting the snapshot."""
        winner = self.config_service.save_stage_snapshot(
            stage_id, resolved_route.model_dump(mode="json")
        )
        stored = ResolvedRoute.model_validate(winner)
        config = self.config_service.load_config()
        source = "stage_override" if stage_id in config.stage_overrides else "legacy"
        canonical = self.config_service.save_ai_route_snapshot(
            stage_id,
            AiRoute(
                stage=stage_id,
                provider_connection_id=stored.provider_id,
                model_id=stored.model,
                source=source,
                resolved_at=stored.started_at,
            ),
        )
        AiRouteAudit(self.run_id).record_routing_resolved(stage_id, canonical)
        return self._resolved_from_snapshot(stage_id, winner)

    def _resolved_from_snapshot(
        self, stage_id: StageId, snapshot: dict[str, object]
    ) -> ResolvedRoute:
        try:
            return ResolvedRoute.model_validate(snapshot)
        except ValidationError:
            route = AiRoute.model_validate(snapshot)
            options = dict(route.provider_options)
            legacy_options = options.pop("__legacy_stage_route__", None) or {}
            base_url = options.get("base_url")
            provider_id = route.provider_connection_id or _detect_default_provider_id(
                base_url, route.model_id
            )
            return ResolvedRoute(
                stage=route.stage or stage_id,
                provider_id=provider_id,
                model=route.model_id or "",
                base_url_sanitized=SecretResolver().sanitize_url(base_url),
                reasoning_effort=legacy_options.get("reasoning_effort") or "none",
                routing_version=1,
                provider_options=options,
                started_at=getattr(route, "resolved_at", None),
            )
