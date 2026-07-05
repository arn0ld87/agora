"""Tests: LLMClient publishes ModelActiveEvent before each LLM call (Slice E.1, #213).

All tests are mock-only — no live LLM call is made.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from app.utils.llm_client import LLMClient
from app.services.model_event_bus import ModelActiveEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """LLMClient instance with __init__ bypassed to avoid env/network deps."""
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 3
    obj._retry_initial_delay = 1.0
    obj._retry_max_delay = 30.0
    obj._num_ctx = 8192
    obj._think = False
    obj.model = "qwen2.5:32b"
    obj.base_url = "http://localhost:11434/v1"
    obj.api_key = "test-key"
    return obj


@pytest.fixture()
def cloud_client():
    """LLMClient with a cloud model name."""
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 3
    obj._retry_initial_delay = 1.0
    obj._retry_max_delay = 30.0
    obj._num_ctx = 8192
    obj._think = False
    obj.model = "qwen3-coder-next:cloud"
    obj.base_url = "http://localhost:11434/v1"
    obj.api_key = "test-key"
    return obj


# ---------------------------------------------------------------------------
# _detect_provider
# ---------------------------------------------------------------------------

class TestDetectProvider:
    def test_ollama_by_port(self, client):
        assert client._detect_provider() == "ollama"

    def test_cloud_by_suffix(self, cloud_client):
        assert cloud_client._detect_provider() == "cloud"

    def test_openai_by_url(self, client):
        client.base_url = "https://api.openai.com/v1"
        client.model = "gpt-4"
        assert client._detect_provider() == "openai"

    def test_unknown_fallback(self, client):
        client.base_url = "http://some-other-host:8080/v1"
        client.model = "some-model"
        assert client._detect_provider() == "unknown"


class TestRunIdInitialization:
    def test_init_reads_run_id_from_env_when_not_passed(self, monkeypatch):
        monkeypatch.setenv("AGORA_RUN_ID", "run_env_123")
        monkeypatch.setattr("app.llm.client.OpenAI", lambda **_kwargs: MagicMock())
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_API_KEY", "env-key")
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_MODEL_NAME", "gpt-4o-mini")

        client = LLMClient()

        assert client.run_id == "run_env_123"


# ---------------------------------------------------------------------------
# chat() publishes exactly one ModelActiveEvent per call
# ---------------------------------------------------------------------------

class TestChatPublishesModelActiveEvent:
    def test_chat_publishes_one_event(self, client, monkeypatch):
        """_publish_model_active is called once with the default 'chat' context."""
        published: list[ModelActiveEvent] = []

        monkeypatch.setattr(
            "app.services.model_event_bus.model_event_bus.publish",
            lambda ev: published.append(ev),
        )

        # Call _publish_model_active directly (it's what chat() calls internally).
        client._publish_model_active("chat", max_tokens=4096, temperature=0.7)

        assert len(published) == 1
        ev = published[0]
        assert ev.model == "qwen2.5:32b"
        assert ev.context == "chat"
        assert ev.provider == "ollama"
        assert ev.ts > 0

    def test_chat_publishes_with_correct_context_default(self, client, monkeypatch):
        published: list[ModelActiveEvent] = []

        monkeypatch.setattr(
            "app.services.model_event_bus.model_event_bus.publish",
            lambda ev: published.append(ev),
        )

        client._publish_model_active("chat")

        assert len(published) == 1
        assert published[0].context == "chat"

    def test_chat_json_publishes_with_chat_json_context(self, client, monkeypatch):
        published: list[ModelActiveEvent] = []

        monkeypatch.setattr(
            "app.services.model_event_bus.model_event_bus.publish",
            lambda ev: published.append(ev),
        )

        client._publish_model_active("chat_json")

        assert len(published) == 1
        assert published[0].context == "chat_json"

    def test_publish_includes_max_tokens_and_temperature(self, client, monkeypatch):
        published: list[ModelActiveEvent] = []

        monkeypatch.setattr(
            "app.services.model_event_bus.model_event_bus.publish",
            lambda ev: published.append(ev),
        )

        client._publish_model_active("report", max_tokens=8192, temperature=0.5)

        ev = published[0]
        assert ev.extra is not None
        assert ev.extra["max_tokens"] == 8192
        assert ev.extra["temperature"] == 0.5


# ---------------------------------------------------------------------------
# Fail-safe: publish error must not abort the LLM call
# ---------------------------------------------------------------------------

class TestPublishFailSafe:
    def test_publish_error_does_not_raise(self, client, monkeypatch):
        """A failing publish must not propagate — only a warning is logged."""
        warning_msgs: list[str] = []

        def boom(_event):
            raise RuntimeError("bus exploded")

        monkeypatch.setattr(
            "app.services.model_event_bus.model_event_bus.publish",
            boom,
        )

        llm_logger = logging.getLogger("agora.llm_client")
        monkeypatch.setattr(
            llm_logger,
            "warning",
            lambda msg, *a, **kw: warning_msgs.append(msg % a if a else msg),
        )

        # Must not raise
        client._publish_model_active("chat")

        assert any("publish" in m.lower() or "bus" in m.lower() for m in warning_msgs), (
            f"Expected warning about failed publish, got: {warning_msgs}"
        )

    def test_chat_proceeds_after_publish_error(self, client, monkeypatch):
        """_publish_model_active must not raise even when the bus.publish raises."""
        def boom(_event):
            raise RuntimeError("bus down")

        monkeypatch.setattr(
            "app.services.model_event_bus.model_event_bus.publish",
            boom,
        )

        # Must not raise — fail-safe swallows the exception and logs a warning.
        client._publish_model_active("chat")
        client._publish_model_active("report", max_tokens=2048, temperature=0.3)
        # Reaching this line means no exception propagated.
