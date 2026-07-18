"""Canonical AI provider, model and route contracts plus legacy adapters."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    BeforeValidator,
    model_validator,
)
from typing_extensions import TypedDict

from .llm_profile_contract import LlmProfile
from .llm_routing_contract import (
    ModelEntry,
    ProviderDescriptor,
    ReasoningEffort,
    StageId,
    StageLLMRoute,
)
from .provider_types import ProviderConnectionKind

_STRICT = ConfigDict(extra="forbid")
_LEGACY_ROUTE_OPTIONS_KEY = "__legacy_stage_route__"
_PUBLIC_BASE_URL_PATTERN = (
    r"^https?://(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])"
    r"(?::[0-9]{1,5})?(?:/[^\s?#]*)?$"
)


def _reject_unsupported_connection_provider(value: object) -> object:
    if value == "opencode_go":
        raise ValueError("opencode_go is unsupported for provider connections in this slice")
    return value


ProviderConnectionProviderKind = Annotated[
    ProviderConnectionKind,
    BeforeValidator(_reject_unsupported_connection_provider),
]
# Muss dem Field(pattern=...) entsprechen, damit Validator und Feld
# deckungsgleich bleiben und die Legacy-Sanitizer nie URLs durchreichen,
# die die Modell-Konstruktion anschließend doch ablehnt.
_PUBLIC_BASE_URL_RE = re.compile(_PUBLIC_BASE_URL_PATTERN)

CapabilityState = Literal["supported", "unsupported", "unknown"]
ModelSource = Literal["live", "cached", "fallback", "custom"]
LocalOrCloud = Literal["local", "cloud", "unknown"]
ProviderTransport = Literal["http", "local"]
ProviderAuthMode = Literal["none", "api_key", "oauth", "session"]
ProviderStatus = Literal["unknown", "connected", "degraded", "disconnected", "error"]
ModelStatus = Literal["unknown", "available", "unavailable", "deprecated"]
RouteSource = Literal[
    "default",
    "profile",
    "stage_override",
    "run_override",
    "project",
    "workspace",
    "provider_fallback",
    "runtime",
    "legacy",
]


def _validate_public_base_url(value: str) -> str:
    if _PUBLIC_BASE_URL_RE.match(value) is None:
        raise ValueError("base_url must be a public HTTP(S) base URL")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("base_url must be a public HTTP(S) base URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base_url must be a public HTTP(S) base URL")
    hostname = parsed.hostname.lower()
    if hostname == "localhost":
        raise ValueError("base_url must be a public HTTP(S) base URL")
    try:
        address = ip_address(hostname)
    except ValueError:
        # DNS-Namen werden nicht aufgeloest: Der Validator darf keinen
        # netzwerkabhaengigen SSRF-Check vortaeuschen.
        return value
    if not address.is_global:
        raise ValueError("base_url must be a public HTTP(S) base URL")
    return value


PublicBaseUrl = Annotated[
    str,
    Field(pattern=_PUBLIC_BASE_URL_PATTERN),
    AfterValidator(_validate_public_base_url),
]


def _validate_local_ollama_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("base_url must be a loopback HTTP(S) URL for local Ollama") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base_url must be a loopback HTTP(S) URL for local Ollama")
    try:
        is_loopback = parsed.hostname == "localhost" or ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise ValueError("base_url must be a loopback HTTP(S) URL for local Ollama")
    return value


LocalOllamaBaseUrl = Annotated[
    str,
    Field(pattern=_PUBLIC_BASE_URL_PATTERN),
    AfterValidator(_validate_local_ollama_base_url),
]


class LegacyStageRouteOptions(TypedDict, closed=True):  # type: ignore[call-arg]  # mypy lacks PEP 728
    temperature: float | None
    max_tokens: int | None
    reasoning_effort: ReasoningEffort | None
    had_reserved_value: bool
    reserved_value: None


class AiProviderOptions(TypedDict, total=False, closed=True):  # type: ignore[call-arg]  # mypy lacks PEP 728
    """Secret-free options currently consumed by Agora routing."""

    base_url: PublicBaseUrl | LocalOllamaBaseUrl | None
    num_ctx: Annotated[int, Field(gt=0)]
    secret_ref: Annotated[str, Field(min_length=1)]
    connection_only: bool
    __legacy_stage_route__: LegacyStageRouteOptions


_AI_PROVIDER_OPTIONS_ADAPTER = TypeAdapter(AiProviderOptions)


def _empty_provider_options() -> AiProviderOptions:
    return {}


class ModelCapabilities(BaseModel):
    """Tri-state model capabilities; unknown is never treated as supported."""

    model_config = _STRICT

    chat: CapabilityState = "unknown"
    embeddings: CapabilityState = "unknown"
    streaming: CapabilityState = "unknown"
    tool_calling: CapabilityState = "unknown"
    json_object: CapabilityState = "unknown"
    json_schema: CapabilityState = "unknown"
    vision: CapabilityState = "unknown"
    reasoning: CapabilityState = "unknown"

    def supports(self, capability: str) -> bool:
        return getattr(self, capability, "unknown") == "supported"


class ProviderConnection(BaseModel):
    """Public connection metadata. Secret values are stored out of contract."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    provider_kind: ProviderConnectionProviderKind
    display_name: str = Field(min_length=1)
    transport: ProviderTransport
    auth_mode: ProviderAuthMode
    base_url: PublicBaseUrl | LocalOllamaBaseUrl | None = None
    enabled: bool = True
    status: ProviderStatus = "unknown"
    status_message: str | None = None
    secret_ref: str | None = None
    capabilities: dict[str, CapabilityState] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_tested_at: datetime | None = None

    @model_validator(mode="after")
    def validate_base_url_for_provider(self) -> ProviderConnection:
        if self.base_url is None:
            return self
        if self.provider_kind == "ollama":
            _validate_local_ollama_base_url(self.base_url)
        else:
            _validate_public_base_url(self.base_url)
        return self


