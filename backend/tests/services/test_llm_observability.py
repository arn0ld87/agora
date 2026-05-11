import json
from app.services.llm_invocation_logger import LlmInvocationLogger
from unittest.mock import patch

def test_llm_invocation_logger_hygiene(tmp_path):
    run_id = "proj_hygiene"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)

    with patch("app.utils.artifact_locator.ArtifactLocator.run_dir", return_value=str(run_dir)):
        logger = LlmInvocationLogger(run_id)
        logger.log_event(
            stage="graph_build",
            provider_id="openai",
            model="gpt-4",
            base_url="https://user:pass@api.openai.com/v1?key=secret",
            routing_version=1,
            latency_ms=150.5,
            success=True
        )

        log_file = run_dir / "llm_call_events.jsonl"
        assert log_file.exists()

        with open(log_file, "r") as f:
            event = json.loads(f.readline())

        assert event["run_id"] == run_id
        assert "pass" not in event["base_url_sanitized"]
        assert "key=secret" not in event["base_url_sanitized"]
        assert event["base_url_sanitized"] == "https://api.openai.com/v1"
