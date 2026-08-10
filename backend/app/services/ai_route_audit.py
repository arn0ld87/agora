"""Secret-free, idempotent audit events for resolved AI routes."""

import os
from datetime import datetime, timezone
from typing import Any

from ..contracts.ai_provider_contract import AiRoute
from ..contracts.llm_routing_contract import StageId
from .runtime_run_config import RuntimeRunConfig, _publish_json_once_atomic


def _carried_ai_model_ref_source(route: AiRoute) -> str | None:
    """Die urspruengliche ``AiModelRef.source`` aus dem Legacy-Kanal lesen.

    Defensiv gehalten: das Audit darf an einer Bestandsroute ohne den Schluessel
    nicht scheitern -- ``ai_model_ref_source`` ist ``NotRequired`` und fehlt in
    allen vor Issue #901 geschriebenen Snapshots.
    """
    legacy = route.provider_options.get("__legacy_stage_route__")
    if not isinstance(legacy, dict):
        return None
    return legacy.get("ai_model_ref_source")


def _carried_fallback_reason(route: AiRoute) -> str | None:
    """Den urspruenglichen ``fallback_reason`` aus dem Legacy-Kanal lesen.

    Issue #992: ``resolve_ai_route`` loescht das oberste
    ``AiRoute.fallback_reason`` fuer jeden Slot ausser ``provider_fallback``.
    Eine ``AiModelRef`` mit ``source="fallback"`` landet aber im Stage-/
    Run-Slot -- ihr Grund reist deshalb, analog zu
    ``ai_model_ref_source``, im ``__legacy_stage_route__``-Kanal mit.
    Defensiv gehalten: Bestandssnapshots ohne den Schluessel duerfen das
    Audit nicht scheitern lassen -- ``fallback_reason`` ist im Legacy-Kanal
    ``NotRequired`` und fehlt in allen vor Issue #992 geschriebenen Snapshots.
    """
    legacy = route.provider_options.get("__legacy_stage_route__")
    if not isinstance(legacy, dict):
        return None
    return legacy.get("fallback_reason")


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
            # Issue #901: ``source`` beantwortet, welche Routing-EBENE gewonnen
            # hat -- ``resolve_ai_route`` setzt sie auf den Slot-Namen
            # ("stage_override", "run_override", ...) und verwirft dabei die
            # ``source`` des Kandidaten. Ohne dieses zweite Feld waeren im Audit
            # genau die Faelle wieder ununterscheidbar, die #901 trennen soll:
            # eine bewusste Nutzerwahl ("explicit"), ein Run-Override und ein
            # Provider-Fallback landen alle als "stage_override".
            #
            # Der Wert ueberlebt die Aufloesung, weil resolve_ai_route
            # ``provider_options`` unveraendert kopiert und die Herkunft im
            # ``__legacy_stage_route__``-Kanal mitreist.
            "ai_model_ref_source": _carried_ai_model_ref_source(route),
            "validated_capabilities": dict(route.validated_capabilities),
            "resolved_at": timestamp.astimezone(timezone.utc).isoformat(),
            # Auf ``is None`` geprueft, nicht auf Wahrheitswert: der leere
            # String ist ein gueltiger fallback_reason und darf nicht
            # stillschweigend durch den Legacy-Wert ersetzt werden.
            "fallback_reason": (
                fallback_reason
                if fallback_reason is not None
                else (
                    route.fallback_reason
                    if route.fallback_reason is not None
                    else _carried_fallback_reason(route)
                )
            ),
        }
        path = os.path.join(
            self.runtime.stages_dir, f"{stage_id}_routing_resolved.json"
        )
        return _publish_json_once_atomic(path, event)
