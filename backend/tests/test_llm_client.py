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
# MiniMax-eigene Plattform (api.minimax.io): `thinking`-Steuerung per Spec.
# `disabled` schaltet Reasoning bei MiniMax-M3 ab; gekoppelt an denselben
# think-Toggle wie Ollama (reasoning_effort / OLLAMA_THINKING).
# ---------------------------------------------------------------------------

_MINIMAX_URL = "https://api.minimax.io/v1"


def test_is_minimax_detects_platform():
    client = LLMClient(
        api_key="k", base_url=_MINIMAX_URL, model="MiniMax-M3", use_active_config=False
    )
    assert client._is_minimax() is True


def test_is_minimax_false_for_openai():
    client = LLMClient(
        api_key="k",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        use_active_config=False,
    )
    assert client._is_minimax() is False


def test_minimax_thinking_disabled_when_think_off(monkeypatch):
    monkeypatch.delenv("OLLAMA_THINKING", raising=False)
    client = LLMClient(
        api_key="k",
        base_url=_MINIMAX_URL,
        model="MiniMax-M3",
        use_active_config=False,
        reasoning_effort="none",
    )
    assert client._minimax_thinking_extra_body() == {"thinking": {"type": "disabled"}}


def test_minimax_thinking_adaptive_when_think_on(monkeypatch):
    monkeypatch.setenv("OLLAMA_THINKING", "true")
    client = LLMClient(
        api_key="k",
        base_url=_MINIMAX_URL,
        model="MiniMax-M3",
        use_active_config=False,
        reasoning_effort="high",
    )
    assert client._think is True
    assert client._minimax_thinking_extra_body() == {"thinking": {"type": "adaptive"}}


def test_minimax_force_no_thinking_overrides_think_on(monkeypatch):
    monkeypatch.setenv("OLLAMA_THINKING", "true")
    client = LLMClient(
        api_key="k",
        base_url=_MINIMAX_URL,
        model="MiniMax-M3",
        use_active_config=False,
        reasoning_effort="high",
    )
    assert client._minimax_thinking_extra_body(force_no_thinking=True) == {
        "thinking": {"type": "disabled"}
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChatJsonLegacy:
    def test_chat_json_legacy_no_schema_keeps_json_object(self, client, monkeypatch):
        """Without schema the legacy json_object response_format must be used."""
        # Ensure json-mode is active regardless of the project .env setting.
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        captured: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat", **kwargs):
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
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        captured: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json", **kwargs):
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
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
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
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")

        call_count = 0
        warning_calls: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json", **kwargs):
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

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json", **kwargs):
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
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        dict_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        captured: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json", **kwargs):
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


class TestChatForceNoThinking:
    def test_chat_force_no_thinking_overrides_extra_body_think(self, monkeypatch):
        """force_no_thinking=True muss extra_body['think']=False setzen, auch wenn reasoning_effort='medium'.

        Prueft, dass ein Ollama-Client mit aktiviertem Reasoning (self._think=True)
        bei force_no_thinking=True trotzdem think=False an die API sendet.
        """
        from unittest.mock import MagicMock

        # Client mit Ollama-Base-URL und Reasoning (self._think=True)
        obj = LLMClient.__new__(LLMClient)
        obj._max_retries = 1
        obj._retry_initial_delay = 0.0
        obj._retry_max_delay = 0.0
        obj._num_ctx = 8192
        obj._think = True  # Reasoning aktiviert (reasoning_effort="medium")
        obj.model = "kimi-k2.6"
        obj.base_url = "http://localhost:11434/v1"
        obj.api_key = "ollama"
        obj.run_id = None
        obj.routing_version = None
        obj.route_stage = None
        obj.route_provider_id = None

        # E2E-Stub deaktivieren
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)
        # Streaming deaktivieren, damit wir den einfachen Response-Pfad testen
        monkeypatch.setenv("LLM_FORCE_STREAM", "false")

        captured_kwargs: list = []

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage.completion_tokens = 5

        def fake_create(**kwargs):
            captured_kwargs.append(dict(kwargs))
            return mock_response

        # client-Attribut direkt setzen (nicht via patch.object — __new__ hat es nicht initialisiert)
        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.side_effect = fake_create
        obj.client = mock_openai_client

        obj.chat(
            messages=[{"role": "user", "content": "test"}],
            force_no_thinking=True,
        )

        assert len(captured_kwargs) >= 1, "Kein API-Call wurde abgesetzt"
        wire_call = captured_kwargs[0]
        extra_body = wire_call.get("extra_body", {})
        assert extra_body.get("think") is False, (
            f"force_no_thinking=True muss extra_body['think']=False setzen, "
            f"erhalten: {extra_body}"
        )