class ProviderConnectionUpsertRequest(BaseModel):
    """Lifecycle input; API keys are never part of public connection metadata."""

    model_config = _STRICT

    display_name: str = Field(min_length=1)
    provider_kind: ProviderConnectionProviderKind
    base_url: str | None = None
    enabled: bool = True
    api_key: SecretStr | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_base_url_for_provider(self) -> ProviderConnectionUpsertRequest:
        if self.base_url is None:
            return self
        if self.provider_kind == "ollama":
            _validate_local_ollama_base_url(self.base_url)
        else:
            _validate_public_base_url(self.base_url)
        return self


class ProviderConnectionResponse(BaseModel):
    """Public lifecycle response with no secret-bearing fields."""

    model_config = _STRICT

    connection: ProviderConnection


class AiModel(BaseModel):
    model_config = _STRICT

    provider_connection_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    source: ModelSource
    status: ModelStatus = "unknown"
    context_window: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    embedding_dimensions: int | None = Field(default=None, gt=0)
    local_or_cloud: LocalOrCloud = "unknown"
    deprecated: bool = False
    metadata_updated_at: datetime | None = None


class AiRoute(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"source": {"const": "provider_fallback"}},
                        "required": ["source"],
                    },
                    "then": {
                        "properties": {
                            "fallback_reason": {
                                "minLength": 1,
                                "pattern": r"\S",
                                "type": "string",
                            }
                        },
                        "required": ["fallback_reason"],
                    },
                },
                {
                    "if": {
                        "properties": {
                            "provider_options": {
                                "properties": {"connection_only": {"const": True}},
                                "required": ["connection_only"],
                            }
                        },
                        "required": ["provider_options"],
                    },
                    "then": {
                        "properties": {
                            "provider_options": {"required": ["secret_ref"]}
                        }
                    },
                },
            ]
        },
    )

    stage: StageId | None = None
    provider_connection_id: str | None = None
    model_id: str | None = None
    source: RouteSource
    validated_capabilities: dict[str, CapabilityState] = Field(default_factory=dict)
    provider_options: AiProviderOptions = Field(default_factory=_empty_provider_options)
    routing_version: int = Field(default=1, ge=1)
    resolved_at: datetime | None = None
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def validate_provider_fallback_reason(self) -> AiRoute:
        """
        Validate fallback and connection-only route requirements.
        
        Returns:
        	AiRoute: The validated route.
        """
        if self.source == "provider_fallback" and not (
            self.fallback_reason and self.fallback_reason.strip()
        ):
            raise ValueError("provider_fallback requires a non-blank fallback_reason")
        if self.provider_options.get("connection_only") is True and not self.provider_options.get(
            "secret_ref"
        ):
            raise ValueError("connection_only requires secret_ref")
        return self


