"""Ein terminal ausgefallenes Tool wird abgeschaltet, nicht abgeraten.

Im Referenzlauf ``report_cc2ef45da5e9`` meldete der erste
``interview_agents``-Aufruf "TERMINALLY UNAVAILABLE … Do NOT call
interview_agents again" — und wurde danach sieben weitere Male aufgerufen.
Acht Aufrufe, null erfolgreiche Interviews.

Ein Satz im Tool-Ergebnis ist eine Bitte. Das Tool stand in jeder Iteration
unverändert im angebotenen Schema, und der Hinweis fiel spätestens beim
nächsten Abschnitt aus dem Nachrichtenverlauf.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

from app.services.graph.graph_dtos import InterviewResult
from app.services.report_agent.tool_circuit_breaker import (
    ToolCircuitBreaker,
    breaker_for,
)
from app.services.report_agent.tools import define_tools, execute_tool_call


class _Agent:
    """Das Minimum, das ``define_tools``/``execute_tool_call`` anfassen."""

    def __init__(self, interview_result: InterviewResult) -> None:
        self.graph_tools = MagicMock()
        self.graph_tools.interview_agents.return_value = interview_result
        self.web_tools = MagicMock()
        self.web_tools.is_available.return_value = False
        self.graph_id = "graph_test"
        self.simulation_id = "sim_test"
        self.simulation_requirement = "Testanforderung"
        self._current_section_index = 0

    def _record_tool_evidence(self, *args: Any, **kwargs: Any) -> None:
        return None


def _terminal_result() -> InterviewResult:
    result = InterviewResult(interview_topic="Stakeholder", interview_questions=[])
    result.summary = "Interview tool TERMINALLY UNAVAILABLE for this report run."
    result.terminal_failure = True
    result.terminal_reason = "keine persistierten Agent-Personas"
    return result


def _healthy_result() -> InterviewResult:
    result = InterviewResult(interview_topic="Stakeholder", interview_questions=[])
    result.summary = "Zwei Interviews geführt."
    return result


def _interview_calls(agent: _Agent) -> int:
    return agent.graph_tools.interview_agents.call_count


# --- Der Zustand selbst -----------------------------------------------------


def test_a_tripped_breaker_reports_the_tool_as_disabled():
    breaker = ToolCircuitBreaker()
    breaker.trip("interview_agents", "keine Personas")

    assert breaker.is_disabled("interview_agents")
    assert breaker.disabled_tools == frozenset({"interview_agents"})
    assert breaker.reason_for("interview_agents") == "keine Personas"


def test_a_retryable_failure_does_not_disable_anything():
    """Ein einzelner Timeout ist kein terminaler Ausfall."""
    breaker = ToolCircuitBreaker()
    breaker.trip("quick_search", "Zeitüberschreitung", retryable=True)

    assert not breaker.is_disabled("quick_search")
    assert breaker.disabled_tools == frozenset()


def test_the_first_reason_survives_a_second_failure():
    breaker = ToolCircuitBreaker()
    breaker.trip("interview_agents", "erste Ursache")
    breaker.trip("interview_agents", "zweite Ursache")

    assert breaker.reason_for("interview_agents") == "erste Ursache"


def test_the_breaker_is_shared_across_lookups_on_one_agent():
    agent = _Agent(_healthy_result())

    assert breaker_for(agent) is breaker_for(agent)


# --- Wirkung auf das Tool-Angebot -------------------------------------------


def test_interview_agents_is_offered_before_the_failure():
    agent = _Agent(_terminal_result())

    assert "interview_agents" in define_tools(agent)


def test_terminal_interview_failure_disables_tool_for_remaining_report():
    """Der Regressionstest aus der Spezifikation.

    Geprüft wird über Section-Grenzen hinweg: ``define_tools`` wird pro
    Iteration neu aufgebaut, der Breaker lebt am Agent und überdauert das.
    """
    agent = _Agent(_terminal_result())

    execute_tool_call(agent, "interview_agents", {"interview_topic": "Sorgen"})

    assert "interview_agents" not in define_tools(agent)

    # Zweiter Abschnitt, neue Iteration, frisch aufgebautes Angebot.
    agent._current_section_index = 3
    assert "interview_agents" not in define_tools(agent)


def test_the_other_tools_stay_available():
    agent = _Agent(_terminal_result())

    execute_tool_call(agent, "interview_agents", {"interview_topic": "Sorgen"})
    offered = define_tools(agent)

    assert {"insight_forge", "panorama_search", "quick_search"} <= set(offered)


def _timeout_result() -> InterviewResult:
    """Wie ``graph_tools`` einen Timeout meldet: ohne terminales Signal."""
    result = InterviewResult(interview_topic="Stakeholder", interview_questions=[])
    result.summary = "Interview tool TERMINALLY UNAVAILABLE (reason: request timed out)."
    result.terminal_reason = "request timed out after 180s"
    return result


def test_a_timeout_does_not_disable_the_tool_for_the_whole_run():
    """Der Breaker ist für terminale Ausfälle da, nicht für Last.

    Der 180-Sekunden-Deckel greift bei Auslastung, nicht bei Unerreichbarkeit.
    Ein einzelner langsamer Batch darf den Bericht nicht um alle weiteren
    Interviews bringen — erst recht nicht mit einer blockierenden
    Degradierung und einer Statusabstufung im Schlepptau.
    """
    agent = _Agent(_timeout_result())

    execute_tool_call(agent, "interview_agents", {"interview_topic": "Sorgen"})

    assert "interview_agents" in define_tools(agent)


def test_a_successful_interview_leaves_the_tool_in_place():
    agent = _Agent(_healthy_result())

    execute_tool_call(agent, "interview_agents", {"interview_topic": "Sorgen"})

    assert "interview_agents" in define_tools(agent)


# --- Wirkung auf die Ausführung ---------------------------------------------


def test_a_second_call_is_refused_without_reaching_the_tool():
    """Zweite Verteidigungslinie: im XML-Modus ist der Tool-Name freier Text."""
    agent = _Agent(_terminal_result())

    execute_tool_call(agent, "interview_agents", {"interview_topic": "Sorgen"})
    assert _interview_calls(agent) == 1

    answer = execute_tool_call(agent, "interview_agents", {"interview_topic": "Mehr"})

    assert _interview_calls(agent) == 1, "Das Tool darf kein zweites Mal laufen"
    assert "nicht verfügbar" in answer
    assert "keine persistierten Agent-Personas" in answer


def test_eight_attempts_produce_exactly_one_call():
    """Die Zahl aus dem Referenzlauf, gegengeprüft."""
    agent = _Agent(_terminal_result())

    for _ in range(8):
        execute_tool_call(agent, "interview_agents", {"interview_topic": "Sorgen"})

    assert _interview_calls(agent) == 1


# --- Signal aus dem Tool ----------------------------------------------------


def test_the_interview_result_carries_the_failure_as_a_field():
    payload: Dict[str, Any] = _terminal_result().to_dict()

    assert payload["terminal_failure"] is True
    assert payload["terminal_reason"] == "keine persistierten Agent-Personas"


def test_a_healthy_result_reports_no_terminal_failure():
    assert _healthy_result().to_dict()["terminal_failure"] is False


def test_filter_tools_removes_disabled_entries():
    breaker = ToolCircuitBreaker()
    breaker.trip("interview_agents", "aus")
    names: List[str] = ["quick_search", "interview_agents"]

    assert breaker.filter_tools(names) == ["quick_search"]