# ---------------------------------------------------------------------------
# Sub-Slice 05.1 — Native Ollama /api/chat-Pfad
# ---------------------------------------------------------------------------

class TestOllamaNativeSchemaPath:
    """Native /api/chat-Branch wird gezogen, wenn _is_ollama() und schema= gesetzt sind."""

    def _make_ollama_client(self):
        """LLMClient mit Ollama-URL (kein __init__)."""
        obj = LLMClient.__new__(LLMClient)
        obj._max_retries = 3
        obj._retry_initial_delay = 1.0
        obj._retry_max_delay = 30.0
        obj._num_ctx = 8192
        obj._think = False
        obj.model = "llama3.2"
        obj.base_url = "http://localhost:11434/v1"
        obj.api_key = "ollama"
        obj.run_id = None
        obj.routing_version = None
        obj.route_stage = None
        obj.route_provider_id = None
        return obj

    def test_ollama_native_path_used_for_schema_call(self, monkeypatch):
        """Bei base_url mit :11434 und schema= -> httpx POST gegen /api/chat statt OpenAI-SDK."""
        from unittest.mock import MagicMock, patch

        client = self._make_ollama_client()
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        captured_posts: list = []

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "message": {"content": '{"x": 42}'}
        }

        def fake_post(url, json=None, **kwargs):
            captured_posts.append({"url": url, "json": json})
            return mock_response

        with patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_ctx
            mock_ctx.post.side_effect = fake_post

            result = client.chat_json(
                messages=[{"role": "user", "content": "give me foo"}],
                schema=Foo,
            )

        assert result == {"x": 42}
        assert len(captured_posts) == 1, "Genau ein POST auf /api/chat erwartet"
        assert captured_posts[0]["url"].endswith("/api/chat"), (
            f"URL muss /api/chat sein, bekommen: {captured_posts[0]['url']}"
        )
        payload = captured_posts[0]["json"]
        assert "format" in payload, "format-Feld fehlt im Payload"
        fmt = payload["format"]
        assert fmt.get("type") == "object", f"format.type muss 'object' sein, bekommen: {fmt}"
        assert "properties" in fmt, "format.properties fehlt"

    def test_ollama_native_path_falls_through_on_http_error(self, monkeypatch):
        """Bei httpx-Fehler -> Fall-Through auf OpenAI-Wrapper-Pfad mit json_object-Fallback."""
        import logging
        from unittest.mock import MagicMock, patch
        import httpx

        client = self._make_ollama_client()
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        warning_msgs: list = []
        llm_logger = logging.getLogger("agora.llm_client")
        monkeypatch.setattr(
            llm_logger,
            "warning",
            lambda msg, *a, **kw: warning_msgs.append(msg % a if a else msg),
        )

        def fake_post(url, json=None, **kwargs):
            raise httpx.ConnectError("connection refused")

        openai_calls: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json", **kwargs):
            openai_calls.append(response_format)
            return '{"x": 9}'

        monkeypatch.setattr(client, "chat", mock_chat)

        with patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_ctx
            mock_ctx.post.side_effect = fake_post

            result = client.chat_json(
                messages=[{"role": "user", "content": "q"}],
                schema=Foo,
            )

        assert result == {"x": 9}
        assert len(openai_calls) >= 1, "Nach httpx-Fehler muss OpenAI-Pfad genutzt werden"
        assert any("fallback" in m.lower() or "fehlgeschlagen" in m.lower() for m in warning_msgs), (
            f"Kein Fallback-Warning gefunden: {warning_msgs}"
        )

    def test_non_ollama_provider_uses_openai_sdk_path(self, monkeypatch):
        """OpenAI-Provider (kein 11434 in base_url) -> kein /api/chat-Call, nur OpenAI-SDK."""
        from unittest.mock import patch

        obj = LLMClient.__new__(LLMClient)
        obj._max_retries = 3
        obj._retry_initial_delay = 1.0
        obj._retry_max_delay = 30.0
        obj._num_ctx = 4096
        obj._think = False
        obj.model = "gpt-4o"
        obj.base_url = "https://api.openai.com/v1"
        obj.api_key = "sk-test"
        obj.run_id = None
        obj.routing_version = None
        obj.route_stage = None
        obj.route_provider_id = None

        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        openai_calls: list = []

        def mock_chat(messages, temperature, max_tokens, response_format, context="chat_json", **kwargs):
            openai_calls.append(response_format)
            return '{"x": 3}'

        monkeypatch.setattr(obj, "chat", mock_chat)

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.side_effect = lambda **kw: (_ for _ in ()).throw(
                AssertionError("httpx.Client darf bei OpenAI-Provider nicht aufgerufen werden")
            )

            result = obj.chat_json(
                messages=[{"role": "user", "content": "q"}],
                schema=Foo,
            )

        assert result == {"x": 3}
        assert len(openai_calls) == 1, "Genau ein OpenAI-SDK-Call erwartet"
        rf = openai_calls[0]
        assert rf["type"] == "json_schema", f"OpenAI-Pfad muss json_schema nutzen, bekommen: {rf}"


