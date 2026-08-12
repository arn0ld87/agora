"""
Tests für native OpenAI function-calling im ReACT-Report-Loop.

B-1 (RED → GREEN nach Implementation).
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch



# ---------------------------------------------------------------------------
# Hilfsfunktionen / Factories
# ---------------------------------------------------------------------------

def _make_tool_call_obj(id_: str, name: str, arguments: dict) -> MagicMock:
    """Erzeugt einen Mock, der einem OpenAI ToolCall-Objekt ähnelt."""
    tc = MagicMock()
    tc.id = id_
    tc.type = "function"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_openai_response(
    content: str = "",
    tool_calls: list | None = None,
    finish_reason: str = "tool_calls",
) -> MagicMock:
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock()
    response.usage.completion_tokens = 42
    return response


def _make_stream_chunk(
    content: str | None = None,
    tool_call_delta: dict | None = None,
    finish_reason: str | None = None,
    tool_call_index: int = 0,
) -> MagicMock:
    """Erzeugt einen Mock-Stream-Chunk."""
    chunk = MagicMock()
    choice = MagicMock()
    choice.finish_reason = finish_reason
    delta = MagicMock()
    delta.content = content
    if tool_call_delta:
        tc_delta = MagicMock()
        tc_delta.index = tool_call_delta.get("index", tool_call_index)
        tc_delta.id = tool_call_delta.get("id")
        tc_delta.type = tool_call_delta.get("type")
        func_delta = MagicMock()
        func_delta.name = tool_call_delta.get("function", {}).get("name")
        func_delta.arguments = tool_call_delta.get("function", {}).get("arguments", "")
        tc_delta.function = func_delta
        delta.tool_calls = [tc_delta]
    else:
        delta.tool_calls = None
    choice.delta = delta
    chunk.choices = [choice]
    chunk.usage = None
    return chunk


# ---------------------------------------------------------------------------
# B-6: Schema-Test — get_openai_tools_schema()
# ---------------------------------------------------------------------------

class TestToolsSchemaOpenAIFormat:
    """B-6: tools.py::get_openai_tools_schema() liefert valides OpenAI-Format."""

    def test_tools_schema_has_openai_format(self) -> None:
        from app.services.report_agent.tools import get_openai_tools_schema

        agent = MagicMock()
        agent.web_tools = MagicMock()
        agent.web_tools.is_available.return_value = False

        schema = get_openai_tools_schema(agent)

        assert isinstance(schema, list)
        assert len(schema) >= 4  # mind. 4 core tools

        for tool in schema:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            params = func["parameters"]
            # Valides JSON-Schema
            assert params.get("type") == "object"
            assert "properties" in params

    def test_tools_schema_includes_web_tools_when_available(self) -> None:
        from app.services.report_agent.tools import get_openai_tools_schema

        agent = MagicMock()
        agent.web_tools = MagicMock()
        agent.web_tools.is_available.return_value = True

        schema = get_openai_tools_schema(agent)
        names = [t["function"]["name"] for t in schema]
        assert "web_search" in names
        assert "fetch_url" in names


# ---------------------------------------------------------------------------
# B-3: LLMClient.chat_with_tools — nicht-streaming (OpenAI-Provider)
# ---------------------------------------------------------------------------

class TestChatWithToolsOpenAIProvider:
    """B-3: chat_with_tools gibt normalisiertes ToolCallResponse zurück."""

    def _make_client(self) -> Any:
        from app.utils.llm_client import LLMClient
        with patch.object(LLMClient, "__init__", lambda self, **kw: None):
            client = LLMClient.__new__(LLMClient)
        # Minimale Attribute setzen
        client.model = "gpt-4o"
        client.base_url = "https://api.openai.com/v1"
        client.api_key = "test-key"
        client.reasoning_effort = "none"
        client.provider_options = {}
        client.run_id = None
        client.routing_version = None
        client.route_stage = None
        client.route_provider_id = None
        client._num_ctx = 8192
        client._think = False
        client._max_retries = 1
        client._retry_initial_delay = 0.0
        client._retry_max_delay = 0.0
        return client

    def test_chat_with_tools_returns_tool_calls_on_openai_provider(self) -> None:
        """Mockt OpenAI-SDK-Response mit message.tool_calls → normalisierten Return."""
        client = self._make_client()

        tool_call_obj = _make_tool_call_obj(
            "call_abc123", "insight_forge", {"query": "Zielgruppenanalyse"}
        )
        mock_response = _make_openai_response(
            content="",
            tool_calls=[tool_call_obj],
            finish_reason="tool_calls",
        )

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response
        client.client = mock_openai

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "insight_forge",
                    "description": "Deep analysis tool",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]

        with patch.dict("os.environ", {}, clear=False):
            result = client.chat_with_tools(
                messages=[{"role": "user", "content": "Analysiere Zielgruppe"}],
                tools=tools,
                temperature=0.5,
                max_tokens=4096,
                context="report",
            )

        assert result["finish_reason"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["id"] == "call_abc123"
        assert tc["name"] == "insight_forge"
        assert tc["arguments"] == {"query": "Zielgruppenanalyse"}

    def test_chat_with_tools_falls_back_to_xml_when_no_native_tool_calls(self) -> None:
        """Wenn message.tool_calls leer/None und Content XML enthält → leere tool_calls."""
        client = self._make_client()

        xml_content = '<tool_call>{"name": "quick_search", "parameters": {"query": "test"}}</tool_call>'
        mock_response = _make_openai_response(
            content=xml_content,
            tool_calls=None,
            finish_reason="stop",
        )

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response
        client.client = mock_openai

        tools: list = []

        with patch.dict("os.environ", {}, clear=False):
            result = client.chat_with_tools(
                messages=[{"role": "user", "content": "Suche"}],
                tools=tools,
                temperature=0.5,
                max_tokens=1024,
                context="report",
            )

        # Native tool_calls ist leer, aber content enthält XML
        assert result["tool_calls"] == []
        assert xml_content in result["content"]

    def test_chat_with_tools_routes_google_through_native_tools_path(self) -> None:
        """Gemini-OpenAI-Compat-Layer geht NICHT in den unknown-Branch.

        Vor diesem Fix matched ``generativelanguage.googleapis.com`` keinen
        Provider-Branch in ``_detect_provider``; ``chat_with_tools`` fiel auf
        XML-im-Prompt zurück. Gemini's Function-Filter rejected das XML mit
        ``MALFORMED_FUNCTION_CALL`` → doppelte Retries pro Section. Nach dem
        Fix wird ``googleapis.com`` als ``"google"`` erkannt, native
        ``tools=``-Pfad greift.
        """
        client = self._make_client()
        client.model = "gemini-3.1-pro-preview-customtools"
        client.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        tool_call_obj = _make_tool_call_obj(
            "call_gemini_xyz", "panorama_search", {"query": "Multiplikator"}
        )
        mock_response = _make_openai_response(
            content="",
            tool_calls=[tool_call_obj],
            finish_reason="tool_calls",
        )
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = mock_response
        client.client = mock_openai

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "panorama_search",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]

        with patch.dict("os.environ", {}, clear=False):
            result = client.chat_with_tools(
                messages=[{"role": "user", "content": "Suche"}],
                tools=tools,
                temperature=0.3,
                max_tokens=4096,
                context="report",
            )

        # Wenn Google in den unknown-Branch fiele, käme tool_calls=[]
        # zurück (chat-Fallback). Native Pfad muss die Tool-Call-Form
        # unverändert weiterreichen.
        assert result["finish_reason"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "panorama_search"
        assert result["tool_calls"][0]["arguments"] == {"query": "Multiplikator"}

    def test_chat_with_tools_unknown_provider_returns_empty_tool_calls(self) -> None:
        """Bei Provider 'unknown' → tool_calls=[], content enthält Text."""
        client = self._make_client()
        client.model = "some-unknown-model"
        client.base_url = "http://some-unknown-proxy.local/v1"

        mock_openai = MagicMock()
        # Simuliere eine Antwort ohne tool_calls
        mock_response = _make_openai_response(
            content="Ich kann keine Tools aufrufen.",
            tool_calls=None,
            finish_reason="stop",
        )
        mock_openai.chat.completions.create.return_value = mock_response
        client.client = mock_openai

        tools: list = [
            {"type": "function", "function": {"name": "insight_forge", "description": "test", "parameters": {}}}
        ]

        with patch.dict("os.environ", {}, clear=False):
            result = client.chat_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=tools,
                temperature=0.5,
                max_tokens=512,
                context="report",
            )

        assert result["tool_calls"] == []
        assert "Ich kann keine Tools" in result["content"]


# ---------------------------------------------------------------------------
# B-3: Streaming-Pfad — Tool-Call-Delta-Akkumulation
# ---------------------------------------------------------------------------

class TestChatWithToolsStreaming:
    """B-3: Streaming-Chunks mit Tool-Call-Deltas werden korrekt reassembliert."""

    def _make_ollama_client(self) -> Any:
        from app.utils.llm_client import LLMClient
        with patch.object(LLMClient, "__init__", lambda self, **kw: None):
            client = LLMClient.__new__(LLMClient)
        client.model = "qwen3-coder-next:cloud"
        client.base_url = "http://localhost:11434/v1"
        client.api_key = "test-key"
        client.reasoning_effort = "none"
        client.provider_options = {}
        client.run_id = None
        client.routing_version = None
        client.route_stage = None
        client.route_provider_id = None
        client._num_ctx = 8192
        client._think = False
        client._max_retries = 1
        client._retry_initial_delay = 0.0
        client._retry_max_delay = 0.0
        return client

    def test_chat_with_tools_streaming_path_accumulates_tool_calls(self) -> None:
        """Streaming-Chunks mit Tool-Call-Deltas werden zu einem Tool-Call zusammengefügt."""
        client = self._make_ollama_client()

        # Simuliere OpenAI-Streaming-Chunks für einen Tool-Call
        chunks = [
            _make_stream_chunk(
                tool_call_delta={
                    "index": 0,
                    "id": "call_stream_01",
                    "type": "function",
                    "function": {"name": "panorama_search", "arguments": ""},
                }
            ),
            _make_stream_chunk(
                tool_call_delta={
                    "index": 0,
                    "id": None,
                    "type": None,
                    "function": {"name": None, "arguments": '{"query":'},
                }
            ),
            _make_stream_chunk(
                tool_call_delta={
                    "index": 0,
                    "id": None,
                    "type": None,
                    "function": {"name": None, "arguments": ' "Marktanalyse"}'},
                }
            ),
            _make_stream_chunk(finish_reason="tool_calls"),
        ]

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = iter(chunks)
        client.client = mock_openai

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "panorama_search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]

        with patch.dict("os.environ", {"LLM_FORCE_STREAM": "true"}, clear=False):
            result = client.chat_with_tools(
                messages=[{"role": "user", "content": "Suche Markt"}],
                tools=tools,
                temperature=0.5,
                max_tokens=1024,
                context="report",
            )

        assert result["finish_reason"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["name"] == "panorama_search"
        assert tc["arguments"]["query"] == "Marktanalyse"


# ---------------------------------------------------------------------------
# B-4: ReACT-Loop — native tool_calls (Feature-Flag = "native")
# ---------------------------------------------------------------------------

class TestReactLoopNativeToolCalls:
    """B-4: generate_section_react nutzt chat_with_tools wenn Flag = 'native'."""

    def _make_minimal_agent(self) -> MagicMock:
        agent = MagicMock()
        agent.llm = MagicMock()
        agent.SECTION_SYSTEM_PROMPT_TEMPLATE = (
            "System {report_title} {report_summary} {simulation_requirement} "
            "{section_title} {tools_description} {language}"
        )
        agent.SECTION_USER_PROMPT_TEMPLATE = (
            "User {previous_content} {section_title}"
        )
        agent.REACT_INSUFFICIENT_TOOLS_MSG = "Insufficient tools {tool_calls_count} {min_tool_calls} {unused_hint}"
        agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT = "Alt {tool_calls_count} {min_tool_calls} {unused_hint}"
        agent.REACT_TOOL_LIMIT_MSG = "Limit {tool_calls_count} {max_tool_calls}"
        agent.REACT_UNUSED_TOOLS_HINT = "Unused {unused_list}"
        agent.REACT_OBSERVATION_TEMPLATE = (
            "Obs {tool_name} {result} {tool_calls_count} {max_tool_calls} {used_tools_str} {unused_hint}"
        )
        agent.REACT_FORCE_FINAL_MSG = "Force final"
        agent.MAX_TOOL_CALLS_PER_SECTION = 5
        agent.report_logger = None
        agent.console_logger = None
        agent._current_section_index = None
        agent._active_section_evidence = []
        agent.simulation_requirement = "Test-Requirement"
        agent._get_tools_description.return_value = "Tools desc"
        agent._get_openai_tools_schema.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "panorama_search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]
        agent._execute_tool.return_value = "Tool result stub"
        agent._parse_tool_calls.return_value = []
        return agent

    def _make_section(self, title: str = "Segment-Analyse") -> MagicMock:
        section = MagicMock()
        section.title = title
        return section

    def _make_outline(self) -> MagicMock:
        outline = MagicMock()
        outline.title = "Test Report"
        outline.summary = "Test Summary"
        return outline

    def test_react_loop_uses_native_tool_calls_when_flag_enabled(self) -> None:
        """Mit REPORT_TOOLCALL_MODE=native ruft generate_section_react chat_with_tools auf."""
        from app.services.report_agent.workflow import generate_section_react

        agent = self._make_minimal_agent()

        # Erster Call: tool_call zurückgeben
        # Zweiter-Vierter Call: weitere tool_calls (min_tool_calls=3)
        # Fünfter Call: Final Answer
        tool_calls_sequence = [
            {
                "content": "",
                "tool_calls": [{"id": "c1", "name": "panorama_search", "arguments": {"query": "q1"}}],
                "finish_reason": "tool_calls",
                "raw_response": None,
            },
            {
                "content": "",
                "tool_calls": [{"id": "c2", "name": "panorama_search", "arguments": {"query": "q2"}}],
                "finish_reason": "tool_calls",
                "raw_response": None,
            },
            {
                "content": "",
                "tool_calls": [{"id": "c3", "name": "panorama_search", "arguments": {"query": "q3"}}],
                "finish_reason": "tool_calls",
                "raw_response": None,
            },
            {
                # Länge realistisch gewählt: der Final-Content-Contract lehnt
                # Abschnitte unter MIN_CONTENT_CHARS als unbrauchbar ab.
                "content": (
                    "Final Answer: Hier ist die Segment-Analyse der simulierten "
                    "Zielgruppen mit den beobachteten Reaktionsmustern."
                ),
                "tool_calls": [],
                "finish_reason": "stop",
                "raw_response": None,
            },
        ]
        agent.llm.chat_with_tools.side_effect = tool_calls_sequence

        section = self._make_section()
        outline = self._make_outline()

        with patch.dict("os.environ", {"REPORT_TOOLCALL_MODE": "native"}):
            # Config muss neu gelesen werden — patch Config direkt
            with patch("app.services.report_agent.workflow.Config") as mock_cfg:
                mock_cfg.REPORT_TOOLCALL_MODE = "native"
                mock_cfg.REPORT_LANGUAGE = "German"
                result = generate_section_react(
                    agent=agent,
                    section=section,
                    outline=outline,
                    previous_sections=[],
                    section_index=0,
                )

        # Final Answer wurde zurückgegeben — strenge Substring-Assertion (vorher: `in r or r`
        # war wegen Truthiness-Bug immer True, hat also nichts verifiziert).
        assert isinstance(result, str)
        assert "Segment-Analyse" in result
        assert agent.llm.chat_with_tools.called
        assert agent._execute_tool.call_count >= 3

    def test_react_loop_native_none_content_triggers_retry_not_typeerror(self) -> None:
        """Issue #1277-1: ``content: None`` + leere ``tool_calls`` auf dem nativen
        Pfad darf keinen TypeError werfen, der den Section dauerhaft auf
        ``generation_failed`` setzt. Der bestehende None-Guard (Retry mit
        „Response empty") muss stattdessen greifen — ein folgender Versuch darf
        die Section noch erfolgreich abschließen.
        """
        from app.services.report_agent.workflow import generate_section_react

        agent = self._make_minimal_agent()

        # Erster Call: content=None, tool_calls=[] (z. B. erschöpftes max_tokens
        # oder Safety-Filter). Danach drei Tool-Calls (min_tool_calls=3) und
        # schließlich der Final Answer.
        tool_calls_sequence = [
            {
                "content": None,
                "tool_calls": [],
                "finish_reason": "stop",
                "raw_response": None,
            },
            {
                "content": "",
                "tool_calls": [{"id": "c1", "name": "panorama_search", "arguments": {"query": "q1"}}],
                "finish_reason": "tool_calls",
                "raw_response": None,
            },
            {
                "content": "",
                "tool_calls": [{"id": "c2", "name": "panorama_search", "arguments": {"query": "q2"}}],
                "finish_reason": "tool_calls",
                "raw_response": None,
            },
            {
                "content": "",
                "tool_calls": [{"id": "c3", "name": "panorama_search", "arguments": {"query": "q3"}}],
                "finish_reason": "tool_calls",
                "raw_response": None,
            },
            {
                "content": (
                    "Final Answer: Segment-Analyse der simulierten Zielgruppen "
                    "mit den beobachteten Reaktionsmustern."
                ),
                "tool_calls": [],
                "finish_reason": "stop",
                "raw_response": None,
            },
        ]
        agent.llm.chat_with_tools.side_effect = tool_calls_sequence

        section = self._make_section()
        outline = self._make_outline()

        with patch("app.services.report_agent.workflow.Config") as mock_cfg:
            mock_cfg.REPORT_TOOLCALL_MODE = "native"
            mock_cfg.REPORT_LANGUAGE = "German"
            result = generate_section_react(
                agent=agent,
                section=section,
                outline=outline,
                previous_sections=[],
                section_index=0,
            )

        # Vor dem Fix warf Zeile 516 ``"Final Answer:" in None`` einen TypeError,
        # den _safe_generate_section_react abfing → SECTION_FALLBACK_BODY,
        # Section dauerhaft generation_failed. Nach dem Fix greift der None-Retry,
        # der fünfte Call liefert den Final Answer.
        assert isinstance(result, str)
        assert "Segment-Analyse" in result
        assert agent.llm.chat_with_tools.call_count == 5

    def test_react_loop_falls_back_to_xml_when_flag_disabled(self) -> None:
        """Mit REPORT_TOOLCALL_MODE=xml bleibt der alte XML-Parsing-Pfad aktiv."""
        from app.services.report_agent.workflow import generate_section_react

        agent = self._make_minimal_agent()

        # chat() gibt XML-Tool-Calls zurück, dann Final Answer
        chat_responses = [
            '<tool_call>{"name": "panorama_search", "parameters": {"query": "q1"}}</tool_call>',
            '<tool_call>{"name": "quick_search", "parameters": {"query": "q2"}}</tool_call>',
            '<tool_call>{"name": "insight_forge", "parameters": {"query": "q3"}}</tool_call>',
            # Siehe oben: MIN_CONTENT_CHARS des Final-Content-Contracts.
            (
                "Final Answer: Ergebnis der Analyse mit den zentralen "
                "Reaktionsmustern der simulierten Gruppen."
            ),
        ]
        agent.llm.chat.side_effect = chat_responses

        # _parse_tool_calls muss für XML-Content funktionieren
        from app.services.tool_validation import parse_tool_calls as real_parse
        agent._parse_tool_calls.side_effect = real_parse

        section = self._make_section()
        outline = self._make_outline()

        with patch("app.services.report_agent.workflow.Config") as mock_cfg:
            mock_cfg.REPORT_TOOLCALL_MODE = "xml"
            mock_cfg.REPORT_LANGUAGE = "German"
            result = generate_section_react(
                agent=agent,
                section=section,
                outline=outline,
                previous_sections=[],
                section_index=0,
            )

        # XML-Pfad: chat() wurde aufgerufen, NICHT chat_with_tools
        assert agent.llm.chat.called
        assert not agent.llm.chat_with_tools.called
        assert "Ergebnis" in result


# ---------------------------------------------------------------------------
# B-3 / B-stub: E2E-Stub-Pfad für chat_with_tools
# ---------------------------------------------------------------------------

class TestChatWithToolsE2EStub:
    """B-3: AGORA_E2E_LLM_MODE=stub liefert deterministischen Tool-Call-Return."""

    def _make_client(self) -> Any:
        from app.utils.llm_client import LLMClient
        with patch.object(LLMClient, "__init__", lambda self, **kw: None):
            client = LLMClient.__new__(LLMClient)
        client.model = "gpt-4o"
        client.base_url = "https://api.openai.com/v1"
        client.api_key = "test-key"
        client.reasoning_effort = "none"
        client.provider_options = {}
        client.run_id = None
        client.routing_version = None
        client.route_stage = None
        client.route_provider_id = None
        client._num_ctx = 8192
        client._think = False
        client._max_retries = 1
        client._retry_initial_delay = 0.0
        client._retry_max_delay = 0.0
        return client

    def test_e2e_stub_chat_with_tools_response(self) -> None:
        """AGORA_E2E_LLM_MODE=stub gibt ToolCallResponse ohne echten LLM-Call zurück."""
        client = self._make_client()
        # client.client darf nicht aufgerufen werden im Stub-Modus
        client.client = MagicMock()
        client.client.chat.completions.create.side_effect = RuntimeError(
            "Sollte im Stub-Modus nicht aufgerufen werden"
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "panorama_search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        with patch.dict("os.environ", {"AGORA_E2E_LLM_MODE": "stub"}):
            result = client.chat_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=tools,
                context="report",
            )

        assert "tool_calls" in result
        assert "content" in result
        assert "finish_reason" in result
        # Stub darf kein RuntimeError werfen
        client.client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# Gemini-Followup: Schema-Heuristik + JSON-Parse-Logging
# ---------------------------------------------------------------------------


class TestToolsSchemaHeuristics:
    """Schema-Generierung markiert Parameter mit korrektem Typ und required-Flag."""

    def _schema_for_tool(self, tool_name: str) -> dict:
        from app.services.report_agent.tools import get_openai_tools_schema

        agent = MagicMock()
        agent.web_tools = MagicMock()
        agent.web_tools.is_available.return_value = False
        schema = get_openai_tools_schema(agent)
        match = next((t for t in schema if t["function"]["name"] == tool_name), None)
        assert match is not None, f"Tool {tool_name} nicht im Schema"
        return match["function"]["parameters"]

    def test_limit_param_is_integer_type(self) -> None:
        params = self._schema_for_tool("quick_search")
        props = params["properties"]
        assert "limit" in props
        assert props["limit"]["type"] == "integer"

    def test_max_agents_param_is_integer_type(self) -> None:
        params = self._schema_for_tool("interview_agents")
        props = params["properties"]
        if "max_agents" in props:
            assert props["max_agents"]["type"] == "integer"

    def test_required_params_include_query(self) -> None:
        params = self._schema_for_tool("quick_search")
        assert "query" in params["required"], (
            "query muss als required markiert sein, sonst lässt das LLM es weg"
        )

    def test_optional_params_excluded_from_required(self) -> None:
        from app.services.report_agent.tools import get_openai_tools_schema

        fake_agent = MagicMock()
        fake_agent.web_tools = MagicMock()
        fake_agent.web_tools.is_available.return_value = False

        with patch(
            "app.services.report_agent.tools.define_tools",
            return_value={
                "fake_tool": {
                    "description": "Fake tool",
                    "parameters": {
                        "query": "the search query",
                        "extra": "optional additional filter",
                    },
                },
            },
        ):
            schema = get_openai_tools_schema(fake_agent)

        params = schema[0]["function"]["parameters"]
        assert "query" in params["required"]
        assert "extra" not in params["required"]


class TestToolArgumentJsonLogging:
    """Ungültiges Tool-Argument-JSON wird mit warning geloggt."""

    def test_non_streaming_logs_warning_on_invalid_json(self) -> None:
        from app.utils import llm_client as llm_client_mod

        msg = MagicMock()
        tc = MagicMock()
        tc.id = "tc1"
        tc.function = MagicMock()
        tc.function.name = "quick_search"
        tc.function.arguments = "not valid {json"
        msg.tool_calls = [tc]

        with patch.object(llm_client_mod.logger, "warning") as warn:
            result = llm_client_mod._extract_tool_calls_from_message(msg)

        assert result == [{"id": "tc1", "name": "quick_search", "arguments": {}}]
        assert warn.called
        msg_fmt = warn.call_args[0][0]
        assert "failed to parse tool arguments" in msg_fmt

    def test_streaming_logs_warning_on_invalid_json(self) -> None:
        from app.utils import llm_client as llm_client_mod

        chunks = [
            _make_stream_chunk(
                tool_call_delta={
                    "index": 0,
                    "id": "tc1",
                    "function": {"name": "quick_search", "arguments": "{broken"},
                },
            ),
            _make_stream_chunk(finish_reason="tool_calls"),
        ]

        with patch.object(llm_client_mod.logger, "warning") as warn:
            content, tool_calls, finish = (
                llm_client_mod._accumulate_streaming_tool_calls(chunks)
            )

        assert finish == "tool_calls"
        assert len(tool_calls) == 1
        assert tool_calls[0]["arguments"] == {}
        assert warn.called
        msg_fmt = warn.call_args[0][0]
        assert "failed to parse streaming tool arguments" in msg_fmt
