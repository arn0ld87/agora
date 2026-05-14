"""
Tests for LLMClient.chat_json strict-schema extension (Sub-Slice 05).

All tests are mock-only — no live LLM call is made.
"""

import pytest
from pydantic import BaseModel, ValidationError

from app.utils.llm_client import LLMClient


# ---------------------------------------------------------------------------
# Minimal Pydantic model used across tests
# ---------------------------------------------------------------------------

class Foo(BaseModel):
    x: int


# ---------------------------------------------------------------------------
# Fixture: LLMClient instance without hitting the constructor's env/network
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    """Return an LLMClient instance with __init__ bypassed via __new__."""
    obj = LLMClient.__new__(LLMClient)
    # Set only the attributes that chat_json / _maybe_validate need.
    obj._max_retries = 3
    obj._retry_initial_delay = 1.0
    obj._retry_max_delay = 30.0
    obj._num_ctx = 8192
    obj._think = False
    obj.model = "test-model"
    obj.base_url = "http://localhost:11434/v1"
    obj.api_key = "test-key"
    return obj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChatJsonLegacy:
    def test_chat_json_legacy_no_schema_keeps_json_object(self, client, monkeypatch):
        """Without schema the legacy json_object response_format must be used."""
        # Ensure json-mode is active regardless of the project .env setting.
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "false")
        captured: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat"):
            captured.append(response_format)
            return '{"result": "ok"}'

        monkeypatch.setattr(client, "chat", mock_chat)

        result = client.chat_json(messages=[{"role": "user", "content": "hi"}])

        assert result == {"result": "ok"}
        assert len(captured) == 1
        assert captured[0] == {"type": "json_object"}


class TestChatJsonStrictSchema:
    def test_chat_json_strict_schema_uses_json_schema_response_format(self, client, monkeypatch):
        """With a Pydantic schema the request must use json_schema response_format."""
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "false")
        captured: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json"):
            captured.append(response_format)
            return '{"x": 5}'

        monkeypatch.setattr(client, "chat", mock_chat)

        result = client.chat_json(
            messages=[{"role": "user", "content": "give me foo"}],
            schema=Foo,
            schema_name="foo",
        )

        assert result == {"x": 5}
        assert len(captured) == 1
        rf = captured[0]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "foo"
        assert rf["json_schema"]["strict"] is True
        schema_body = rf["json_schema"]["schema"]
        assert "properties" in schema_body
        assert "x" in schema_body["properties"]

    def test_chat_json_strict_validates_against_pydantic(self, client, monkeypatch):
        """Valid JSON validated against Pydantic model returns typed dict; invalid raises."""
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "false")
        # --- valid case ---
        monkeypatch.setattr(client, "chat", lambda **_kw: '{"x": 7}')
        result = client.chat_json(
            messages=[{"role": "user", "content": "q"}],
            schema=Foo,
        )
        assert result == {"x": 7}

        # --- invalid case ---
        monkeypatch.setattr(client, "chat", lambda **_kw: '{"x": "not-int"}')
        with pytest.raises(ValidationError):
            client.chat_json(
                messages=[{"role": "user", "content": "q"}],
                schema=Foo,
            )

    def test_chat_json_strict_falls_back_on_unsupported(self, client, monkeypatch):
        """On 'unknown response_format' exception the fallback to json_object is used."""
        import logging
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "false")

        call_count = 0
        warning_calls: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json"):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("unknown response_format type 'json_schema'")
            # Second call: fallback with json_object
            assert response_format == {"type": "json_object"}, (
                f"Fallback must use json_object, got {response_format}"
            )
            return '{"x": 1}'

        monkeypatch.setattr(client, "chat", mock_chat)

        # Patch logger.warning directly because setup_logger sets propagate=False,
        # so pytest caplog (which relies on propagation) cannot capture records.
        llm_logger = logging.getLogger("agora.llm_client")
        monkeypatch.setattr(llm_logger, "warning", lambda msg, *a, **kw: warning_calls.append(msg % a if a else msg))

        result = client.chat_json(
            messages=[{"role": "user", "content": "q"}],
            schema=Foo,
        )

        assert result == {"x": 1}
        assert call_count == 2
        # Warning log must contain "fall"
        assert any("fall" in msg.lower() for msg in warning_calls), (
            f"Expected fallback warning, got: {warning_calls}"
        )

    def test_chat_json_disable_json_mode_keeps_strict_schema(self, client, monkeypatch):
        """LLM_DISABLE_JSON_MODE=true must not disable schema-bound strict JSON."""
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "true")

        captured: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json"):
            captured.append(response_format)
            return '{"x": 99}'

        monkeypatch.setattr(client, "chat", mock_chat)

        result = client.chat_json(
            messages=[{"role": "user", "content": "q"}],
            schema=Foo,
        )

        assert result == {"x": 99}
        assert len(captured) == 1
        assert captured[0]["type"] == "json_schema"
        assert captured[0]["json_schema"]["strict"] is True

    def test_chat_json_dict_schema_no_server_validation(self, client, monkeypatch):
        """When schema is a plain dict the returned value is passed through unchanged."""
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "false")
        dict_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        captured: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json"):
            captured.append(response_format)
            return '{"name": "Agora"}'

        monkeypatch.setattr(client, "chat", mock_chat)

        result = client.chat_json(
            messages=[{"role": "user", "content": "q"}],
            schema=dict_schema,
            schema_name="name_obj",
        )

        assert result == {"name": "Agora"}
        rf = captured[0]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "name_obj"
        assert rf["json_schema"]["strict"] is True