class TestFlattenSchemaForOllama:
    """Unit-Tests fuer _flatten_pydantic_schema_for_ollama."""

    def test_resolves_defs_inline(self):
        """PlanResponse hat $defs (PlanSection) -> nach _flatten_pydantic_schema_for_ollama
        sind $defs/$ref ersetzt, properties.sections.items ist ein vollstaendiges Objekt."""
        from app.utils.llm_client import _flatten_pydantic_schema_for_ollama
        from app.services.report_agent.schemas import PlanResponse

        flat = _flatten_pydantic_schema_for_ollama(PlanResponse)

        assert "$defs" not in flat, "$defs darf im geflatteten Schema nicht mehr vorkommen"
        assert "$ref" not in str(flat), "$ref darf im geflatteten Schema nicht mehr vorkommen"
        items = flat["properties"]["sections"]["items"]
        assert items.get("type") == "object", (
            f"sections.items muss type=object sein, bekommen: {items}"
        )
        assert "properties" in items, "sections.items muss properties enthalten"

    def test_drops_title_and_schema_keys(self):
        """Top-level title und $schema sind raus, property-descriptions bleiben."""
        from app.utils.llm_client import _flatten_pydantic_schema_for_ollama

        class WithTitle(BaseModel):
            name: str

        flat = _flatten_pydantic_schema_for_ollama(WithTitle)

        assert "title" not in flat, "title darf im Top-Level nicht mehr vorkommen"
        assert "$schema" not in flat, "$schema darf im Top-Level nicht mehr vorkommen"
        assert "properties" in flat
        assert "name" in flat["properties"]

    def test_handles_cyclic_refs(self):
        """Selbst-referenzierende Pydantic-Models brechen nicht in Endlos-Rekursion."""
        from typing import Optional as Opt
        from app.utils.llm_client import _flatten_pydantic_schema_for_ollama

        class Node(BaseModel):
            value: int
            child: Opt["Node"] = None  # type: ignore[assignment]

        Node.model_rebuild()

        # Darf nicht in RecursionError enden
        flat = _flatten_pydantic_schema_for_ollama(Node)
        assert flat.get("type") == "object"
        assert "$ref" not in str(flat), "$ref darf im geflatteten Schema nicht mehr vorkommen"


# ---------------------------------------------------------------------------
# Sub-Slice 05.2 — OLLAMA_THINKING env überstimmt reasoning_effort
# ---------------------------------------------------------------------------


