import pytest
from unittest.mock import patch
from app.services.runtime_run_config import RuntimeRunConfig, _detect_default_provider_id
from app.services.stage_model_router import StageModelRouter
from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute

@pytest.fixture
def temp_run_dir(tmp_path):
    run_id = "proj_testrun123"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)

    with patch("app.utils.artifact_locator.ArtifactLocator.run_dir", return_value=str(run_dir)):
        yield run_id

def test_runtime_run_config_persistence(temp_run_dir):
    service = RuntimeRunConfig(temp_run_dir)
    global_default = StageLLMRoute(provider_id="ollama", model="qwen")
    config = RuntimeLlmRouting(global_default=global_default, routing_version=1)

    service.save_config(config)
    loaded = service.load_config()
    assert loaded.routing_version == 1
    assert loaded.global_default.provider_id == "ollama"

def test_stage_model_router_resolution(temp_run_dir):
    service = RuntimeRunConfig(temp_run_dir)
    global_default = StageLLMRoute(provider_id="openai", model="gpt-4o")
    override_route = StageLLMRoute(provider_id="ollama", model="qwen")
    config = RuntimeLlmRouting(
        global_default=global_default,
        stage_overrides={"graph_build": override_route},
        routing_version=1
    )
    service.save_config(config)

    router = StageModelRouter(temp_run_dir)

    # Resolve default
    resolved_ingest = router.resolve("document_ingest")
    assert resolved_ingest.provider_id == "openai"

    # Resolve override
    resolved_graph = router.resolve("graph_build")
    assert resolved_graph.provider_id == "ollama"

def test_stage_model_router_snapshot_isolation(temp_run_dir):
    service = RuntimeRunConfig(temp_run_dir)
    router = StageModelRouter(temp_run_dir)

    global_default = StageLLMRoute(provider_id="openai", model="gpt-4o")
    config = RuntimeLlmRouting(global_default=global_default, routing_version=1)
    service.save_config(config)

    # 1. Resolve and lock stage
    resolved = router.resolve("document_ingest")
    router.lock_stage("document_ingest", resolved)

    # 2. Update runtime config
    new_global_default = StageLLMRoute(provider_id="ollama", model="qwen")
    new_config = RuntimeLlmRouting(global_default=new_global_default, routing_version=2)
    service.save_config(new_config)

    # 3. Resolve again - should still return the locked version
    resolved_after = router.resolve("document_ingest")
    assert resolved_after.provider_id == "openai"
    assert resolved_after.routing_version == 1

    # 4. Resolve another stage - should return the new version
    resolved_other = router.resolve("graph_build")
    assert resolved_other.provider_id == "ollama"
    assert resolved_other.routing_version == 2


def test_detect_default_provider_id_matches_hostname_not_substring():
    assert _detect_default_provider_id("https://api.openai.com/v1", "gpt-4o") == "openai"
    assert _detect_default_provider_id(
        "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-1.5-pro"
    ) == "google"
    assert _detect_default_provider_id("https://evil-openai.com/v1", "custom-model") == "openai_compatible"
    assert _detect_default_provider_id(
        "https://proxy.example/generativelanguage.googleapis.com", "custom-model"
    ) == "openai_compatible"
