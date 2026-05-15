import pytest
from pydantic import ValidationError
from app.contracts.llm_routing_contract import (
    StageLLMRoute,
    RuntimeLlmRouting,
    ProviderDescriptor,
    ResolvedRoute,
)

def test_stage_llm_route_valid():
    route = StageLLMRoute(
        provider_id="ollama",
        model="qwen2.5:32b",
        reasoning_effort="medium"
    )
    assert route.provider_id == "ollama"
    assert route.model == "qwen2.5:32b"
    assert route.reasoning_effort == "medium"
    assert route.provider_options == {}

def test_stage_llm_route_extra_forbid():
    with pytest.raises(ValidationError) as excinfo:
        StageLLMRoute(
            provider_id="ollama",
            model="qwen2.5:32b",
            unknown_field="error"
        )
    assert "Extra inputs are not permitted" in str(excinfo.value)

def test_stage_llm_route_thinking_legacy_mapping():
    # thinking=True → "medium"
    route = StageLLMRoute(provider_id="o1", model="o1-preview", thinking=True)
    assert route.reasoning_effort == "medium"

    # thinking=False → "none"
    route = StageLLMRoute(provider_id="gpt-4", model="gpt-4o", thinking=False)
    assert route.reasoning_effort == "none"

    # missing → unchanged (default "none")
    route = StageLLMRoute(provider_id="gpt-4", model="gpt-4o")
    assert route.reasoning_effort == "none"

    # reasoning_effort wins over thinking
    route = StageLLMRoute(provider_id="o1", model="o1-preview", thinking=True, reasoning_effort="high")
    assert route.reasoning_effort == "high"

def test_stage_llm_route_num_ctx_rejection():
    # num_ctx at top-level rejected
    with pytest.raises(ValidationError) as excinfo:
        StageLLMRoute(provider_id="ollama", model="qwen", num_ctx=32768)
    assert "num_ctx must be inside provider_options" in str(excinfo.value)

    # num_ctx inside provider_options ok
    route = StageLLMRoute(
        provider_id="ollama",
        model="qwen",
        provider_options={"num_ctx": 32768}
    )
    assert route.provider_options["num_ctx"] == 32768

def test_runtime_llm_routing_valid():
    default_route = StageLLMRoute(provider_id="openai", model="gpt-4o")
    routing = RuntimeLlmRouting(
        global_default=default_route,
        stage_overrides={
            "graph_build": StageLLMRoute(provider_id="ollama", model="qwen2.5:32b")
        },
        routing_version=2
    )
    assert routing.global_default.provider_id == "openai"
    assert routing.stage_overrides["graph_build"].provider_id == "ollama"
    assert routing.routing_version == 2

def test_provider_descriptor_valid():
    desc = ProviderDescriptor(
        id="ollama_cloud",
        label="Ollama Local",
        type="ollama_cloud",
        base_url="http://localhost:11434",
        supports_models_endpoint=True,
        fallback_models=["llama3"]
    )
    assert desc.id == "ollama_cloud"
    assert desc.label == "Ollama Local"
    assert desc.type == "ollama_cloud"
    assert desc.base_url == "http://localhost:11434"
    assert desc.supports_models_endpoint is True
    assert desc.fallback_models == ["llama3"]

def test_resolved_route_valid():
    route = ResolvedRoute(
        stage="graph_build",
        provider_id="ollama",
        model="qwen2.5:32b",
        base_url_sanitized="http://localhost:11434",
        reasoning_effort="high",
        routing_version=5,
        provider_options={"num_ctx": 32768},
        started_at="2026-05-12T10:00:00Z"
    )
    assert route.stage == "graph_build"
    assert route.provider_id == "ollama"
    assert route.model == "qwen2.5:32b"
    assert route.base_url_sanitized == "http://localhost:11434"
    assert route.reasoning_effort == "high"
    assert route.routing_version == 5
    assert route.provider_options == {"num_ctx": 32768}
    assert route.started_at == "2026-05-12T10:00:00Z"

def test_resolved_route_extra_forbid():
    with pytest.raises(ValidationError):
        ResolvedRoute(
            stage="graph_build",
            provider_id="ollama",
            model="qwen2.5:32b",
            routing_version=5,
            extra_field="rejected"
        )
