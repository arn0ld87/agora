"""Issue #593 — LLM_DISABLE_JSON_MODE semantics clarification.

Tests für alle vier Kombinationen:
  schema-yes / schema-no  ×  env-on / env-off

Neue Env-Vars:
  LLM_DISABLE_JSON_OBJECT_MODE  — unterdrückt {type: "json_object"}
  LLM_DISABLE_JSON_SCHEMA_MODE  — unterdrückt strict json_schema; fällt auf json_object + Pydantic-Validierung zurück
  LLM_DISABLE_JSON_MODE         — Legacy-Alias für LLM_DISABLE_JSON_OBJECT_MODE (Deprecation-Warning bei Startup)

Mock-only — kein Netzwerk.
"""
from __future__ import annotations

import warnings
from unittest.mock import MagicMock

from pydantic import BaseModel

from app.utils.llm_client import LLMClient, should_disable_openai_json_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SampleSchema(BaseModel):
    value: int
    label: str


_SAMPLE_JSON = '{"value": 42, "label": "test"}'
_PLAIN_JSON = '{"ok": true}'


def _make_client() -> LLMClient:
    """LLMClient ohne echten OpenAI-Init."""
    obj = LLMClient.__new__(LLMClient)
    obj._max_retries = 0
    obj._retry_initial_delay = 0.0
    obj._retry_max_delay = 0.0
    obj._num_ctx = 8192
    obj._think = False
    obj.api_key = "test"
    obj.model = "gpt-4o"
    obj.base_url = "https://api.openai.com/v1"
    obj.client = MagicMock()
    return obj


def _stub_chat(client: LLMClient, return_value: str) -> MagicMock:
    """Patch client.chat() und gib den aufgezeichneten response_format zurück."""
    mock = MagicMock(return_value=return_value)
    client.chat = mock  # type: ignore[method-assign]
    return mock


# ---------------------------------------------------------------------------
# 1. schema=None, env off  →  json_object
# ---------------------------------------------------------------------------

class TestNoSchemaEnvOff:
    """Ohne Schema und ohne Disable-Env wird json_object angefordert."""

    def test_response_format_is_json_object(self, monkeypatch) -> None:
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_SCHEMA_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        client = _make_client()
        mock = _stub_chat(client, _PLAIN_JSON)

        result = client.chat_json([{"role": "user", "content": "hi"}])

        assert result == {"ok": True}
        _, kwargs = mock.call_args
        assert kwargs.get("response_format") == {"type": "json_object"}


# ---------------------------------------------------------------------------
# 2. schema=None, env on  →  no response_format (plain call)
# ---------------------------------------------------------------------------

class TestNoSchemaEnvOn:
    """LLM_DISABLE_JSON_OBJECT_MODE=true unterdrückt json_object bei schema=None."""

    def test_response_format_is_none_with_new_env(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "true")
        monkeypatch.delenv("LLM_DISABLE_JSON_SCHEMA_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        client = _make_client()
        mock = _stub_chat(client, _PLAIN_JSON)

        result = client.chat_json([{"role": "user", "content": "hi"}])

        assert result == {"ok": True}
        _, kwargs = mock.call_args
        assert kwargs.get("response_format") is None

    def test_legacy_env_still_suppresses_json_object(self, monkeypatch) -> None:
        """LLM_DISABLE_JSON_MODE als Alias wirkt wie LLM_DISABLE_JSON_OBJECT_MODE."""
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "true")
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_SCHEMA_MODE", raising=False)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        client = _make_client()
        mock = _stub_chat(client, _PLAIN_JSON)

        result = client.chat_json([{"role": "user", "content": "hi"}])

        assert result == {"ok": True}
        _, kwargs = mock.call_args
        assert kwargs.get("response_format") is None


# ---------------------------------------------------------------------------
# 3. schema=SomeModel, env off  →  strict json_schema
# ---------------------------------------------------------------------------

