import pytest
import json
from app.services.runtime_run_config import RuntimeRunConfig
from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute
from unittest.mock import patch

@pytest.fixture
def temp_run_dir(tmp_path):
    run_id = "proj_secret_test"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    with patch("app.utils.artifact_locator.ArtifactLocator.run_dir", return_value=str(run_dir)):
        yield run_id, run_dir

def test_recursive_secret_scrubbing(temp_run_dir):
    run_id, run_dir = temp_run_dir
    service = RuntimeRunConfig(run_id)

    # Create a config with secrets in provider_options (nested)
    global_default = StageLLMRoute(
        provider_id="ollama",
        model="qwen",
        provider_options={
            "api_key": "secret123",
            "base_url": "https://user:pass@example.test/v1?api_key=secret",
            "nested": {
                "password": "pass",
                "safe": "value"
            }
        }
    )
    config = RuntimeLlmRouting(global_default=global_default, routing_version=1)

    # Save config
    service.save_config(config)

    # Check the file content manually
    config_path = run_dir / "runtime_llm_routing.json"
    with open(config_path, "r") as f:
        data = json.load(f)

    def check_no_secrets(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k.lower() not in ("api_key", "password", "secret")
                check_no_secrets(v)
        elif isinstance(obj, list):
            for i in obj:
                check_no_secrets(i)

    check_no_secrets(data)
    provider_options = data["global_default"]["provider_options"]
    assert provider_options["nested"]["safe"] == "value"
    assert provider_options["base_url"] == "https://example.test/v1"

def test_stage_snapshot_secret_scrubbing(temp_run_dir):
    run_id, run_dir = temp_run_dir
    service = RuntimeRunConfig(run_id)

    snapshot = {
        "stage": "graph_build",
        "provider_id": "openai",
        "api_key": "SK-12345",
        "provider_options": {
            "token": "TOK-555"
        }
    }

    service.save_stage_snapshot("graph_build", snapshot)

    snapshot_path = run_dir / "stages" / "graph_build_llm_route_snapshot.json"
    with open(snapshot_path, "r") as f:
        data = json.load(f)

    assert "api_key" not in data
    assert "token" not in data["provider_options"]


def test_stage_snapshot_is_write_once(temp_run_dir):
    run_id, run_dir = temp_run_dir
    service = RuntimeRunConfig(run_id)

    service.save_stage_snapshot("graph_build", {"provider_id": "openai", "model": "gpt-4o"})
    service.save_stage_snapshot("graph_build", {"provider_id": "google", "model": "gemini"})

    snapshot_path = run_dir / "stages" / "graph_build_llm_route_snapshot.json"
    with open(snapshot_path, "r") as f:
        data = json.load(f)

    assert data["provider_id"] == "openai"
    assert data["model"] == "gpt-4o"
