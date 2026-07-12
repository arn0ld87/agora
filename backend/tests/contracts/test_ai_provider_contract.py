from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from app.contracts.ai_provider_contract import (
    AiModel,
    AiRoute,
    ModelCapabilities,
    ProviderConnection,
    ProviderConnectionResponse,
    ProviderConnectionUpsertRequest,
    ai_model_from_model_entry,
    ai_route_from_stage_route,
    llm_profile_from_canonical,
    llm_profile_to_canonical,
    model_entry_from_ai_model,
    provider_connection_from_descriptor,
    provider_descriptor_from_connection,
    stage_route_from_ai_route,
)
from app.contracts.llm_profile_contract import LlmProfile
from app.contracts.llm_routing_contract import ModelEntry, ProviderDescriptor, StageLLMRoute


NOW = datetime(2026, 7, 10, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_FIXTURES = json.loads(
    (REPO_ROOT / "schemas/fixtures/ai-provider-contract-fixtures.json").read_text()
)
CONTRACT_CASES = {
    "provider_connection": (
        ProviderConnection,
        REPO_ROOT / "schemas/ai-provider-connection.schema.json",
    ),
    "ai_model": (AiModel, REPO_ROOT / "schemas/ai-model.schema.json"),
    "ai_route": (AiRoute, REPO_ROOT / "schemas/ai-route.schema.json"),
}


def _connection_data(base_url: str) -> dict:
    return {
        "id": "provider-1",
        "provider_kind": "openai_compatible",
        "display_name": "Provider",
        "transport": "http",
        "auth_mode": "none",
        "base_url": base_url,
    }


@pytest.mark.parametrize("provider_kind", ["minimax"])
def test_provider_connection_upsert_request_accepts_new_api_key_providers(
    provider_kind: str,
) -> None:
    request = ProviderConnectionUpsertRequest(
        display_name="Cloud provider",
        provider_kind=provider_kind,
        base_url="https://api.example.test/v1",
    )

    assert request.provider_kind == provider_kind


def test_provider_connection_upsert_request_rejects_opencode_go_as_unsupported() -> None:
    with pytest.raises(ValidationError, match="unsupported"):
        ProviderConnectionUpsertRequest(
            display_name="OpenCode Go",
            provider_kind="opencode_go",
            base_url="https://api.example.test/v1",
        )


def test_provider_connection_rejects_opencode_go_as_unsupported() -> None:
    with pytest.raises(ValidationError, match="unsupported"):
        ProviderConnection(
            **{
                **_connection_data("https://api.example.test/v1"),
                "provider_kind": "opencode_go",
            }
        )


@pytest.mark.parametrize(
    "base_url",
    ["http://127.0.0.1:11434", "http://[::1]:11434/v1", "http://localhost:11434"],
)
def test_provider_connection_upsert_request_accepts_only_loopback_ollama_urls(
    base_url: str,
) -> None:
    request = ProviderConnectionUpsertRequest(
        display_name="Ollama lokal",
        provider_kind="ollama",
        base_url=base_url,
    )

    assert request.base_url == base_url


@pytest.mark.parametrize(
    "base_url",
    ["https://ollama.example.test", "http://192.168.1.10:11434", "http://0.0.0.0:11434"],
)
def test_provider_connection_upsert_request_rejects_non_loopback_ollama_urls(
    base_url: str,
) -> None:
    with pytest.raises(ValidationError):
        ProviderConnectionUpsertRequest(
            display_name="Ollama lokal",
            provider_kind="ollama",
            base_url=base_url,
        )


def test_provider_connection_rejects_loopback_url_for_non_local_provider() -> None:
    with pytest.raises(ValidationError, match="public HTTP\\(S\\) base URL"):
        ProviderConnection(
            **{
                **_connection_data("http://localhost:11434"),
                "provider_kind": "openai_compatible",
            }
        )


def test_provider_connection_upsert_request_never_serializes_api_key() -> None:
    request = ProviderConnectionUpsertRequest(
        display_name="OpenAI",
        provider_kind="openai",
        api_key="test-only-api-key",
    )
    response = ProviderConnectionResponse(
        connection=ProviderConnection(
            id="openai-main",
            provider_kind="openai",
            display_name="OpenAI",
            transport="http",
            auth_mode="api_key",
        )
    )

    assert "api_key" not in request.model_dump(mode="json")
    assert "test-only-api-key" not in str(response.model_dump(mode="json"))


def test_canonical_contracts_are_strict_and_secret_free() -> None:
    connection = ProviderConnection(
        id="ollama-local",
        provider_kind="ollama",
        display_name="Ollama lokal",
        transport="local",
        auth_mode="none",
        capabilities={"model_discovery": "supported"},
        created_at=NOW,
        updated_at=NOW,
    )
    model = AiModel(
        provider_connection_id=connection.id,
        model_id="qwen3:8b",
        display_name="Qwen 3 8B",
        capabilities=ModelCapabilities(chat="supported"),
        source="live",
        status="available",
        local_or_cloud="local",
        metadata_updated_at=NOW,
    )
    route = AiRoute(
        stage="report_generation",
        provider_connection_id=connection.id,
        model_id=model.model_id,
        source="stage_override",
        validated_capabilities={"chat": "supported"},
    )

    assert model.capabilities.supports("chat") is True
    assert model.capabilities.supports("vision") is False
    assert route.provider_options == {}
    for contract, instance in (
        (ProviderConnection, connection),
        (AiModel, model),
        (AiRoute, route),
    ):
        assert "api_key" not in contract.model_fields
        assert "secret" not in contract.model_fields
        assert contract.model_json_schema()["additionalProperties"] is False
        with pytest.raises(ValidationError):
            contract.model_validate({**instance.model_dump(), "unexpected": True})


@pytest.mark.parametrize("contract_name", CONTRACT_CASES)
def test_shared_fixtures_match_pydantic_and_generated_json_schema(
    contract_name: str,
) -> None:
    model, schema_path = CONTRACT_CASES[contract_name]
    validator = Draft202012Validator(json.loads(schema_path.read_text()))

    for fixture in SHARED_FIXTURES[contract_name]["valid"]:
        model.model_validate(fixture)
        validator.validate(fixture)
    for fixture in SHARED_FIXTURES[contract_name]["invalid"]:
        with pytest.raises(ValidationError):
            model.model_validate(fixture)
        with pytest.raises(JsonSchemaValidationError):
            validator.validate(fixture)


@pytest.mark.parametrize("base_url", SHARED_FIXTURES["base_urls"]["invalid"])
def test_provider_connection_rejects_non_public_base_url(base_url: str) -> None:
    with pytest.raises(ValidationError):
        ProviderConnection.model_validate(_connection_data(base_url))


@pytest.mark.parametrize("base_url", SHARED_FIXTURES["base_urls"]["invalid"])
def test_ai_route_rejects_non_public_base_url(base_url: str) -> None:
    with pytest.raises(ValidationError):
        AiRoute(source="runtime", provider_options={"base_url": base_url})


@pytest.mark.parametrize("base_url", SHARED_FIXTURES["base_urls"]["valid"])
def test_public_base_url_positive_fixtures(base_url: str) -> None:
    assert ProviderConnection.model_validate(_connection_data(base_url)).base_url == base_url
    route = AiRoute(source="runtime", provider_options={"base_url": base_url})
    assert route.provider_options["base_url"] == base_url


def test_generated_json_schemas_enforce_public_base_url_fixtures() -> None:
    connection_validator = Draft202012Validator(
        json.loads((REPO_ROOT / "schemas/ai-provider-connection.schema.json").read_text())
    )
    route_validator = Draft202012Validator(
        json.loads((REPO_ROOT / "schemas/ai-route.schema.json").read_text())
    )

    for base_url in SHARED_FIXTURES["base_urls"]["valid"]:
        connection_validator.validate(_connection_data(base_url))
        route_validator.validate(
            {"source": "runtime", "provider_options": {"base_url": base_url}}
        )
    for base_url in SHARED_FIXTURES["base_urls"]["invalid"]:
        with pytest.raises(JsonSchemaValidationError):
            connection_validator.validate(_connection_data(base_url))
        with pytest.raises(JsonSchemaValidationError):
            route_validator.validate(
                {"source": "runtime", "provider_options": {"base_url": base_url}}
            )


def test_unknown_capability_is_never_treated_as_supported() -> None:
    capabilities = ModelCapabilities()

    assert capabilities.chat == "unknown"
    assert capabilities.supports("chat") is False
    assert capabilities.supports("missing") is False


@pytest.mark.parametrize(
    "provider_options",
    [
        {"x-api-key": "fixture-token"},
        {"client_secret": "fixture-token"},
        {"refresh_token": "fixture-token"},
        {"headers": {"bearer_token": "fixture-token"}},
    ],
)
def test_route_provider_options_reject_non_allowlisted_keys(
    provider_options: dict,
) -> None:
    with pytest.raises(ValidationError):
        AiRoute(
            source="runtime",
            provider_options=provider_options,
        )


def test_route_provider_options_accept_runtime_allowlist() -> None:
    route = AiRoute(
        source="runtime",
        provider_options={
            "base_url": "https://gateway.example/v1",
            "num_ctx": 32768,
        },
    )

    assert route.provider_options == {
        "base_url": "https://gateway.example/v1",
        "num_ctx": 32768,
    }


def test_route_json_schema_expresses_provider_options_allowlist() -> None:
    schema = AiRoute.model_json_schema()
    options_schema = schema["$defs"]["AiProviderOptions"]

    assert options_schema["additionalProperties"] is False
    assert set(options_schema["properties"]) == {
        "base_url",
        "num_ctx",
        "__legacy_stage_route__",
    }


def test_provider_descriptor_adapter_roundtrip_preserves_public_metadata() -> None:
    legacy = ProviderDescriptor(
        id="openai-main",
        label="OpenAI",
        type="openai",
        base_url="https://api.openai.com/v1",
        api_key_ref="vault:openai-main",
        supports_models_endpoint=True,
        supports_tools=True,
        fallback_models=["gpt-4.1-mini"],
    )

    canonical = provider_connection_from_descriptor(legacy, now=NOW)
    restored = provider_descriptor_from_connection(canonical, fallback_models=legacy.fallback_models)

    assert canonical.secret_ref == "vault:openai-main"
    assert restored == legacy


@pytest.mark.parametrize("base_url", SHARED_FIXTURES["base_urls"]["invalid"])
def test_provider_descriptor_adapter_sanitizes_unsafe_legacy_base_url(
    base_url: str,
) -> None:
    legacy = ProviderDescriptor(
        id="legacy-provider",
        label="Legacy Provider",
        type="openai_compatible",
        base_url=base_url,
    )

    canonical = provider_connection_from_descriptor(legacy, now=NOW)

    assert canonical.base_url == "https://example.test/v1"
    assert canonical.status == "degraded"
    assert canonical.status_message == "Legacy base URL requires reconfiguration"
    assert "fixture-token" not in str(canonical.model_dump())


@pytest.mark.parametrize("base_url", SHARED_FIXTURES["base_urls"]["invalid"])
def test_stage_route_adapter_rejects_unsafe_legacy_base_url(base_url: str) -> None:
    legacy = StageLLMRoute(
        provider_id="legacy-provider",
        model="model-1",
        provider_options={"base_url": base_url},
    )

    with pytest.raises(ValueError):
        ai_route_from_stage_route(legacy)


def test_provider_descriptor_reverse_adapter_requires_fallback_sidecar() -> None:
    connection = ProviderConnection(
        id="openai-main",
        provider_kind="openai",
        display_name="OpenAI",
        transport="http",
        auth_mode="api_key",
        secret_ref="vault:openai-main",
    )

    with pytest.raises(TypeError):
        provider_descriptor_from_connection(connection)


def test_model_entry_adapter_roundtrip_and_unknown_defaults() -> None:
    legacy = ModelEntry(
        id="gpt-4.1-mini",
        name="GPT-4.1 mini",
        provider_id="openai-main",
        source="cached",
        refreshed_at=NOW.timestamp(),
        supports_tools=True,
        supports_json_mode=False,
        context_window=128_000,
    )

    canonical = ai_model_from_model_entry(legacy)

    assert canonical.capabilities.tool_calling == "supported"
    assert canonical.capabilities.json_object == "unsupported"
    assert canonical.capabilities.vision == "unknown"
    assert model_entry_from_ai_model(canonical) == legacy


def test_stage_route_adapter_roundtrip_preserves_legacy_tuning() -> None:
    legacy = StageLLMRoute(
        stage="simulation_rounds",
        provider_id="ollama-local",
        model="qwen3:8b",
        temperature=0.4,
        max_tokens=2048,
        reasoning_effort="medium",
        provider_options={"num_ctx": 32768},
    )

    canonical = ai_route_from_stage_route(legacy)

    assert canonical.source == "legacy"
    assert stage_route_from_ai_route(canonical) == legacy


def test_stage_route_roundtrip_preserves_reserved_none_collision() -> None:
    legacy = StageLLMRoute(
        stage="report_generation",
        provider_id="ollama-local",
        model="qwen3:8b",
        provider_options={
            "num_ctx": 32768,
            "__legacy_stage_route__": None,
        },
    )

    canonical = ai_route_from_stage_route(legacy)

    assert stage_route_from_ai_route(canonical) == legacy


def test_stage_route_roundtrip_preserves_none_reasoning_effort() -> None:
    legacy = StageLLMRoute(
        stage="report_generation",
        provider_id="ollama-local",
        model="qwen3:8b",
        reasoning_effort=None,
    )

    canonical = ai_route_from_stage_route(legacy)

    assert stage_route_from_ai_route(canonical).reasoning_effort is None


def test_llm_profile_adapter_keeps_secrets_out_of_canonical_contracts() -> None:
    legacy = LlmProfile(
        id="profile-1",
        name="Lokales Profil",
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model_name="qwen3:8b",
        api_key="fixture-token",
        is_default=True,
        created_at=NOW,
        updated_at=NOW,
    )

    connection, model, route = llm_profile_to_canonical(
        legacy,
        secret_ref="vault:profile-1",
    )
    serialized = f"{connection.model_dump()} {model.model_dump()} {route.model_dump()}"

    assert connection.secret_ref == "vault:profile-1"
    assert "fixture-token" not in serialized
    assert llm_profile_from_canonical(
        connection,
        model,
        template=legacy,
        api_key="fixture-token",
    ) == legacy


def test_llm_profile_with_legacy_key_without_ref_is_explicitly_degraded() -> None:
    legacy = LlmProfile(
        id="profile-unresolved",
        name="Unresolved secret",
        provider="openai",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4.1-mini",
        api_key="fixture-token",
        is_default=False,
        created_at=NOW,
        updated_at=NOW,
    )

    connection, _, _ = llm_profile_to_canonical(legacy)

    assert connection.auth_mode == "api_key"
    assert connection.status == "degraded"
    assert connection.status_message == "Legacy API key has no resolved secret_ref"
    assert connection.secret_ref is None


def test_descriptor_adapter_normalizes_uppercase_scheme_instead_of_raising() -> None:
    legacy = ProviderDescriptor(
        id="legacy-upper",
        label="Legacy Upper",
        type="openai_compatible",
        base_url="HTTPS://Example.test/v1",
    )

    canonical = provider_connection_from_descriptor(legacy, now=NOW)

    assert canonical.base_url == "https://example.test/v1"
    assert canonical.status == "degraded"
    assert canonical.status_message == "Legacy base URL requires reconfiguration"


def test_descriptor_adapter_degrades_unsalvageable_host_instead_of_raising() -> None:
    legacy = ProviderDescriptor(
        id="legacy-underscore",
        label="Legacy Underscore",
        type="openai_compatible",
        base_url="http://legacy_host.example:11434/v1",
    )

    canonical = provider_connection_from_descriptor(legacy, now=NOW)

    assert canonical.base_url is None
    assert canonical.status == "degraded"
    assert canonical.status_message == "Legacy base URL requires reconfiguration"


def test_llm_profile_adapter_sanitizes_unsafe_base_url_instead_of_raising() -> None:
    legacy = LlmProfile(
        id="profile-unsafe-url",
        name="Unsafe URL",
        provider="openai_compatible",
        base_url="https://host.example/v1?key=fixture-token",
        model_name="model-1",
        created_at=NOW,
        updated_at=NOW,
    )

    connection, _, _ = llm_profile_to_canonical(
        legacy,
        secret_ref="vault:profile-unsafe-url",
    )

    assert connection.base_url == "https://host.example/v1"
    assert connection.status == "degraded"
    assert connection.status_message == "Legacy base URL requires reconfiguration"
    assert "fixture-token" not in str(connection.model_dump())


def test_llm_profile_adapter_combines_secret_and_base_url_degradation() -> None:
    legacy = LlmProfile(
        id="profile-doubly-degraded",
        name="Doubly degraded",
        provider="openai",
        base_url="https://user@host.example/v1",
        model_name="gpt-4.1-mini",
        api_key="fixture-token",
        created_at=NOW,
        updated_at=NOW,
    )

    connection, _, _ = llm_profile_to_canonical(legacy)

    assert connection.auth_mode == "api_key"
    assert connection.status == "degraded"
    assert connection.status_message == (
        "Legacy API key has no resolved secret_ref; "
        "Legacy base URL requires reconfiguration"
    )
    assert connection.base_url == "https://host.example/v1"
    assert "fixture-token" not in str(connection.model_dump())
