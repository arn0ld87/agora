"""Unit-Tests für services/tool_execution.py (Issue #47, Sub-Slice 3/3).

Mockt ``GraphToolsService`` und ``WebToolsService`` und schickt jeden
Tool-Pfad einmal durch ``execute_tool``. Sichert auch
Backwards-Compat-Redirects (``search_graph`` → ``quick_search``,
``get_simulation_context`` → ``insight_forge``), den Evidence-Callback
und das Exception-Swallowing.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import report_agent
from app.services import tool_execution
from app.services.tool_execution import execute_tool


def _structured(text: str = "rendered text"):
    """Stub für ein structured_result mit ``.to_text()``-Methode."""
    return SimpleNamespace(to_text=lambda: text)


@pytest.fixture
def graph_tools():
    return MagicMock()


@pytest.fixture
def web_tools():
    return MagicMock()


@pytest.fixture
def kwargs(graph_tools, web_tools):
    """Gemeinsame Pflicht-kwargs für ``execute_tool``-Aufrufe."""
    return dict(
        graph_tools=graph_tools,
        web_tools=web_tools,
        graph_id="g-1",
        simulation_id="sim-1",
        simulation_requirement="Was passiert wenn X?",
    )


class TestInsightForge:
    def test_uses_parameter_context_over_report_context(self, kwargs, graph_tools):
        graph_tools.insight_forge.return_value = _structured("ifs result")
        result = execute_tool(
            tool_name="insight_forge",
            parameters={"query": "q", "report_context": "param-ctx"},
            report_context="fallback-ctx",
            **kwargs,
        )
        assert result == "ifs result"
        graph_tools.insight_forge.assert_called_once_with(
            graph_id="g-1",
            query="q",
            simulation_requirement="Was passiert wenn X?",
            report_context="param-ctx",
        )

    def test_falls_back_to_report_context_arg(self, kwargs, graph_tools):
        graph_tools.insight_forge.return_value = _structured()
        execute_tool(
            tool_name="insight_forge",
            parameters={"query": "q"},
            report_context="fallback-ctx",
            **kwargs,
        )
        assert graph_tools.insight_forge.call_args.kwargs["report_context"] == "fallback-ctx"


class TestPanoramaSearch:
    def test_default_includes_expired(self, kwargs, graph_tools):
        graph_tools.panorama_search.return_value = _structured()
        execute_tool(
            tool_name="panorama_search",
            parameters={"query": "q"},
            report_context="",
            **kwargs,
        )
        assert graph_tools.panorama_search.call_args.kwargs["include_expired"] is True

    @pytest.mark.parametrize("raw,expected", [
        ("true", True), ("True", True), ("1", True), ("yes", True),
        ("false", False), ("0", False), ("no", False), ("nope", False),
    ])
    def test_string_include_expired_is_coerced(self, kwargs, graph_tools, raw, expected):
        graph_tools.panorama_search.return_value = _structured()
        execute_tool(
            tool_name="panorama_search",
            parameters={"query": "q", "include_expired": raw},
            report_context="",
            **kwargs,
        )
        assert graph_tools.panorama_search.call_args.kwargs["include_expired"] is expected


class TestQuickSearch:
    def test_default_limit_is_10(self, kwargs, graph_tools):
        graph_tools.quick_search.return_value = _structured()
        execute_tool(
            tool_name="quick_search",
            parameters={"query": "q"},
            report_context="",
            **kwargs,
        )
        assert graph_tools.quick_search.call_args.kwargs["limit"] == 10

    def test_string_limit_is_int_coerced(self, kwargs, graph_tools):
        graph_tools.quick_search.return_value = _structured()
        execute_tool(
            tool_name="quick_search",
            parameters={"query": "q", "limit": "25"},
            report_context="",
            **kwargs,
        )
        assert graph_tools.quick_search.call_args.kwargs["limit"] == 25


class TestInterviewAgents:
    def test_topic_falls_back_to_query(self, kwargs, graph_tools):
        graph_tools.interview_agents.return_value = _structured()
        execute_tool(
            tool_name="interview_agents",
            parameters={"query": "Wie reagieren Eltern?"},
            report_context="",
            **kwargs,
        )
        assert graph_tools.interview_agents.call_args.kwargs["interview_requirement"] == "Wie reagieren Eltern?"

    def test_max_agents_capped_at_10(self, kwargs, graph_tools):
        graph_tools.interview_agents.return_value = _structured()
        execute_tool(
            tool_name="interview_agents",
            parameters={"interview_topic": "t", "max_agents": "99"},
            report_context="",
            **kwargs,
        )
        assert graph_tools.interview_agents.call_args.kwargs["max_agents"] == 10


class TestSearchSimulationActions:
    """Issue #1778, Schritt 1.7: Dispatch des Werkzeugs für Simulationsbeiträge."""

    @staticmethod
    def _patch_search(monkeypatch, text: str = "beiträge"):
        from app.services.report_agent import action_search

        calls = []

        def fake_search(**search_kwargs):
            calls.append(search_kwargs)
            return _structured(text)

        monkeypatch.setattr(action_search, "search_simulation_actions", fake_search)
        return calls

    def test_dispatches_with_coerced_parameters(self, kwargs, monkeypatch):
        calls = self._patch_search(monkeypatch)

        result = execute_tool(
            tool_name="search_simulation_actions",
            parameters={
                "query": "Schließung",
                "agent_name": "Hebamme",
                "round_from": "2",
                "round_to": 5,
                "limit": "8",
            },
            report_context="",
            **kwargs,
        )

        assert result == "beiträge"
        assert calls == [
            {
                "simulation_id": "sim-1",
                "query": "Schließung",
                "agent_name": "Hebamme",
                "round_from": 2,
                "round_to": 5,
                "limit": 8,
            }
        ]

    def test_defaults_without_parameters(self, kwargs, monkeypatch):
        calls = self._patch_search(monkeypatch)

        execute_tool(
            tool_name="search_simulation_actions",
            parameters={},
            report_context="",
            **kwargs,
        )

        assert calls == [
            {
                "simulation_id": "sim-1",
                "query": "",
                "agent_name": "",
                "round_from": None,
                "round_to": None,
                "limit": 12,
            }
        ]

    def test_result_is_recorded_as_evidence(self, kwargs, monkeypatch):
        self._patch_search(monkeypatch, "gerendert")
        recorded = []

        execute_tool(
            tool_name="search_simulation_actions",
            parameters={"query": "q"},
            report_context="",
            record_evidence=lambda *args: recorded.append(args),
            section_index=4,
            **kwargs,
        )

        assert len(recorded) == 1
        assert recorded[0][0] == "search_simulation_actions"
        assert recorded[0][3] == "gerendert"
        assert recorded[0][4] == 4


