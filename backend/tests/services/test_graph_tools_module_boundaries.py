"""Architecture regression tests for the graph-tools interview helper split."""

from unittest.mock import MagicMock


def test_graph_tools_interview_helpers_are_extracted_and_wrapped(monkeypatch):
    from app.services.graph import interview_helpers
    from app.services.graph_tools import GraphToolsService

    monkeypatch.setattr(
        interview_helpers,
        "clean_tool_call_response",
        lambda response: f"delegated:{response}",
    )
    assert GraphToolsService._clean_tool_call_response("payload") == "delegated:payload"

    service = GraphToolsService.__new__(GraphToolsService)
    service._llm_client = MagicMock(name="llm")
    captured = {}

    def fake_select(**kwargs):
        captured.update(kwargs)
        return ["agent"], [0], "reason"

    monkeypatch.setattr(interview_helpers, "select_agents_for_interview", fake_select)
    result = service._select_agents_for_interview(
        profiles=[{"realname": "A"}],
        interview_requirement="topic",
        simulation_requirement="background",
        max_agents=1,
        panel_tracker=None,
    )

    assert result == (["agent"], [0], "reason")
    assert captured["llm"] is service._llm_client
    assert captured["max_agents"] == 1
