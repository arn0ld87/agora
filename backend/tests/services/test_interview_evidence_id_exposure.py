"""Issue #1300 (Review-Finding Codex, P1, PR #1313): die vom Section-Prompt
verlangte ``ev_``-Anker-Form (statt ``seed_doc:``) ist fuer den Modell-Aufrufer
nur einlösbar, wenn die vergebene Evidence-ID auch im beobachteten Tool-Text
steht — sie entsteht erst beim Registrieren, NACH dem urspruenglichen Rendern
des Interview-Transkripts. Ohne diese Kette muss das Modell die ID entweder
kopieren (unmöglich, sie stand nie im Text) oder erfinden — genau das, was
``agent_quote_rejects_seed_doc_anchor`` und der Repair-Pass verhindern sollen.

Deckt zwei Stellen der Kette ab:
1. ``InterviewResult.to_text(evidence_ids=...)`` rendert die IDs sichtbar.
2. ``tool_execution.execute_tool`` reicht die vom Callback zurückgegebene
   Zuordnung durch und rendert den Interview-Text damit ein zweites Mal.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.graph.graph_dtos import AgentInterview, InterviewResult
from app.services.tool_execution import execute_tool


def _interview(agent_name: str = "Agent A") -> AgentInterview:
    return AgentInterview(
        agent_name=agent_name,
        agent_role="Kundin",
        agent_bio="Bio-Text",
        question="Was halten Sie davon?",
        response="Ich finde das Produkt überzeugend.",
        key_quotes=[],
    )


class TestInterviewResultToTextEvidenceIds:
    def test_without_evidence_ids_renders_as_before(self) -> None:
        result = InterviewResult(
            interview_topic="Produktakzeptanz",
            interview_questions=["Was halten Sie davon?"],
            interviews=[_interview()],
        )

        assert "**Evidence ID:**" not in result.to_text()

    def test_with_evidence_ids_prints_the_id_beneath_the_matching_answer(self) -> None:
        result = InterviewResult(
            interview_topic="Produktakzeptanz",
            interview_questions=["Was halten Sie davon?"],
            interviews=[_interview("Agent A"), _interview("Agent B")],
        )

        rendered = result.to_text(evidence_ids={
            0: "ev_" + "a" * 32,
            1: "ev_" + "b" * 32,
        })

        first_block, second_block = rendered.split("#### Interview #2")
        assert "ev_" + "a" * 32 in first_block
        assert "ev_" + "b" * 32 not in first_block
        assert "ev_" + "b" * 32 in second_block

    def test_missing_index_in_the_mapping_renders_no_id_for_that_answer(self) -> None:
        """Nur substanzielle Antworten werden registriert (#1300-Vorarbeit) —
        eine ausgelassene Antwort darf keine erfundene ID zeigen."""
        result = InterviewResult(
            interview_topic="Produktakzeptanz",
            interview_questions=["Was halten Sie davon?"],
            interviews=[_interview("Agent A"), _interview("Agent B")],
        )

        rendered = result.to_text(evidence_ids={1: "ev_" + "b" * 32})

        first_block, second_block = rendered.split("#### Interview #2")
        assert "**Evidence ID:**" not in first_block
        assert "ev_" + "b" * 32 in second_block


class TestExecuteToolThreadsEvidenceIdsIntoTheRenderedText:
    def _kwargs(self, graph_tools):
        return dict(
            graph_tools=graph_tools,
            web_tools=MagicMock(),
            graph_id="g-1",
            simulation_id="sim-1",
            simulation_requirement="Was passiert wenn X?",
        )

    def test_interview_agents_re_renders_with_the_callbacks_evidence_ids(self) -> None:
        structured = InterviewResult(
            interview_topic="Produktakzeptanz",
            interview_questions=["Was halten Sie davon?"],
            interviews=[_interview()],
        )
        graph_tools = MagicMock()
        graph_tools.interview_agents.return_value = structured

        def cb(name, params, result, rendered, section_index):
            assert "**Evidence ID:**" not in rendered, (
                "Der Callback muss den urspruenglich gerenderten Text (ohne "
                "IDs) sehen — er entscheidet erst danach, welche IDs vergeben "
                "wurden."
            )
            return {0: "ev_" + "c" * 32}

        rendered = execute_tool(
            tool_name="interview_agents",
            parameters={"interview_topic": "t"},
            report_context="",
            record_evidence=cb,
            **self._kwargs(graph_tools),
        )

        assert "ev_" + "c" * 32 in rendered

    def test_no_ids_from_the_callback_leaves_the_original_render_untouched(self) -> None:
        """Nicht-Interview-Tools und ein leerer/None-Rueckgabewert loesen kein
        zweites Rendern aus — Stubs ohne ``evidence_ids``-Parameter (wie im
        Rest der Testsuite) duerfen nicht brechen."""
        graph_tools = MagicMock()
        graph_tools.quick_search.return_value = SimpleNamespace(to_text=lambda: "rendered text")

        rendered = execute_tool(
            tool_name="quick_search",
            parameters={"query": "q"},
            report_context="",
            record_evidence=lambda *a, **kw: {0: "ev_" + "d" * 32},
            **self._kwargs(graph_tools),
        )

        assert rendered == "rendered text"

    def test_empty_mapping_from_the_callback_leaves_the_original_render_untouched(self) -> None:
        structured = InterviewResult(
            interview_topic="Produktakzeptanz",
            interview_questions=["Was halten Sie davon?"],
            interviews=[_interview()],
        )
        graph_tools = MagicMock()
        graph_tools.interview_agents.return_value = structured

        rendered = execute_tool(
            tool_name="interview_agents",
            parameters={"interview_topic": "t"},
            report_context="",
            record_evidence=lambda *a, **kw: None,
            **self._kwargs(graph_tools),
        )

        assert "**Evidence ID:**" not in rendered
