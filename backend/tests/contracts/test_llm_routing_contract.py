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
    with pytest.raises(ValidationError):
        StageLLMRoute(
            provider_id="ollama",
            model="qwen2.5:32b",
            unknown_field="error"
        )

def test_runtime_llm_routing_valid():
    default_route = StageLLMRoute(provider_id="openai", model="gpt-4o")
    routing = RuntimeLlmRouting(
        default_route=default_route,
        stage_overrides={
            "graph_build": StageLLMRoute(provider_id="ollama", model="qwen2.5:32b")
        },
        routing_version=2
    )
    assert routing.default_route.provider_id == "openai"
    assert routing.stage_overrides["graph_build"].provider_id == "ollama"
    assert routing.routing_version == 2

def test_provider_descriptor_valid():
    desc = ProviderDescriptor(
        id="ollama_local",
        name="Ollama Local",
        type="ollama_local",
        auth_status="configured"
    )
    assert desc.id == "ollama_local"
    assert desc.type == "ollama_local"

def test_resolved_route_valid():
    route = ResolvedRoute(
        stage="graph_build",
        provider_id="ollama",
        model="qwen2.5:32b",
        routing_version=5,
        started_at="2026-05-12T10:00:00Z"
    )
    assert route.stage == "graph_build"
    assert route.routing_version == 5