def provider_connection_from_descriptor(
    descriptor: ProviderDescriptor,
    *,
    now: datetime | None = None,
) -> ProviderConnection:
    """Read a legacy descriptor into the canonical public contract."""

    timestamp = now or datetime.now(timezone.utc)
    base_url, base_url_was_sanitized = _sanitize_legacy_base_url(descriptor.base_url)
    return ProviderConnection(
        id=descriptor.id,
        # Statische Verengung; unsupported Kinds lehnt der BeforeValidator
        # von ProviderConnectionProviderKind zur Laufzeit ab.
        provider_kind=cast(ProviderConnectionKind, descriptor.type),
        display_name=descriptor.label,
        transport="local" if descriptor.type == "ollama" else "http",
        auth_mode="api_key" if descriptor.api_key_ref else "none",
        base_url=base_url,
        status="degraded" if base_url_was_sanitized else "unknown",
        status_message=(
            "Legacy base URL requires reconfiguration"
            if base_url_was_sanitized
            else None
        ),
        secret_ref=descriptor.api_key_ref,
        capabilities={
            "model_discovery": (
                "supported" if descriptor.supports_models_endpoint else "unsupported"
            ),
            "tool_calling": "supported" if descriptor.supports_tools else "unsupported",
        },
        created_at=timestamp,
        updated_at=timestamp,
    )


def _sanitize_legacy_base_url(value: str | None) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    try:
        return _validate_public_base_url(value), False
    except ValueError:
        pass

    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None, True
        hostname = parsed.hostname
        if ":" in hostname:
            hostname = f"[{hostname}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        sanitized = urlunsplit(
            (parsed.scheme, f"{hostname}{port}", parsed.path, "", "")
        )
        return _validate_public_base_url(sanitized), True
    except ValueError:
        return None, True


def provider_descriptor_from_connection(
    connection: ProviderConnection,
    *,
    fallback_models: list[str],
) -> ProviderDescriptor:
    """Adapt to the legacy descriptor; fallback models stay explicit at the boundary."""

    return ProviderDescriptor(
        id=connection.id,
        label=connection.display_name,
        type=connection.provider_kind,
        base_url=connection.base_url,
        api_key_ref=connection.secret_ref,
        supports_models_endpoint=(
            connection.capabilities.get("model_discovery") == "supported"
        ),
        supports_tools=connection.capabilities.get("tool_calling") == "supported",
        fallback_models=fallback_models,
    )


def ai_model_from_model_entry(entry: ModelEntry) -> AiModel:
    return AiModel(
        provider_connection_id=entry.provider_id,
        model_id=entry.id,
        display_name=entry.name,
        capabilities=ModelCapabilities(
            tool_calling="supported" if entry.supports_tools else "unsupported",
            json_object="supported" if entry.supports_json_mode else "unsupported",
        ),
        source=entry.source,
        status="available",
        context_window=entry.context_window,
        metadata_updated_at=datetime.fromtimestamp(entry.refreshed_at, tz=timezone.utc),
    )


def model_entry_from_ai_model(model: AiModel) -> ModelEntry:
    refreshed_at = model.metadata_updated_at or datetime.fromtimestamp(0, tz=timezone.utc)
    return ModelEntry(
        id=model.model_id,
        name=model.display_name,
        provider_id=model.provider_connection_id,
        source=model.source,
        refreshed_at=refreshed_at.timestamp(),
        supports_tools=model.capabilities.supports("tool_calling"),
        supports_json_mode=model.capabilities.supports("json_object"),
        context_window=model.context_window,
    )


