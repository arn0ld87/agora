"""Issue #1778 — die Beitragssuche läuft je Abschnitt einmal durch das System.

Im Abnahmelauf ``report_89d20c11edc1`` rief der Report-Agent
``search_simulation_actions`` in zwei von sieben Abschnitten auf. Ein Abschnitt
ohne Suche schreibt allein aus Interviews, und kein Claim kann sich dann auf
einen Simulationsbeitrag stützen.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from app.services.report_agent.workflow import generate_section_react
from app.services.report_prompts import (
    REACT_PREFETCH_EMPTY_NOTE,
    REACT_PREFETCHED_POSTS_TEMPLATE,
)

POSTS = (
    'Simulation posts for "Stakeholder-Positionen": showing 1 of 1 matching posts '
    "(1 posts with text in the simulation).\n"
    "1. [Evidence ID: `ev_a`] Landfrauenverband CREATE_POST on reddit in round 3: "
    "Familien ohne Auto erreichen den Kreißsaal nur schwer."
)
NO_POSTS = (
    'Simulation posts for "Stakeholder-Positionen": no matching posts or comments '
    "(0 posts with text in the simulation)."
)
FINAL = "Final Answer: Familien ohne Auto erreichen den Kreißsaal nur schwer."


def _final_turn() -> Dict[str, Any]:
    return {"content": FINAL, "tool_calls": [], "finish_reason": "stop", "raw_response": None}


def _tool_turn(name: str, query: str) -> Dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [{"id": query, "name": name, "arguments": {"query": query}}],
        "finish_reason": "tool_calls",
        "raw_response": None,
    }


def _make_agent(*, tools: Any, post_result: str = POSTS) -> MagicMock:
    agent = MagicMock()
    agent.SECTION_SYSTEM_PROMPT_TEMPLATE = (
        "System {report_title} {report_summary} {simulation_requirement} "
        "{section_title} {tools_description} {language}"
    )
    agent.SECTION_USER_PROMPT_TEMPLATE = "User {previous_content} {section_title}"
    agent.REACT_INSUFFICIENT_TOOLS_MSG = "Coverage gap {tool_calls_count} {unused_hint}"
    agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT = "Coverage gap alt {tool_calls_count} {unused_hint}"
    agent.REACT_TOOL_LIMIT_MSG = "Limit {tool_calls_count} {max_tool_calls}"
    agent.REACT_UNUSED_TOOLS_HINT = "Unused {unused_list}"
    agent.REACT_OBSERVATION_TEMPLATE = (
        "Obs {tool_name} {result} {tool_calls_count}/{max_tool_calls} {used_tools_str} {unused_hint}"
    )
    agent.REACT_FORCE_FINAL_MSG = "Force final"
    agent.REACT_PREFETCHED_POSTS_TEMPLATE = REACT_PREFETCHED_POSTS_TEMPLATE
    agent.REACT_PREFETCH_EMPTY_NOTE = REACT_PREFETCH_EMPTY_NOTE
    agent.MAX_TOOL_CALLS_PER_SECTION = 5
    agent.report_logger = None
    agent.simulation_requirement = "Schließung Kreißsaal"
    agent.tools = tools
    agent.evidence_map = {
        "evidence_index": {
            "ev_a": {
                "evidence_id": "ev_a",
                "type": "agent_action",
                "snippet": "Familien ohne Auto erreichen den Kreißsaal nur schwer.",
            }
        },
        "global_evidence_refs": ["ev_a"],
    }
    agent._get_tools_description.return_value = "Tools"
    agent._get_openai_tools_schema.return_value = []
    agent._parse_tool_calls.return_value = []

    def _execute_tool(name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        return post_result if name == "search_simulation_actions" else "Treffer"

    agent._execute_tool.side_effect = _execute_tool
    return agent


def _run(agent: MagicMock, turns: List[Dict[str, Any]]) -> str:
    agent.llm.chat_with_tools.side_effect = turns
    section = MagicMock()
    section.title = "Stakeholder-Positionen"
    section.description = "Wer steht wo"
    outline = MagicMock()
    outline.title = "Bericht"
    outline.summary = "Zusammenfassung"
    with patch("app.services.report_agent.workflow.Config") as cfg:
        cfg.REPORT_TOOLCALL_MODE = "native"
        cfg.REPORT_LANGUAGE = "German"
        return generate_section_react(
            agent=agent, section=section, outline=outline, previous_sections=[], section_index=2,
        )


def _first_user_prompt(agent: MagicMock) -> str:
    messages = agent.llm.chat_with_tools.call_args_list[0].kwargs["messages"]
    return next(m["content"] for m in messages if m["role"] == "user")


def test_post_search_runs_before_the_first_model_turn() -> None:
    agent = _make_agent(tools={"search_simulation_actions": {}})

    _run(agent, [_final_turn()])

    name, parameters = agent._execute_tool.call_args_list[0].args[:2]
    assert name == "search_simulation_actions"
    assert parameters["query"] == "Stakeholder-Positionen Wer steht wo"
    prompt = _first_user_prompt(agent)
    assert "[Evidence ID: `ev_a`]" in prompt
    assert "plain statements" in prompt


def test_prefetch_counts_against_the_tool_limit() -> None:
    """Das Limit bleibt fünf: nach der Vorab-Suche sind noch vier Aufrufe frei."""
    agent = _make_agent(tools={"search_simulation_actions": {}})
    turns = [_tool_turn("panorama_search", f"q{i}") for i in range(4)] + [_final_turn()]

    _run(agent, turns)

    assert "used so far: 1/5" in _first_user_prompt(agent)
    last_messages = agent.llm.chat_with_tools.call_args_list[-1].kwargs["messages"]
    observations = [m["content"] for m in last_messages if m["content"].startswith("Obs ")]
    assert " 5/5 " in observations[-1]
    assert "search_simulation_actions" in observations[-1].split("5/5")[1]


def test_searches_without_posts_show_no_block_but_count_against_the_limit() -> None:
    """Review PR #1785: jede ausgeführte Suche zählt, auch eine ohne Treffer."""
    agent = _make_agent(tools={"search_simulation_actions": {}}, post_result=NO_POSTS)

    _run(agent, [_tool_turn("panorama_search", "q0"), _final_turn()])

    assert "search_simulation_actions Returned" not in _first_user_prompt(agent)
    # Der Agent erfährt das verbrauchte Budget auch ohne Treffer.
    assert "Tool calls used so far: 2/5" in _first_user_prompt(agent)
    # Abschnittssuche und Rückfall auf die Fragestellung: zwei Aufrufe.
    assert agent._execute_tool.call_count == 3
    last_messages = agent.llm.chat_with_tools.call_args_list[-1].kwargs["messages"]
    observation = next(m["content"] for m in last_messages if m["content"].startswith("Obs "))
    assert " 3/5 " in observation


