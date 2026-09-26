"""#1688 (Security-Review 2026-09-26), Item 2: ``ReportAgent`` must never
offer Tavily-backed web tools (``web_search``) to a workspace-scoped
(JWT/BYOK) run. The operator's ``TAVILY_API_KEY``/``ENABLE_WEB_TOOLS``
config is not something a visitor brought with them; a JWT report run must
see ``web_tools.is_available() is False`` regardless of how the operator's
instance is configured.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.report_agent.agent import ReportAgent


def _build_agent() -> ReportAgent:
    return ReportAgent(
        graph_id="graph-1",
        simulation_id="sim-1",
        simulation_requirement="Test requirement",
        llm_client=MagicMock(),
        graph_tools=MagicMock(),
    )


@patch("app.services.report_agent.agent.WebToolsService")
@patch("app.services.report_agent.agent.workspace_credential_id_for_run")
def test_workspace_scoped_run_gets_no_web_tools(mock_scope, mock_web_tools_cls):
    """RED before the fix: a workspace-scoped run still constructed
    ``WebToolsService()`` with the operator's configured Tavily key/flag."""
    mock_scope.return_value = uuid4()
    mock_web_tools_cls.return_value = MagicMock(is_available=MagicMock(return_value=False))

    _build_agent()

    mock_web_tools_cls.assert_called_once_with(enabled=False)


@patch("app.services.report_agent.agent.WebToolsService")
@patch("app.services.report_agent.agent.workspace_credential_id_for_run")
def test_operator_run_keeps_configured_web_tools(mock_scope, mock_web_tools_cls):
    """Guard for the guard: an operator (non-workspace) run is unaffected —
    ``WebToolsService()`` still decides availability from settings/env."""
    mock_scope.return_value = None
    mock_web_tools_cls.return_value = MagicMock(is_available=MagicMock(return_value=True))

    _build_agent()

    mock_web_tools_cls.assert_called_once_with()


@patch("app.services.report_agent.agent.workspace_credential_id_for_run", return_value=uuid4())
def test_workspace_scoped_run_web_search_tool_not_offered(_mock_scope):
    """End-to-end through ``_define_tools``: with a real (unmocked)
    ``WebToolsService(enabled=False)``, ``web_search`` must not appear in
    the agent's tool list even if TAVILY_API_KEY is configured operator-side."""
    with patch(
        "app.services.web_tools._setting_value",
        side_effect=lambda key, include_secret=False: (
            "operator-tavily-key" if key == "TAVILY_API_KEY" else True
        ),
    ):
        agent = _build_agent()

    assert agent.web_tools.is_available() is False
    assert "web_search" not in agent.tools