class TestOllamaThinkingEnvOverride:
    """LLMClient.__init__: OLLAMA_THINKING in der env hat Vorrang vor
    reasoning_effort-basiertem _think. Konsistent zu run_*_simulation.py.
    """

    def _make_client(self, monkeypatch, reasoning_effort):
        from unittest.mock import MagicMock
        monkeypatch.setattr("app.llm.client.OpenAI", lambda **_kwargs: MagicMock())
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_API_KEY", "k")
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_MODEL_NAME", "qwen3:8b")
        monkeypatch.setattr("app.llm.client._read_active_config_safely", lambda: None)
        return LLMClient(reasoning_effort=reasoning_effort, use_active_config=False)

    def test_ollama_thinking_false_overrides_reasoning_effort(self, monkeypatch):
        """OLLAMA_THINKING=false → _think=False, auch wenn reasoning_effort='medium'."""
        monkeypatch.setenv("OLLAMA_THINKING", "false")
        client = self._make_client(monkeypatch, reasoning_effort="medium")
        assert client._think is False, (
            "OLLAMA_THINKING=false muss reasoning_effort='medium' überstimmen"
        )

    def test_ollama_thinking_true_overrides_reasoning_effort_none(self, monkeypatch):
        """OLLAMA_THINKING=true → _think=True, auch wenn reasoning_effort='none'."""
        monkeypatch.setenv("OLLAMA_THINKING", "true")
        client = self._make_client(monkeypatch, reasoning_effort="none")
        assert client._think is True, (
            "OLLAMA_THINKING=true muss reasoning_effort='none' überstimmen"
        )

    def test_ollama_thinking_unset_uses_reasoning_effort(self, monkeypatch):
        """Ohne OLLAMA_THINKING → klassisches reasoning_effort-Mapping."""
        monkeypatch.delenv("OLLAMA_THINKING", raising=False)
        client_high = self._make_client(monkeypatch, reasoning_effort="high")
        client_none = self._make_client(monkeypatch, reasoning_effort="none")
        assert client_high._think is True
        assert client_none._think is False

    def test_ollama_thinking_accepts_aliases(self, monkeypatch):
        """Aliase '0'/'no'/'off' → False; '1'/'yes'/'on' → True."""
        for falsy in ("0", "no", "off", "False"):
            monkeypatch.setenv("OLLAMA_THINKING", falsy)
            client = self._make_client(monkeypatch, reasoning_effort="high")
            assert client._think is False, f"OLLAMA_THINKING={falsy!r} muss falsy sein"
        for truthy in ("1", "yes", "on", "TRUE"):
            monkeypatch.setenv("OLLAMA_THINKING", truthy)
            client = self._make_client(monkeypatch, reasoning_effort="none")
            assert client._think is True, f"OLLAMA_THINKING={truthy!r} muss truthy sein"


# ---------------------------------------------------------------------------
# Sub-Slice 05.3 — Ollama Cloud (ollama.com) Native-Pfad + Bearer Auth
# ---------------------------------------------------------------------------


class TestIsOllamaMatchesCloud:
    """_is_ollama() erkennt sowohl lokales (Port 11434) als auch Cloud
    (ollama.com) — beide hosten denselben /api/chat-Endpoint.
    """

    def _make(self, base_url, api_key="k"):
        obj = LLMClient.__new__(LLMClient)
        obj.base_url = base_url
        obj.api_key = api_key
        return obj

    def test_local_ollama_matches(self):
        assert self._make("http://localhost:11434/v1")._is_ollama() is True
        assert self._make("http://host.docker.internal:11434/v1")._is_ollama() is True

    def test_cloud_ollama_matches(self):
        assert self._make("https://ollama.com/v1")._is_ollama() is True
        assert self._make("https://ollama.com/api")._is_ollama() is True
        assert self._make("https://OLLAMA.COM/v1")._is_ollama() is True, "muss case-insensitiv sein"

    def test_openai_does_not_match(self):
        assert self._make("https://api.openai.com/v1")._is_ollama() is False
        assert self._make("https://api.together.xyz/v1")._is_ollama() is False


