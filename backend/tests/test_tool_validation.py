"""Unit-Tests für services/tool_validation.py (Issue #47, EPIC-07-ST-03, Sub-Slice 2/3).

Sichern Parsing der drei unterstützten LLM-Antwort-Formate sowie die
Key-Alias-Normalisierung (``tool``→``name``, ``params``→``parameters``).
Auch die Re-Export-Identität in ``services/report_agent`` wird gepinnt.
"""

import json

from app.services import report_agent
from app.services import tool_validation
from app.services.tool_validation import (
    VALID_TOOL_NAMES,
    is_valid_tool_call,
    parse_tool_calls,
)


class TestValidToolNames:
    def test_contains_all_four_default_tools(self):
        assert VALID_TOOL_NAMES == frozenset({
            "insight_forge",
            "panorama_search",
            "quick_search",
            "interview_agents",
        })

    def test_is_immutable_frozenset(self):
        assert isinstance(VALID_TOOL_NAMES, frozenset)


class TestIsValidToolCall:
    def test_canonical_keys_pass(self):
        data = {"name": "quick_search", "parameters": {"query": "x"}}
        assert is_valid_tool_call(data) is True
        assert data == {"name": "quick_search", "parameters": {"query": "x"}}

    def test_alias_tool_normalized_to_name(self):
        data = {"tool": "insight_forge", "parameters": {}}
        assert is_valid_tool_call(data) is True
        assert "name" in data and "tool" not in data
        assert data["name"] == "insight_forge"

    def test_alias_params_normalized_to_parameters(self):
        data = {"name": "quick_search", "params": {"query": "x"}}
        assert is_valid_tool_call(data) is True
        assert "parameters" in data and "params" not in data

    def test_both_aliases_normalized(self):
        data = {"tool": "panorama_search", "params": {"query": "x"}}
        assert is_valid_tool_call(data) is True
        assert data == {"name": "panorama_search", "parameters": {"query": "x"}}

    def test_unknown_tool_name_rejected(self):
        data = {"name": "evil_tool", "parameters": {}}
        assert is_valid_tool_call(data) is False
        assert data == {"name": "evil_tool", "parameters": {}}

    def test_missing_name_rejected(self):
        assert is_valid_tool_call({"parameters": {}}) is False

    def test_empty_dict_rejected(self):
        assert is_valid_tool_call({}) is False

    def test_existing_parameters_not_overwritten_by_params_alias(self):
        """Wenn beide Keys vorhanden sind, gewinnt der kanonische ``parameters``."""
        data = {"name": "quick_search", "parameters": {"a": 1}, "params": {"b": 2}}
        assert is_valid_tool_call(data) is True
        assert data["parameters"] == {"a": 1}
        assert "params" in data  # nur normalisiert, wenn 'parameters' fehlt


class TestParseToolCallsXmlFormat:
    def test_single_xml_tool_call(self):
        resp = '<tool_call>{"name": "quick_search", "parameters": {"query": "test"}}</tool_call>'
        calls = parse_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0] == {"name": "quick_search", "parameters": {"query": "test"}}

    def test_multiple_xml_tool_calls_all_returned(self):
        resp = (
            '<tool_call>{"name": "quick_search", "parameters": {"query": "a"}}</tool_call>'
            ' some text '
            '<tool_call>{"name": "panorama_search", "parameters": {"query": "b"}}</tool_call>'
        )
        calls = parse_tool_calls(resp)
        assert len(calls) == 2
        assert calls[0]["name"] == "quick_search"
        assert calls[1]["name"] == "panorama_search"

    def test_xml_with_thinking_text_around_it(self):
        resp = (
            "I should search for this.\n"
            '<tool_call>{"name": "insight_forge", "parameters": {"query": "x"}}</tool_call>'
            "\nDone."
        )
        calls = parse_tool_calls(resp)
        assert len(calls) == 1

    def test_malformed_xml_json_returns_empty(self):
        resp = '<tool_call>{not valid json}</tool_call>'
        assert parse_tool_calls(resp) == []

    def test_xml_not_validated_against_valid_names(self):
        """XML-Format wird ohne Tool-Name-Whitelist akzeptiert (historisches Verhalten)."""
        resp = '<tool_call>{"name": "future_tool", "parameters": {}}</tool_call>'
        calls = parse_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0]["name"] == "future_tool"


class TestParseToolCallsRawJson:
    def test_raw_json_with_valid_tool_name(self):
        resp = json.dumps({"name": "quick_search", "parameters": {"query": "x"}})
        calls = parse_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0]["name"] == "quick_search"

    def test_raw_json_with_invalid_tool_name_dropped(self):
        resp = json.dumps({"name": "evil_tool", "parameters": {}})
        assert parse_tool_calls(resp) == []

    def test_raw_json_normalizes_aliases(self):
        resp = json.dumps({"tool": "insight_forge", "params": {"query": "x"}})
        calls = parse_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0] == {"name": "insight_forge", "parameters": {"query": "x"}}


class TestParseToolCallsTailJson:
    def test_thinking_text_then_trailing_json(self):
        resp = (
            "Let me think about this. I should use a search tool.\n"
            '{"name": "quick_search", "parameters": {"query": "test"}}'
        )
        calls = parse_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0]["name"] == "quick_search"

    def test_trailing_json_with_tool_alias(self):
        resp = 'Reasoning... {"tool": "panorama_search", "params": {"query": "x"}}'
        calls = parse_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0]["name"] == "panorama_search"

    def test_trailing_json_with_invalid_name_dropped(self):
        resp = 'Reasoning... {"name": "shell_exec", "parameters": {}}'
        assert parse_tool_calls(resp) == []


class TestParseToolCallsEdgeCases:
    def test_empty_response(self):
        assert parse_tool_calls("") == []

    def test_pure_text_no_json(self):
        assert parse_tool_calls("Just some thinking, no tool call here.") == []

    def test_xml_takes_priority_over_raw_json(self):
        """Wenn XML-Tag matched, werden Raw-/Tail-Fallbacks NICHT ausgewertet."""
        resp = (
            '<tool_call>{"name": "quick_search", "parameters": {}}</tool_call>'
            '\n{"name": "insight_forge", "parameters": {}}'
        )
        calls = parse_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0]["name"] == "quick_search"


class TestReportAgentReExport:
    def test_re_exports_module_objects(self):
        assert report_agent.parse_tool_calls is tool_validation.parse_tool_calls
        assert report_agent.is_valid_tool_call is tool_validation.is_valid_tool_call
        assert report_agent.VALID_TOOL_NAMES is tool_validation.VALID_TOOL_NAMES