class TestWithSchemaEnvOff:
    """Mit Schema und ohne Disable-Env wird strict json_schema angefordert."""

    def test_response_format_is_strict_json_schema(self, monkeypatch) -> None:
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_SCHEMA_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        client = _make_client()
        mock = _stub_chat(client, _SAMPLE_JSON)

        result = client.chat_json(
            [{"role": "user", "content": "hi"}],
            schema=_SampleSchema,
        )

        assert result["value"] == 42
        _, kwargs = mock.call_args
        rf = kwargs.get("response_format", {})
        assert rf.get("type") == "json_schema"
        assert rf["json_schema"].get("strict") is True


# ---------------------------------------------------------------------------
# 4. schema=SomeModel, LLM_DISABLE_JSON_SCHEMA_MODE=true  →  json_object fallback
# ---------------------------------------------------------------------------

class TestWithSchemaDisableSchemaMode:
    """LLM_DISABLE_JSON_SCHEMA_MODE=true mit Schema: fällt auf json_object zurück,
    Pydantic-Validierung erfolgt trotzdem."""

    def test_response_format_falls_back_to_json_object(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_DISABLE_JSON_SCHEMA_MODE", "true")
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        client = _make_client()
        mock = _stub_chat(client, _SAMPLE_JSON)

        result = client.chat_json(
            [{"role": "user", "content": "hi"}],
            schema=_SampleSchema,
        )

        assert result["value"] == 42
        _, kwargs = mock.call_args
        rf = kwargs.get("response_format", {})
        assert rf.get("type") == "json_object", (
            f"Expected json_object fallback, got: {rf}"
        )

    def test_legacy_disable_json_mode_does_not_suppress_schema_mode(self, monkeypatch) -> None:
        """LLM_DISABLE_JSON_MODE wirkt als Alias für OBJECT_MODE, nicht SCHEMA_MODE.
        Mit schema gesetzt bleibt strict json_schema aktiv."""
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "true")
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_SCHEMA_MODE", raising=False)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        client = _make_client()
        mock = _stub_chat(client, _SAMPLE_JSON)

        result = client.chat_json(
            [{"role": "user", "content": "hi"}],
            schema=_SampleSchema,
        )

        assert result["value"] == 42
        _, kwargs = mock.call_args
        rf = kwargs.get("response_format", {})
        # Legacy alias does NOT disable schema mode → strict json_schema still used
        assert rf.get("type") == "json_schema"


# ---------------------------------------------------------------------------
# 5. should_disable_openai_json_mode — wired to LLM_DISABLE_JSON_OBJECT_MODE
# ---------------------------------------------------------------------------

class TestShouldDisableOpenaiJsonMode:
    """should_disable_openai_json_mode respektiert LLM_DISABLE_JSON_OBJECT_MODE
    und den Legacy-Alias LLM_DISABLE_JSON_MODE."""

    def test_new_env_triggers_disable(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "true")
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        assert should_disable_openai_json_mode("https://api.openai.com/v1") is True

    def test_legacy_env_still_triggers_disable(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "true")
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        assert should_disable_openai_json_mode("https://api.openai.com/v1") is True

    def test_neither_env_set_returns_false(self, monkeypatch) -> None:
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        assert should_disable_openai_json_mode("https://api.openai.com/v1") is False

    def test_non_openai_base_url_returns_false(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "true")
        assert should_disable_openai_json_mode("http://localhost:11434") is False


# ---------------------------------------------------------------------------
# 6. Deprecation warning for legacy env at import/startup
# ---------------------------------------------------------------------------

class TestLegacyEnvDeprecationWarning:
    """Wenn LLM_DISABLE_JSON_MODE gesetzt ist, soll eine DeprecationWarning
    ausgegeben werden (einmalig bei erstem chat_json-Aufruf)."""

    def test_deprecation_warning_emitted(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_DISABLE_JSON_MODE", "true")
        monkeypatch.delenv("LLM_DISABLE_JSON_OBJECT_MODE", raising=False)
        monkeypatch.delenv("LLM_DISABLE_JSON_SCHEMA_MODE", raising=False)
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        client = _make_client()
        _stub_chat(client, _PLAIN_JSON)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.chat_json([{"role": "user", "content": "hi"}])

        messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        assert any("LLM_DISABLE_JSON_MODE" in m for m in messages), (
            f"Expected DeprecationWarning mentioning LLM_DISABLE_JSON_MODE, got: {messages}"
        )