class TestOllamaCloudBearerAuth:
    """_ollama_chat_with_schema sendet Authorization: Bearer <api_key>,
    sodass der Native-Pfad auch gegen Ollama Cloud funktioniert.
    """

    def _make_cloud_client(self, api_key="test-cloud-key"):
        obj = LLMClient.__new__(LLMClient)
        obj._max_retries = 3
        obj._retry_initial_delay = 1.0
        obj._retry_max_delay = 30.0
        obj._num_ctx = 8192
        obj._think = False
        obj.model = "gpt-oss:120b"
        obj.base_url = "https://ollama.com/v1"
        obj.api_key = api_key
        obj.run_id = None
        obj.routing_version = None
        obj.route_stage = None
        obj.route_provider_id = None
        return obj

    def test_cloud_native_path_sends_bearer_header(self, monkeypatch):
        """Bei base_url=ollama.com + schema= → POST mit Authorization: Bearer."""
        from unittest.mock import MagicMock, patch

        client = self._make_cloud_client(api_key="cloud-secret-42")
        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        captured: list = []
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"message": {"content": '{"x": 1}'}}

        def fake_post(url, json=None, headers=None, **kwargs):
            captured.append({"url": url, "json": json, "headers": headers or {}})
            return mock_response

        with patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_ctx
            mock_ctx.post.side_effect = fake_post

            client.chat_json(
                messages=[{"role": "user", "content": "give foo"}],
                schema=Foo,
            )

        assert len(captured) == 1
        assert captured[0]["url"] == "https://ollama.com/api/chat", (
            f"Cloud-URL falsch zusammengesetzt: {captured[0]['url']}"
        )
        auth = captured[0]["headers"].get("Authorization", "")
        assert auth == "Bearer cloud-secret-42", (
            f"Authorization-Header fehlt oder falsch: {auth!r}"
        )

    def test_local_ollama_dummy_key_omits_bearer(self, monkeypatch):
        """Bei lokalem Ollama (api_key='ollama' Dummy) → kein Bearer-Header senden."""
        from unittest.mock import MagicMock, patch

        obj = LLMClient.__new__(LLMClient)
        obj._max_retries = 3
        obj._retry_initial_delay = 1.0
        obj._retry_max_delay = 30.0
        obj._num_ctx = 8192
        obj._think = False
        obj.model = "qwen3:8b"
        obj.base_url = "http://localhost:11434/v1"
        obj.api_key = "ollama"  # ignored by local Ollama
        obj.run_id = None
        obj.routing_version = None
        obj.route_stage = None
        obj.route_provider_id = None

        monkeypatch.delenv("LLM_DISABLE_JSON_MODE", raising=False)
        monkeypatch.setenv("LLM_DISABLE_JSON_OBJECT_MODE", "false")
        monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

        captured: list = []
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"message": {"content": '{"x": 7}'}}

        def fake_post(url, json=None, headers=None, **kwargs):
            captured.append({"headers": headers or {}})
            return mock_response

        with patch("httpx.Client") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_ctx
            mock_ctx.post.side_effect = fake_post

            obj.chat_json(
                messages=[{"role": "user", "content": "q"}],
                schema=Foo,
            )

        assert len(captured) == 1
        assert "Authorization" not in captured[0]["headers"], (
            "Lokaler Ollama-Pfad darf keinen Bearer-Header senden (Dummy-Key 'ollama')"
        )


# ---------------------------------------------------------------------------
# Sub-Slice 05.5 — Cloud-aware num_ctx-Heuristik
# ---------------------------------------------------------------------------


