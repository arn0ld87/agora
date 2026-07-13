from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.contracts.ai_provider_contract import AiRoute
from app.services.ai_route_resolver import (
    AiRouteCapabilityMismatchError,
    AiRouteResolutionError,
    NoAiRouteCandidateError,
    resolve_ai_route,
)


RESOLVED_AT = datetime(2026, 7, 13, 10, 30, tzinfo=timezone.utc)


def _route(
    name: str,
    *,
    capabilities: dict[str, str] | None = None,
    fallback_reason: str | None = None,
) -> AiRoute:
    data = {
        "provider_connection_id": f"provider-{name}",
        "model_id": f"model-{name}",
        "source": "default",
        "validated_capabilities": capabilities or {"chat": "supported"},
    }
    if fallback_reason is not None:
        data["fallback_reason"] = fallback_reason
    return AiRoute.model_validate(data)


@pytest.mark.parametrize(
    ("present", "expected_source"),
    [
        (
            ("stage_override", "run_override", "project", "workspace", "provider_fallback"),
            "stage_override",
        ),
        (("run_override", "project", "workspace", "provider_fallback"), "run_override"),
        (("project", "workspace", "provider_fallback"), "project"),
        (("workspace", "provider_fallback"), "workspace"),
        (("provider_fallback",), "provider_fallback"),
    ],
)
def test_resolver_uses_strict_candidate_precedence(
    present: tuple[str, ...],
    expected_source: str,
) -> None:
    candidates = {
        name: _route(
            name,
            fallback_reason=(
                "No configured route was available" if name == "provider_fallback" else None
            ),
        )
        for name in present
    }

    resolved = resolve_ai_route(
        stage_override=candidates.get("stage_override"),
        run_override=candidates.get("run_override"),
        project_route=candidates.get("project"),
        workspace_route=candidates.get("workspace"),
        provider_fallback=candidates.get("provider_fallback"),
        required_capabilities={"chat"},
        resolved_at=RESOLVED_AT,
    )

    assert resolved.source == expected_source
    assert resolved.provider_connection_id == f"provider-{expected_source}"
    assert resolved.model_id == f"model-{expected_source}"
    assert resolved.resolved_at == RESOLVED_AT


def test_resolver_is_deterministic_and_does_not_mutate_candidate() -> None:
    candidate = _route("project")
    arguments = {
        "project_route": candidate,
        "required_capabilities": {"chat"},
        "resolved_at": RESOLVED_AT,
    }

    first = resolve_ai_route(**arguments)
    second = resolve_ai_route(**arguments)

    assert first == second
    assert first is not candidate
    assert candidate.source == "default"
    assert candidate.resolved_at is None


def test_resolver_raises_typed_error_when_no_candidate_exists() -> None:
    with pytest.raises(NoAiRouteCandidateError) as raised:
        resolve_ai_route(
            required_capabilities={"chat"},
            resolved_at=RESOLVED_AT,
        )

    assert isinstance(raised.value, AiRouteResolutionError)
    assert raised.value.required_capabilities == ("chat",)


def test_resolver_raises_typed_error_for_capability_mismatch() -> None:
    candidate = _route(
        "stage_override",
        capabilities={
            "chat": "supported",
            "json_schema": "unsupported",
            "tool_calling": "unknown",
        },
    )

    with pytest.raises(AiRouteCapabilityMismatchError) as raised:
        resolve_ai_route(
            stage_override=candidate,
            provider_fallback=_route(
                "provider_fallback",
                capabilities={
                    "chat": "supported",
                    "json_schema": "supported",
                    "tool_calling": "supported",
                },
                fallback_reason="Stage override lacks required capabilities",
            ),
            required_capabilities={"chat", "json_schema", "tool_calling"},
            resolved_at=RESOLVED_AT,
        )

    assert isinstance(raised.value, AiRouteResolutionError)
    assert raised.value.source == "stage_override"
    assert raised.value.missing_capabilities == ("json_schema", "tool_calling")
    assert raised.value.candidate is candidate


def test_resolver_treats_absent_capability_as_mismatch() -> None:
    candidate = _route("workspace", capabilities={"chat": "supported"})

    with pytest.raises(AiRouteCapabilityMismatchError) as raised:
        resolve_ai_route(
            workspace_route=candidate,
            required_capabilities={"vision"},
            resolved_at=RESOLVED_AT,
        )

    assert raised.value.missing_capabilities == ("vision",)
