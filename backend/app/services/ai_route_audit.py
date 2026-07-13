"""Secret-free, idempotent audit events for resolved AI routes."""

import os
from datetime import datetime, timezone
from typing import Any

from ..contracts.ai_provider_contract import AiRoute
from ..contracts.llm_routing_contract import StageId
from .runtime_run_config import RuntimeRunConfig, _publish_json_once_atomic


class AiRouteAudit:
    def __init__(self, run_id: str):
        self.runtime = RuntimeRunConfig(run_id)

    def record_routing_resolved(
        self,
        stage_id: StageId,
        route: AiRoute,
        *,
        fallback_reason: str | None = None,
        resolved_at: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = resolved_at or route.resolved_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        event = {
            "event": "routing_resolved",
            "stage": stage_id,
            "provider_connection_id": route.provider_connection_id,
            "model_id": route.model_id,
            "source": route.source,
            "validated_capabilities": dict(route.validated_capabilities),
            "resolved_at": timestamp.astimezone(timezone.utc).isoformat(),
            "fallback_reason": (
                fallback_reason
                if fallback_reason is not None
                else route.fallback_reason
            ),
        }
        path = os.path.join(
            self.runtime.stages_dir, f"{stage_id}_routing_resolved.json"
        )
        return _publish_json_once_atomic(path, event)