class TestWebTools:
    def test_web_search_uses_format_search_result(self, kwargs, web_tools):
        web_tools.web_search.return_value = "raw"
        web_tools.format_search_result.return_value = "formatted search"
        result = execute_tool(
            tool_name="web_search",
            parameters={"query": "q", "max_results": "3"},
            report_context="",
            **kwargs,
        )
        assert result == "formatted search"
        web_tools.web_search.assert_called_once_with(query="q", max_results=3)

    def test_web_search_invalid_max_results_falls_back_to_5(self, kwargs, web_tools):
        web_tools.web_search.return_value = "raw"
        web_tools.format_search_result.return_value = "ok"
        execute_tool(
            tool_name="web_search",
            parameters={"query": "q", "max_results": "abc"},
            report_context="",
            **kwargs,
        )
        assert web_tools.web_search.call_args.kwargs["max_results"] == 5

    def test_fetch_url_uses_format_extract_result(self, kwargs, web_tools):
        web_tools.fetch_url.return_value = "raw"
        web_tools.format_extract_result.return_value = "formatted extract"
        result = execute_tool(
            tool_name="fetch_url",
            parameters={"url": "https://example.com"},
            report_context="",
            **kwargs,
        )
        assert result == "formatted extract"
        web_tools.fetch_url.assert_called_once_with(url="https://example.com")


class TestBackwardsCompatRedirects:
    def test_search_graph_redirects_to_quick_search(self, kwargs, graph_tools):
        graph_tools.quick_search.return_value = _structured("via redirect")
        result = execute_tool(
            tool_name="search_graph",
            parameters={"query": "q", "limit": 5},
            report_context="",
            **kwargs,
        )
        assert result == "via redirect"
        graph_tools.quick_search.assert_called_once()
        graph_tools.panorama_search.assert_not_called()

    def test_get_simulation_context_redirects_to_insight_forge(self, kwargs, graph_tools):
        graph_tools.insight_forge.return_value = _structured("via redirect")
        result = execute_tool(
            tool_name="get_simulation_context",
            parameters={},
            report_context="",
            **kwargs,
        )
        assert result == "via redirect"
        graph_tools.insight_forge.assert_called_once()
        # default query bei fehlendem param ist simulation_requirement
        assert graph_tools.insight_forge.call_args.kwargs["query"] == "Was passiert wenn X?"


