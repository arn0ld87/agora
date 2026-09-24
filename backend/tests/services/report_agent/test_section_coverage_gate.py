"""Issue #1294: Evidence-Deckung statt Tool-Call-Anzahl im Section-ReACT-Loop.

Matrix 0/1/mehr Tool-Calls × ausreichende/unzureichende Deckung auf dem
produktiven Pfad ``generate_section_react``, plus der Forced-Final-Fall: ein
gültiger, nur mangels Deckung zurückgewiesener Entwurf darf durch die
erzwungene Endgenerierung nicht verschlechtert werden.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from app.services.report_agent.run_degradation import events_for
from app.services.report_agent.section_coverage import (
    draft_claim_units,
    section_has_sufficient_evidence,
)
from app.services.report_agent.workflow import generate_section_react

DRAFT = (
    "Die Lehrkräfte in Sachsen lehnen das neue Pflichtfach mehrheitlich ab. "
    "Die Elternverbände unterstützen die geplante Einführung ausdrücklich."
)
FINAL = f"Final Answer: {DRAFT}"

COVERING_SNIPPETS = [
    "Lehrkräfte in Sachsen lehnen das Pflichtfach ab, heißt es in der Umfrage.",
    "Elternverbände unterstützen die geplante Einführung.",
]
UNRELATED_SNIPPETS = ["Regenwetter am Wochenende in Hamburg erwartet."]


def _evidence_map(snippets: List[str]) -> Dict[str, Any]:
    index = {
        f"ev-g{i}": {"evidence_id": f"ev-g{i}", "type": "agent_action", "snippet": text}
        for i, text in enumerate(snippets)
    }
    return {"evidence_index": index, "global_evidence_refs": list(index)}


def _tool_turn(call_id: str) -> Dict[str, Any]:
    return {
        "content": "",
        "tool_calls": [{"id": call_id, "name": "panorama_search", "arguments": {"query": call_id}}],
        "finish_reason": "tool_calls",
        "raw_response": None,
    }


def _final_turn(content: Optional[str] = FINAL) -> Dict[str, Any]:
    return {"content": content, "tool_calls": [], "finish_reason": "stop", "raw_response": None}


def _make_agent(*, preloaded: List[str], tool_registers_evidence: bool) -> MagicMock:
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
        "Obs {tool_name} {result} {tool_calls_count} {max_tool_calls} {used_tools_str} {unused_hint}"
    )
    agent.REACT_FORCE_FINAL_MSG = "Force final"
    agent.MAX_TOOL_CALLS_PER_SECTION = 5
    agent.report_logger = None
    agent.simulation_requirement = "Pflichtfach-Einführung"
    agent.evidence_map = _evidence_map(preloaded)
    agent._get_tools_description.return_value = "Tools"
    agent._get_openai_tools_schema.return_value = []
    agent._parse_tool_calls.return_value = []

    def _execute_tool(name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        if tool_registers_evidence:
            agent._active_section_evidence.append(
                {"evidence_id": f"ev-{parameters.get('query')}", "type": "graph_fact", "snippet": "Treffer"}
            )
            return "Treffer"
        return "(keine Ergebnisse)"

    agent._execute_tool.side_effect = _execute_tool
    return agent


def _run(agent: MagicMock, turns: List[Dict[str, Any]], mode: str = "native") -> str:
    agent.llm.chat_with_tools.side_effect = turns
    section = MagicMock()
    section.title = "Stakeholder-Positionen"
    outline = MagicMock()
    outline.title = "Bericht"
    outline.summary = "Zusammenfassung"
    with patch("app.services.report_agent.workflow.Config") as cfg:
        cfg.REPORT_TOOLCALL_MODE = mode
        cfg.REPORT_LANGUAGE = "German"
        return generate_section_react(
            agent=agent, section=section, outline=outline, previous_sections=[], section_index=2,
        )


def _user_messages(agent: MagicMock) -> List[str]:
    last_messages = agent.llm.chat_with_tools.call_args_list[-1].kwargs["messages"]
    return [m["content"] for m in last_messages if m["role"] == "user"]


def _gap_prompts(agent: MagicMock) -> int:
    return sum("Coverage gap" in content for content in _user_messages(agent))


# ---------------------------------------------------------------------------
# section_has_sufficient_evidence — die Entscheidung selbst
# ---------------------------------------------------------------------------


def test_section_retrieval_evidence_is_sufficient() -> None:
    assert section_has_sufficient_evidence(
        DRAFT,
        section_evidence=[{"evidence_id": "ev-1", "type": "graph_fact"}],
        evidence_map=None,
    )


def test_model_output_in_section_pool_does_not_count_as_evidence() -> None:
    assert not section_has_sufficient_evidence(
        DRAFT,
        section_evidence=[{"evidence_id": "ev-1", "type": "section_synthesis"}],
        evidence_map=_evidence_map(UNRELATED_SNIPPETS),
    )


def test_preloaded_evidence_covering_every_statement_is_sufficient() -> None:
    assert section_has_sufficient_evidence(
        DRAFT, section_evidence=[], evidence_map=_evidence_map(COVERING_SNIPPETS),
    )


def test_one_uncovered_statement_is_a_coverage_gap() -> None:
    assert not section_has_sufficient_evidence(
        DRAFT, section_evidence=[], evidence_map=_evidence_map(COVERING_SNIPPETS[:1]),
    )


def test_without_any_evidence_the_draft_is_not_covered() -> None:
    assert not section_has_sufficient_evidence(DRAFT, section_evidence=[], evidence_map=None)


def test_draft_without_checkable_statement_is_not_covered() -> None:
    discourse = "Im Folgenden werden die Reaktionsmuster dargestellt."
    assert draft_claim_units(discourse) == []
    assert not section_has_sufficient_evidence(
        discourse, section_evidence=[], evidence_map=_evidence_map(COVERING_SNIPPETS),
    )


def test_discourse_only_draft_is_a_gap_even_with_section_evidence() -> None:
    """PR #1563 (Codex P2): der Fast-Path über registrierte Abschnitts-Evidence
    ließ einen Entwurf ohne jede prüfbare Aussage durch."""
    discourse = "Im Folgenden werden die Reaktionsmuster der Stakeholder ausführlich dargestellt."
    assert not section_has_sufficient_evidence(
        discourse,
        section_evidence=[{"evidence_id": "ev-1", "type": "graph_fact"}],
        evidence_map=None,
    )


def test_compound_claim_is_checked_per_binder_unit() -> None:
    """PR #1563 (Codex P2): ``während`` hielt beide Teilaussagen in einer
    Einheit; die gedeckte Hälfte trug die ungedeckte mit. Der Binder spaltet
    per ``split_claim_chunks`` — das Gate muss dieselben Einheiten prüfen."""
    compound = (
        "Die Lehrkräfte in Sachsen lehnen das Pflichtfach ab, während die "
        "Elternverbände die geplante Einführung ausdrücklich unterstützen."
    )
    assert len(draft_claim_units(compound)) == 2
    assert not section_has_sufficient_evidence(
        compound, section_evidence=[], evidence_map=_evidence_map(COVERING_SNIPPETS[:1]),
    )


def test_matching_number_without_topic_overlap_is_a_gap() -> None:
    """PR #1563 (Codex P2): ``classify_claim_gap`` schließt über gleiche Zahlen
    kurz — für das Gate ist "90 Prozent Regenwahrscheinlichkeit" kein Beleg
    für "90 Prozent der Lehrkräfte"."""
    numeric = "90 Prozent der Lehrkräfte in Sachsen lehnen das Pflichtfach ab."
    assert not section_has_sufficient_evidence(
        numeric,
        section_evidence=[],
        evidence_map=_evidence_map(["90 Prozent Regenwahrscheinlichkeit am Wochenende."]),
    )


# ---------------------------------------------------------------------------
# Matrix auf dem produktiven Loop
# ---------------------------------------------------------------------------


def test_zero_tool_calls_with_sufficient_coverage_is_accepted() -> None:
    agent = _make_agent(preloaded=COVERING_SNIPPETS, tool_registers_evidence=True)

    result = _run(agent, [_final_turn()])

    assert "Lehrkräfte in Sachsen" in result
    assert agent._execute_tool.call_count == 0
    assert agent.llm.chat_with_tools.call_count == 1
    assert 2 not in events_for(agent).forced_final_sections


def test_zero_tool_calls_with_coverage_gap_requests_retrieval() -> None:
    agent = _make_agent(preloaded=UNRELATED_SNIPPETS, tool_registers_evidence=True)

    result = _run(agent, [_final_turn(), _tool_turn("q1"), _final_turn()])

    assert "Lehrkräfte in Sachsen" in result
    assert agent._execute_tool.call_count == 1
    assert _gap_prompts(agent) == 1


def test_one_tool_call_with_registered_evidence_is_accepted() -> None:
    agent = _make_agent(preloaded=[], tool_registers_evidence=True)

    result = _run(agent, [_tool_turn("q1"), _final_turn()])

    assert "Lehrkräfte in Sachsen" in result
    assert agent._execute_tool.call_count == 1
    assert _gap_prompts(agent) == 0


def test_one_tool_call_without_evidence_is_a_coverage_gap() -> None:
    """Vorher genügte ein ergebnisloser Aufruf dem Gate (min_tool_calls=1)."""
    agent = _make_agent(preloaded=UNRELATED_SNIPPETS, tool_registers_evidence=False)

    def _evidence_on_second_call(name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        if agent._execute_tool.call_count >= 2:
            agent._active_section_evidence.append({"evidence_id": "ev-q2", "type": "graph_fact"})
        return "Treffer"

    agent._execute_tool.side_effect = _evidence_on_second_call

    result = _run(agent, [_tool_turn("q1"), _final_turn(), _tool_turn("q2"), _final_turn()])

    assert "Lehrkräfte in Sachsen" in result
    assert agent._execute_tool.call_count == 2
    assert _gap_prompts(agent) == 1
    assert 2 not in events_for(agent).forced_final_sections


def test_several_tool_calls_with_registered_evidence_are_accepted() -> None:
    agent = _make_agent(preloaded=[], tool_registers_evidence=True)

    result = _run(agent, [_tool_turn("q1"), _tool_turn("q2"), _tool_turn("q3"), _final_turn()])

    assert "Lehrkräfte in Sachsen" in result
    assert agent._execute_tool.call_count == 3
    assert _gap_prompts(agent) == 0


def test_several_tool_calls_without_evidence_keep_the_gap_visible() -> None:
    agent = _make_agent(preloaded=UNRELATED_SNIPPETS, tool_registers_evidence=False)

    result = _run(
        agent,
        [_tool_turn("q1"), _tool_turn("q2"), _final_turn(), _tool_turn("q3"), _final_turn()],
    )

    # Der Abschnitt endet über den Erschöpfungspfad — sichtbar als forced_final.
    assert 2 in events_for(agent).forced_final_sections
    assert "Lehrkräfte in Sachsen" in result
    assert _gap_prompts(agent) == 2


def test_output_without_final_answer_prefix_uses_the_same_gate() -> None:
    agent = _make_agent(preloaded=UNRELATED_SNIPPETS, tool_registers_evidence=True)

    result = _run(agent, [_final_turn(DRAFT), _tool_turn("q1"), _final_turn(DRAFT)])

    assert "Lehrkräfte in Sachsen" in result
    assert "Coverage gap alt" in "\n".join(_user_messages(agent))


# ---------------------------------------------------------------------------
# Forced-Final
# ---------------------------------------------------------------------------


def test_forced_final_keeps_a_valid_draft_instead_of_an_empty_regeneration() -> None:
    """Vorher verwarf Forced-Final den Entwurf; eine leere Endantwort machte
    aus einem brauchbaren Abschnitt den Fehlertext."""
    agent = _make_agent(preloaded=UNRELATED_SNIPPETS, tool_registers_evidence=False)
    turns = [_final_turn(), _tool_turn("q1"), _final_turn(), _tool_turn("q2"), _final_turn()]
    # Eine sechste Antwort (die erzwungene Endgenerierung) wäre leer.
    turns.append(_final_turn(None))

    result = _run(agent, turns)

    assert "Lehrkräfte in Sachsen" in result
    assert "konnte nicht generiert werden" not in result
    assert agent.llm.chat_with_tools.call_count == 5
    assert "Force final" not in _user_messages(agent)
    assert 2 in events_for(agent).forced_final_sections


def test_forced_final_without_valid_draft_still_regenerates() -> None:
    agent = _make_agent(preloaded=UNRELATED_SNIPPETS, tool_registers_evidence=False)
    turns = [_tool_turn(f"q{i}") for i in range(5)] + [_final_turn()]

    result = _run(agent, turns)

    assert "Lehrkräfte in Sachsen" in result
    assert agent.llm.chat_with_tools.call_count == 6
    assert "Force final" in _user_messages(agent)
    assert 2 in events_for(agent).forced_final_sections
