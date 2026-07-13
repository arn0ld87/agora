"""Pure, deterministic resolution of explicit AI route candidates."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime

from app.contracts.ai_provider_contract import AiRoute, RouteSource


class AiRouteResolutionError(Exception):
    """Base class for typed route-resolution failures."""


class NoAiRouteCandidateError(AiRouteResolutionError):
    """Raised when no candidate exists at any supported resolution level."""

    def __init__(self, required_capabilities: Collection[str]) -> None:
        self.required_capabilities = tuple(sorted(set(required_capabilities)))
        super().__init__("No AI route candidate is configured")


class AiRouteCapabilityMismatchError(AiRouteResolutionError):
    """Raised when the highest-priority candidate lacks required capabilities."""

    def __init__(
        self,
        *,
        source: RouteSource,
        candidate: AiRoute,
        missing_capabilities: Collection[str],
    ) -> None:
        self.source = source
        self.candidate = candidate
        self.missing_capabilities = tuple(sorted(set(missing_capabilities)))
        joined = ", ".join(self.missing_capabilities)
        super().__init__(f"AI route candidate from {source} lacks capabilities: {joined}")


def resolve_ai_route(
    *,
    stage_override: AiRoute | None = None,
    run_override: AiRoute | None = None,
    project_route: AiRoute | None = None,
    workspace_route: AiRoute | None = None,
    provider_fallback: AiRoute | None = None,
    required_capabilities: Collection[str] = (),
    resolved_at: datetime,
) -> AiRoute:
    """Resolve explicit candidates in strict Stage > Run > Project > Workspace order."""

    candidates: tuple[tuple[RouteSource, AiRoute | None], ...] = (
        ("stage_override", stage_override),
        ("run_override", run_override),
        ("project", project_route),
        ("workspace", workspace_route),
        ("provider_fallback", provider_fallback),
    )
    selected = next(
        ((source, candidate) for source, candidate in candidates if candidate is not None),
        None,
    )
    if selected is None:
        raise NoAiRouteCandidateError(required_capabilities)

    source, candidate = selected
    missing_capabilities = {
        capability
        for capability in required_capabilities
        if candidate.validated_capabilities.get(capability) != "supported"
    }
    if missing_capabilities:
        raise AiRouteCapabilityMismatchError(
            source=source,
            candidate=candidate,
            missing_capabilities=missing_capabilities,
        )

    data = candidate.model_dump(mode="python")
    data.update(
        source=source,
        resolved_at=resolved_at,
        fallback_reason=(
            candidate.fallback_reason if source == "provider_fallback" else None
        ),
    )
    return AiRoute.model_validate(data)


__all__ = [
    "AiRouteCapabilityMismatchError",
    "AiRouteResolutionError",
    "NoAiRouteCandidateError",
    "resolve_ai_route",
]