class TestRawJsonTools:
    def test_get_graph_statistics_returns_json(self, kwargs, graph_tools):
        graph_tools.get_graph_statistics.return_value = {"nodes": 10, "edges": 20}
        result = execute_tool(
            tool_name="get_graph_statistics",
            parameters={},
            report_context="",
            **kwargs,
        )
        assert '"nodes": 10' in result
        assert '"edges": 20' in result

    def test_get_entity_summary(self, kwargs, graph_tools):
        graph_tools.get_entity_summary.return_value = {"name": "X", "summary": "..."}
        result = execute_tool(
            tool_name="get_entity_summary",
            parameters={"entity_name": "X"},
            report_context="",
            **kwargs,
        )
        assert '"name": "X"' in result

    def test_get_entities_by_type(self, kwargs, graph_tools):
        node_a = MagicMock()
        node_a.to_dict.return_value = {"name": "A"}
        graph_tools.get_entities_by_type.return_value = [node_a]
        result = execute_tool(
            tool_name="get_entities_by_type",
            parameters={"entity_type": "Person"},
            report_context="",
            **kwargs,
        )
        assert '"name": "A"' in result


class TestUnknownTool:
    def test_unknown_returns_friendly_error(self, kwargs):
        result = execute_tool(
            tool_name="some_unknown_tool",
            parameters={},
            report_context="",
            **kwargs,
        )
        assert "Unknown tool" in result
        assert "some_unknown_tool" in result
        assert "search_simulation_actions" in result


class TestExceptionSwallowed:
    def test_graph_tools_error_returns_error_string(self, kwargs, graph_tools):
        graph_tools.quick_search.side_effect = RuntimeError("boom")
        result = execute_tool(
            tool_name="quick_search",
            parameters={"query": "q"},
            report_context="",
            **kwargs,
        )
        assert result.startswith("Tool execution failed")
        assert "boom" in result


class TestEvidenceCallback:
    def test_callback_invoked_after_successful_execution(self, kwargs, graph_tools):
        graph_tools.quick_search.return_value = _structured("rendered")
        recorded = []

        def cb(name, params, structured, rendered, section):
            recorded.append((name, params, structured, rendered, section))

        execute_tool(
            tool_name="quick_search",
            parameters={"query": "q"},
            report_context="",
            record_evidence=cb,
            section_index=7,
            **kwargs,
        )
        assert len(recorded) == 1
        name, params, _structured_arg, rendered, section = recorded[0]
        assert name == "quick_search"
        assert params == {"query": "q"}
        assert rendered == "rendered"
        assert section == 7

    def test_callback_not_invoked_for_raw_json_tools(self, kwargs, graph_tools):
        """Raw-JSON-Tools (get_graph_statistics, …) lösen kein Evidence-Recording aus."""
        graph_tools.get_graph_statistics.return_value = {"x": 1}
        recorded = []
        execute_tool(
            tool_name="get_graph_statistics",
            parameters={},
            report_context="",
            record_evidence=lambda *a, **kw: recorded.append(a),
            **kwargs,
        )
        assert recorded == []

    def test_callback_not_invoked_on_unknown_tool(self, kwargs):
        recorded = []
        execute_tool(
            tool_name="unknown",
            parameters={},
            report_context="",
            record_evidence=lambda *a, **kw: recorded.append(a),
            **kwargs,
        )
        assert recorded == []

    def test_callback_not_invoked_on_exception(self, kwargs, graph_tools):
        graph_tools.quick_search.side_effect = RuntimeError("boom")
        recorded = []
        execute_tool(
            tool_name="quick_search",
            parameters={"query": "q"},
            report_context="",
            record_evidence=lambda *a, **kw: recorded.append(a),
            **kwargs,
        )
        assert recorded == []


class TestReportAgentReExport:
    def test_re_exports_execute_tool(self):
        assert report_agent.execute_tool is tool_execution.execute_tool


def test_contested_statement_reicht_einen_budgetabbruch_durch(monkeypatch):
    """Review PR #1780 (P0): ein Budgetabbruch ist kein „keine Streitfrage"."""
    import pytest

    from app.services import artifact_store, tool_execution
    from app.services.run_budget import BudgetExceededError

    class _Store:
        def read_json(self, *_a, **_k):
            raise BudgetExceededError("calls", 101, 100)

    monkeypatch.setattr(artifact_store, "resolve_default_store", lambda: _Store())

    with pytest.raises(BudgetExceededError):
        tool_execution._contested_statement("sim-1")


def test_contested_statement_ohne_lesbare_config_ist_none(monkeypatch):
    from app.services import artifact_store, tool_execution

    class _Store:
        def read_json(self, *_a, **_k):
            raise PermissionError("simulation_config.json")

    monkeypatch.setattr(artifact_store, "resolve_default_store", lambda: _Store())

    assert tool_execution._contested_statement("sim-1") is None