class TestResolveNumCtx:
    """_resolve_num_ctx folgt der Override-Hierarchie aus dem Slice-Plan."""

    def test_provider_options_explicit_wins(self, monkeypatch):
        """provider_options.num_ctx ist die höchste Prio (explizite Route)."""
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.setenv("LLM_CONTEXT_LIMIT", "12345")
        monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
        result = _resolve_num_ctx(model_name="gemini-3-pro", provider_options_num_ctx=4096)
        assert result == 4096, "provider_options muss alle anderen Quellen überstimmen"

    def test_per_model_env_map_overrides_heuristic(self, monkeypatch):
        """LLM_MODEL_CONTEXT_LIMITS_JSON pro-Modell-Map schlägt Heuristik."""
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.setenv(
            "LLM_MODEL_CONTEXT_LIMITS_JSON",
            '{"qwen3-coder-next:cloud": 65536}',
        )
        result = _resolve_num_ctx(
            model_name="qwen3-coder-next:cloud",
            provider_options_num_ctx=None,
        )
        assert result == 65536, "per-Modell-env-Map muss greifen"

    def test_heuristic_for_known_cloud_models(self, monkeypatch):
        """Heuristik liefert für bekannte Cloud-Modelle die echten Context-Windows."""
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)

        cases = {
            "gemini-3-pro:cloud": 1_048_576,
            "qwen3-coder-next:cloud": 262_144,
            "gpt-oss:120b": 131_072,
            "nemotron-3-nano:30b": 131_072,
            "deepseek-v3:cloud": 131_072,
            "claude-sonnet-4-6": 200_000,
        }
        for model, expected in cases.items():
            got = _resolve_num_ctx(model_name=model, provider_options_num_ctx=None)
            assert got == expected, f"{model}: erwartet {expected}, bekommen {got}"

    def test_unknown_model_falls_back_to_ollama_num_ctx(self, monkeypatch):
        """Unbekanntes Modell → OLLAMA_NUM_CTX (legacy) oder 8192 default."""
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
        result = _resolve_num_ctx(model_name="some-niche-model:7b", provider_options_num_ctx=None)
        assert result == 16384

    def test_unknown_model_default_8192(self, monkeypatch):
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
        result = _resolve_num_ctx(model_name="some-unknown:7b", provider_options_num_ctx=None)
        assert result == 8192

    def test_global_env_overrides_when_no_heuristic(self, monkeypatch):
        """LLM_CONTEXT_LIMIT greift wenn die Heuristik nichts liefert."""
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
        monkeypatch.setenv("LLM_CONTEXT_LIMIT", "32768")
        result = _resolve_num_ctx(model_name="unknown-model", provider_options_num_ctx=None)
        assert result == 32768

    def test_global_env_max_with_heuristic(self, monkeypatch):
        """Wenn Heuristik UND LLM_CONTEXT_LIMIT da → der größere Wert."""
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.setenv("LLM_CONTEXT_LIMIT", "2_000_000".replace("_", ""))
        result = _resolve_num_ctx(model_name="gemini-3-pro", provider_options_num_ctx=None)
        assert result == 2_000_000, "LLM_CONTEXT_LIMIT > Heuristik muss gewinnen"

    def test_invalid_per_model_json_falls_through(self, monkeypatch):
        """Kaputtes JSON in LLM_MODEL_CONTEXT_LIMITS_JSON → Fall-Through, kein crash."""
        from app.utils.llm_client import _resolve_num_ctx
        monkeypatch.setenv("LLM_MODEL_CONTEXT_LIMITS_JSON", "{not-json")
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
        result = _resolve_num_ctx(model_name="gemini-3-pro", provider_options_num_ctx=None)
        assert result == 1_048_576, "kaputtes env muss Heuristik nicht blockieren"


class TestLlmClientInitUsesResolveNumCtx:
    """LLMClient.__init__ verdrahtet _resolve_num_ctx korrekt."""

    def _make(self, monkeypatch, model="gemini-3-pro:cloud", provider_options=None):
        from unittest.mock import MagicMock
        monkeypatch.setattr("app.llm.client.OpenAI", lambda **_kw: MagicMock())
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_API_KEY", "k")
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_BASE_URL", "https://ollama.com/v1")
        monkeypatch.setattr("app.utils.llm_client.Config.LLM_MODEL_NAME", model)
        monkeypatch.setattr("app.llm.client._read_active_config_safely", lambda: None)
        return LLMClient(provider_options=provider_options, use_active_config=False)

    def test_init_picks_up_heuristic_for_cloud_model(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
        client = self._make(monkeypatch, model="gemini-3-pro:cloud")
        assert client._num_ctx == 1_048_576

    def test_init_provider_options_overrides(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
        client = self._make(
            monkeypatch,
            model="gemini-3-pro:cloud",
            provider_options={"num_ctx": 32_000},
        )
        assert client._num_ctx == 32_000

    def test_init_legacy_ollama_num_ctx_for_unknown_model(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
        client = self._make(monkeypatch, model="custom:fancy")
        assert client._num_ctx == 16384
