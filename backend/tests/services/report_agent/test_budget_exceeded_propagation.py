"""Issue #978: BudgetExceededError darf im Report-Pfad niemals stillschweigend
verschluckt werden.

Root-Cause-Befund (verifiziert am Code, NICHT die im Issue genannte Hypothese
zur run_id-Bindung — die ist bereits korrekt verdrahtet, siehe
``ReportGenerationService.start_generation`` → ``LLMClient.from_route(...,
run_id=run_record["run_id"])`` → ``ReportAgent(llm_client=shared_llm_client)``):

Mehrere Stellen im Report-Agent-Aufrufpfad fangen ``except Exception`` breit
ab und liefern einen Fallback-Wert, OHNE ``BudgetExceededError`` vorher
durchzureichen — anders als das bereits korrekt implementierte Muster in
``workflow._safe_generate_section_react`` und ``workflow.generate_report``'s
äußerem Handler (beide prüfen ``isinstance(exc, BudgetExceededError)`` und
reraisen explizit).

Betroffene Stellen (vor dem Fix):
  1. ``report_agent.planning.plan_outline`` (Zeile ~151)
  2. ``report_agent.workflow.generate_section_metadata`` (Zeile ~748)
  3. ``tool_execution.execute_tool`` (Zeile ~217)
  4. ``graph.insight_forge_tool.generate_sub_queries`` (Zeile ~103)
  5. ``graph_tools.GraphToolsService._select_agents_for_interview`` (Zeile ~539)
  6. ``graph_tools.GraphToolsService._generate_interview_questions`` (Zeile ~587)
  7. ``graph_tools.GraphToolsService._generate_interview_summary`` (Zeile ~643)

Je nachdem, welcher physische LLM-Call im ReACT-Loop das Budget genau
überschreitet (abhängig von Tool-Rotation und Section-Anzahl), landet der
Abbruch in einer dieser Stellen und wird zu einem harmlosen Fallback-Text
degradiert statt den Run mit ``status=stopped`` / ``termination_reason=
budget_calls`` zu beenden — exakt das im Issue beschriebene Symptom.

Diese Tests isolieren jede Stelle einzeln: ein Fake-LLM/Fake-Tool wirft
``BudgetExceededError`` direkt, und der Test erwartet, dass die Funktion sie
unverändert durchreicht statt sie abzufangen.
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.services.graph.insight_forge_tool import generate_sub_queries
from app.services.graph_tools import GraphToolsService
from app.services.report_agent.planning import plan_outline
from app.services.report_agent.workflow import generate_section_metadata
from app.services.run_budget import BudgetExceededError
from app.services.tool_execution import execute_tool


def _budget_error() -> BudgetExceededError:
    return BudgetExceededError("calls", observed=2, threshold=2)


class _RaisingLLM:
    """Fake-LLMClient, dessen chat/chat_json-Methoden BudgetExceededError werfen."""

    def chat_json(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise _budget_error()

    def chat(self, *args: Any, **kwargs: Any) -> str:
        raise _budget_error()

    def chat_with_tools(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise _budget_error()


# ---------------------------------------------------------------------------
# 1. plan_outline
# ---------------------------------------------------------------------------


def test_plan_outline_propagates_budget_exceeded():
    """RED: plan_outline() darf BudgetExceededError nicht in ein Fallback-Outline
    umwandeln — der Run muss mit dem Abbruch terminieren, nicht mit einem
    generischen 3-Section-Default weiterlaufen."""
    agent = MagicMock()
    agent.llm = _RaisingLLM()
    agent.graph_tools.get_simulation_context.return_value = {
        "graph_statistics": {"total_nodes": 0, "total_edges": 0, "entity_types": {}},
        "total_entities": 0,
        "related_facts": [],
    }
    agent.simulation_requirement = "Test requirement"

    with pytest.raises(BudgetExceededError):
        plan_outline(agent)


# ---------------------------------------------------------------------------
# 2. generate_section_metadata
# ---------------------------------------------------------------------------


def test_generate_section_metadata_propagates_budget_exceeded():
    """RED: generate_section_metadata() darf BudgetExceededError nicht in ein
    leeres dict umwandeln — sonst läuft die Section-Schleife nach einem
    Budget-Abbruch klaglos weiter."""
    agent = MagicMock()
    agent.llm = _RaisingLLM()

    with pytest.raises(BudgetExceededError):
        generate_section_metadata(
            agent,
            section_title="Executive Summary",
            section_content="Some content",
            section_index=1,
        )


# ---------------------------------------------------------------------------
# 3. execute_tool
# ---------------------------------------------------------------------------


def test_execute_tool_propagates_budget_exceeded():
    """RED: execute_tool() darf BudgetExceededError aus graph_tools.insight_forge
    nicht in einen "Tool execution failed"-Text umwandeln — der ReACT-Loop
    würde sonst mit einer harmlosen Observation weiterlaufen."""
    graph_tools = MagicMock()
    graph_tools.insight_forge.side_effect = _budget_error()

    with pytest.raises(BudgetExceededError):
        execute_tool(
            tool_name="insight_forge",
            parameters={"query": "test"},
            report_context="ctx",
            graph_tools=graph_tools,
            web_tools=MagicMock(),
            graph_id="graph-1",
            simulation_id="sim-1",
            simulation_requirement="Test requirement",
        )


# ---------------------------------------------------------------------------
# 4. generate_sub_queries (insight_forge_tool)
# ---------------------------------------------------------------------------


def test_generate_sub_queries_propagates_budget_exceeded():
    """RED: generate_sub_queries() darf BudgetExceededError nicht in
    Default-Sub-Fragen umwandeln — insight_forge würde sonst ohne Fehler
    weiterlaufen, obwohl das harte Limit bereits erreicht ist."""
    with pytest.raises(BudgetExceededError):
        generate_sub_queries(
            query="test query",
            simulation_requirement="Test requirement",
            llm=_RaisingLLM(),
        )


# ---------------------------------------------------------------------------
# 5-7. GraphToolsService interview helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def graph_tools_with_raising_llm() -> GraphToolsService:
    tools = GraphToolsService(storage=MagicMock(), llm_client=_RaisingLLM())
    return tools


def test_select_agents_for_interview_propagates_budget_exceeded(
    graph_tools_with_raising_llm: GraphToolsService,
):
    """RED: _select_agents_for_interview() darf BudgetExceededError nicht in
    eine Default-Selektion umwandeln."""
    profiles: List[Dict[str, Any]] = [{"realname": "A", "profession": "tester"}]

    with pytest.raises(BudgetExceededError):
        graph_tools_with_raising_llm._select_agents_for_interview(
            profiles=profiles,
            interview_requirement="req",
            simulation_requirement="sim req",
            max_agents=3,
        )


def test_generate_interview_questions_propagates_budget_exceeded(
    graph_tools_with_raising_llm: GraphToolsService,
):
    """RED: _generate_interview_questions() darf BudgetExceededError nicht in
    Default-Fragen umwandeln."""
    with pytest.raises(BudgetExceededError):
        graph_tools_with_raising_llm._generate_interview_questions(
            interview_requirement="req",
            simulation_requirement="sim req",
            selected_agents=[{"profession": "tester"}],
        )


def test_generate_interview_summary_propagates_budget_exceeded(
    graph_tools_with_raising_llm: GraphToolsService,
):
    """RED: _generate_interview_summary() darf BudgetExceededError nicht in
    einen Default-Summary-Text umwandeln."""
    interview = MagicMock()
    interview.agent_name = "Agent A"
    interview.agent_role = "tester"
    interview.response = "response text"

    with pytest.raises(BudgetExceededError):
        graph_tools_with_raising_llm._generate_interview_summary(
            interviews=[interview],
            interview_requirement="req",
        )


# ---------------------------------------------------------------------------
# 8. _run_red_team_review (workflow)
#
# Achte Stelle, bei der Vollstaendigkeitspruefung des Fixes gefunden: ein
# `except Exception` um `agent.llm.chat_json(...)`, das den Abbruch zu
# `findings = []` degradiert. Der Red-Team-Schritt laeuft dann klaglos durch
# und der Run endet auf `completed` statt `stopped`.
# ---------------------------------------------------------------------------


def test_run_red_team_review_propagates_budget_exceeded():
    """RED: _run_red_team_review() darf BudgetExceededError nicht in leere
    findings umwandeln.

    Ein Lauf ist Voraussetzung — wo das Gate den LLM-Call unterbindet, kann
    die Funktion den Fehler nie sehen.
    """
    from app.services.report_agent.workflow import _run_red_team_review
    from app.services.report_intent import ReportIntent

    agent = MagicMock()
    agent.llm = _RaisingLLM()

    report_v3 = MagicMock()
    report_v3.claims = []
    report_v3.hypotheses = []

    with pytest.raises(BudgetExceededError):
        _run_red_team_review(
            agent, report_v3, echo_index=0.9, intent=ReportIntent.OPINION
        )


# ---------------------------------------------------------------------------
# 9. generate_report — AUFRUFER-Ebene
#
# Die acht Tests oben pruefen jede Stelle isoliert. Sie koennen strukturell
# nicht sehen, ob ein dazwischenliegender Handler den frisch reraisten Fehler
# erneut verschluckt. Genau das war der Fall: der `except Exception` in
# generate_report, der den _run_red_team_review-Aufruf umschliesst, fing den
# Abbruch wieder ab, die naechste Zeile setzte "completed", und
# report_generation.py::except BudgetExceededError -> mark_budget_abort wurde
# nie erreicht — der Fix an Stelle 3 war damit wirkungslos.
#
# Dieser Test prueft deshalb die Aufrufer-Ebene: der Abbruch muss
# generate_report VERLASSEN.
# ---------------------------------------------------------------------------


def test_generate_report_propagates_budget_exceeded_from_red_team(tmp_path):
    """RED: Ein Budgetabbruch im Red-Team-Schritt muss generate_report verlassen.

    Alle LLM-nutzenden Schritte davor sind gepatcht; der einzige Aufruf, der
    `agent.llm` tatsaechlich erreicht, ist der Red-Team-Call. Faengt der
    umschliessende Handler den Fehler ab, kehrt generate_report normal zurueck
    und der Run wuerde auf `completed` laufen statt auf `stopped`.
    """
    import os

    from app.models.report import ReportOutline, ReportSection
    from app.services.report_agent.workflow import generate_report

    report_id = "report_budget_red_team_01"

    agent = MagicMock()
    agent.llm = _RaisingLLM()
    agent.report_logger = MagicMock()
    agent.console_logger = MagicMock()
    agent.simulation_id = "sim_test"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Test requirement"
    agent.persona_ids = ["p1"]
    agent._collect_simulation_evidence_items = MagicMock(return_value=[])

    outline = ReportOutline(
        title="Test Report",
        summary="Test summary",
        sections=[ReportSection(title="Section 1", content="", description="")],
    )

    report_folder = str(tmp_path / report_id)
    os.makedirs(report_folder, exist_ok=True)

    with (
        patch("app.services.report_agent.workflow.generate_section_react", return_value="Content"),
        patch("app.services.report_agent.workflow.generate_section_metadata", return_value={}),
        patch("app.services.report_agent.workflow.ReportManager") as mock_rm,
        patch("app.services.report_agent.workflow.plan_outline_impl", return_value=outline),
        patch("app.services.report_agent.workflow.validate_required_sections", return_value=[]),
        patch("app.services.report_agent.workflow._load_persona_count", return_value=100),
        patch("app.services.report_agent.workflow.MIN_PERSONA_TABLE_ROWS", 0),
        patch(
            "app.services.report_agent.workflow.validate_quote_anchors",
            return_value=MagicMock(valid=True),
        ),
        patch("app.services.report_agent.workflow.migrate_v1_to_v2", return_value=None),
        patch("app.services.report_agent.workflow._get_echo_index", return_value=0.9),
        patch("app.services.report_agent.workflow.ReportV3") as mock_v3,
        patch("app.services.report_agent.workflow.EvidenceMapModel") as mock_em,
    ):
        mock_rm._ensure_report_folder.return_value = report_folder
        mock_rm.get_evidence_map.return_value = None
        mock_rm.get_report.return_value = None
        mock_rm.get_generated_sections.return_value = []
        mock_rm.assemble_full_report.return_value = "## Section 1\n"
        mock_rm._write_json_atomic.side_effect = lambda path, data: None
        mock_rm.get_report_v3.return_value = {"schema_version": 3}

        report_v3_obj = MagicMock()
        report_v3_obj.claims = []
        report_v3_obj.hypotheses = []
        mock_v3.model_validate.return_value = report_v3_obj

        mock_em.model_validate.return_value = MagicMock(
            model_dump=MagicMock(
                return_value={
                    "schema_version": 2,
                    "report_id": report_id,
                    "simulation_id": "sim_test",
                    "global_evidence": [],
                    "sections": [],
                }
            )
        )

        with pytest.raises(BudgetExceededError):
            generate_report(agent, progress_callback=None, report_id=report_id)

        # Der Abbruch darf den Report nicht als abgeschlossen markieren.
        # Genau auf das Stage-Argument pruefen — ein Substring-Check auf den
        # ganzen Call wuerde auch `completed_sections=[...]` und die Meldung
        # "Section 1 completed" treffen und damit immer anschlagen.
        completed = [
            call
            for call in mock_rm.update_progress.call_args_list
            if len(call.args) > 1 and call.args[1] == "completed"
        ]
        assert not completed, (
            "generate_report hat trotz Budgetabbruch update_progress(..., 'completed', ...) "
            f"aufgerufen: {completed}"
        )