def test_tool_failure_is_not_presented_as_posts() -> None:
    agent = _make_agent(
        tools={"search_simulation_actions": {}},
        post_result="Tool execution failed: simulation not found",
    )

    _run(agent, [_final_turn()])

    assert "Tool execution failed" not in _first_user_prompt(agent)


def test_agent_without_the_tool_is_not_prefetched() -> None:
    agent = _make_agent(tools={"quick_search": {}})

    _run(agent, [_final_turn()])

    assert agent._execute_tool.call_count == 0


def test_requirement_is_only_the_fallback_query() -> None:
    """Review PR #1785: Die Fragestellung steht in fast jedem Beitrag.

    Als Teil der Anfrage füllte sie die Trefferliste mit beliebigen Beiträgen.
    Sie wird erst gesucht, wenn die Wörter des Abschnitts nichts finden.
    """
    agent = _make_agent(tools={"search_simulation_actions": {}})

    def _execute_tool(name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        return POSTS if parameters["query"] == "Schließung Kreißsaal" else NO_POSTS

    agent._execute_tool.side_effect = _execute_tool

    _run(agent, [_final_turn()])

    queries = [call.args[1]["query"] for call in agent._execute_tool.call_args_list]
    assert queries == ["Stakeholder-Positionen Wer steht wo", "Schließung Kreißsaal"]
    # Beide ausgeführten Suchen zählen gegen das Limit von fünf.
    assert "used so far: 2/5" in _first_user_prompt(agent)


def test_fallback_search_leaves_three_calls_for_the_model() -> None:
    """Mit zwei Vorab-Suchen führt der Abschnitt höchstens fünf Werkzeuge aus."""
    agent = _make_agent(tools={"search_simulation_actions": {}})

    def _execute_tool(name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        if name != "search_simulation_actions":
            return "Treffer"
        return POSTS if parameters["query"] == "Schließung Kreißsaal" else NO_POSTS

    agent._execute_tool.side_effect = _execute_tool
    turns = [_tool_turn("panorama_search", f"q{i}") for i in range(6)] + [_final_turn()]

    _run(agent, turns)

    assert agent._execute_tool.call_count == 5