def ai_route_from_stage_route(route: StageLLMRoute) -> AiRoute:
    raw_options = dict(route.provider_options)
    had_reserved_value = _LEGACY_ROUTE_OPTIONS_KEY in raw_options
    previous_reserved_value = raw_options.pop(_LEGACY_ROUTE_OPTIONS_KEY, None)
    if previous_reserved_value is not None:
        raise ValueError("legacy reserved provider option must be null")
    legacy_options: LegacyStageRouteOptions = {
        "temperature": route.temperature,
        "max_tokens": route.max_tokens,
        "reasoning_effort": route.reasoning_effort,
        "had_reserved_value": had_reserved_value,
        "reserved_value": previous_reserved_value,
    }
    raw_options[_LEGACY_ROUTE_OPTIONS_KEY] = legacy_options
    options = _AI_PROVIDER_OPTIONS_ADAPTER.validate_python(raw_options)
    return AiRoute(
        stage=route.stage,
        provider_connection_id=route.provider_id,
        model_id=route.model,
        source="legacy",
        provider_options=options,
    )


def stage_route_from_ai_route(route: AiRoute) -> StageLLMRoute:
    legacy = route.provider_options.get("__legacy_stage_route__")
    options = dict(route.provider_options)
    options.pop(_LEGACY_ROUTE_OPTIONS_KEY, None)
    if legacy is not None and legacy.get("had_reserved_value"):
        options[_LEGACY_ROUTE_OPTIONS_KEY] = legacy.get("reserved_value")
    return StageLLMRoute(
        stage=route.stage,
        provider_id=route.provider_connection_id,
        model=route.model_id,
        temperature=legacy.get("temperature") if legacy is not None else None,
        max_tokens=legacy.get("max_tokens") if legacy is not None else None,
        reasoning_effort=(
            legacy.get("reasoning_effort", "none") if legacy is not None else "none"
        ),
        provider_options=options,
    )


def llm_profile_to_canonical(
    profile: LlmProfile,
    *,
    secret_ref: str | None = None,
) -> tuple[ProviderConnection, AiModel, AiRoute]:
    """Read a legacy profile without copying its secret value."""

    unresolved_legacy_secret = bool(profile.api_key) and secret_ref is None
    base_url, base_url_was_sanitized = _sanitize_legacy_base_url(profile.base_url)
    degradation_reasons = []
    if unresolved_legacy_secret:
        degradation_reasons.append("Legacy API key has no resolved secret_ref")
    if base_url_was_sanitized:
        degradation_reasons.append("Legacy base URL requires reconfiguration")
    connection = ProviderConnection(
        id=profile.id,
        # Statische Verengung; unsupported Kinds lehnt der BeforeValidator
        # von ProviderConnectionProviderKind zur Laufzeit ab.
        provider_kind=cast(ProviderConnectionKind, profile.provider),
        display_name=profile.name,
        transport="local" if profile.provider == "ollama" else "http",
        auth_mode="api_key" if secret_ref or unresolved_legacy_secret else "none",
        base_url=base_url,
        status="degraded" if degradation_reasons else "unknown",
        status_message="; ".join(degradation_reasons) or None,
        secret_ref=secret_ref,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )
    model = AiModel(
        provider_connection_id=profile.id,
        model_id=profile.model_name,
        display_name=profile.model_name,
        source="custom",
        local_or_cloud="local" if profile.provider == "ollama" else "cloud",
        metadata_updated_at=profile.updated_at,
    )
    route = AiRoute(
        provider_connection_id=profile.id,
        model_id=profile.model_name,
        source="profile",
    )
    return connection, model, route


def llm_profile_from_canonical(
    connection: ProviderConnection,
    model: AiModel,
    *,
    template: LlmProfile,
    api_key: str | None = None,
) -> LlmProfile:
    """Write a legacy-compatible view; the secret is supplied by the secret store."""

    return LlmProfile(
        id=connection.id,
        name=connection.display_name,
        provider=connection.provider_kind,
        base_url=connection.base_url or template.base_url,
        model_name=model.model_id,
        api_key=api_key,
        is_default=template.is_default,
        created_at=connection.created_at or template.created_at,
        updated_at=connection.updated_at or template.updated_at,
    )
