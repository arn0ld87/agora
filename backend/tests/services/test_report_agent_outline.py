"""Issue #1832: freie Szenariotitel und ehrliche Planungsfehler."""
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import ReportOutlineModel
from app.services.report_agent.planning import plan_outline
from app.services.report_agent.run_degradation import events_for
from app.services.run_budget import BudgetExceededError


def _make_agent():
    agent = MagicMock()
    agent.graph_id = "graph_outline"
    agent.simulation_requirement = "Geburtshilfe bündeln: Rettungswege und Hebammenwechsel prüfen."
    agent.graph_tools.get_simulation_context.return_value = {
        "graph_statistics": {"total_nodes": 10, "total_edges": 5, "entity_types": {}},
        "total_entities": 10,
        "related_facts": ["Nur zwei von sieben Hebammen wollen wechseln."],
    }
    return agent


def _response(titles=("Rettungswege bei Paralleleinsätzen", "Wechselbereitschaft der Hebammen")):
    return {
        "title": "Geburtshilfe im Landkreis",
        "summary": "Bündelung unter knappen Personalressourcen",
        "sections": [{"title": title, "description": "Quellen und simulierte Stimmen abgleichen."} for title in titles],
    }


def test_free_scenario_titles_survive_planning_and_contract_roundtrip():
    agent = _make_agent()
    agent.llm.chat_json.return_value = _response()
    outline = plan_outline(agent)
    validated = ReportOutlineModel.model_validate({
        "title": outline.title,
        "summary": outline.summary,
        "sections": [{"title": s.title, "description": s.description} for s in outline.sections],
    })
    assert [s.title for s in validated.sections] == [s["title"] for s in _response()["sections"]]
    assert events_for(agent).fallback_outline_used is False
    messages = agent.llm.chat_json.call_args.kwargs["messages"]
    assert agent.simulation_requirement in messages[1]["content"]
    assert "Nur zwei von sieben Hebammen" in messages[1]["content"]
    assert "Persona-Tabelle" not in messages[1]["content"]


@pytest.mark.parametrize("error", [RuntimeError("Provider nicht erreichbar"), ValueError("Invalid JSON format from LLM")])
def test_planning_failure_preserves_cause_without_success_event(error):
    agent = _make_agent()
    agent.llm.chat_json.side_effect = error
    progress = MagicMock()
    with pytest.raises(type(error), match=str(error)) as caught:
        plan_outline(agent, progress_callback=progress)
    assert caught.value is error
    assert events_for(agent).fallback_outline_used is False
    assert not any(call.args[1] == 100 for call in progress.call_args_list)


@pytest.mark.parametrize("titles", [(), ("Hebammen", "  HEBAMMEN "), ("  ",)])
def test_invalid_model_outline_is_rejected_without_replacement(titles):
    agent = _make_agent()
    agent.llm.chat_json.return_value = _response(titles)
    with pytest.raises(ValidationError, match="sections|title|doppelt|eindeutig"):
        plan_outline(agent)
    assert events_for(agent).fallback_outline_used is False


def test_budget_abort_preserves_identity_and_termination_reason():
    agent = _make_agent()
    error = BudgetExceededError("calls", 10, 10)
    agent.llm.chat_json.side_effect = error
    with pytest.raises(BudgetExceededError, match="10 >= 10") as caught:
        plan_outline(agent)
    assert caught.value is error
    assert caught.value.termination_reason == "budget_calls"
    agent.llm.chat_json.assert_called_once()


def test_explicit_required_sections_preserve_order():
    agent = _make_agent()
    required = [("Rettungswege", "Kapazität"), ("Hebammen", "Wechsel")]
    agent.llm.chat_json.return_value = _response(tuple(title for title, _ in required))
    outline = plan_outline(agent, required_sections=required)
    assert [s.title for s in outline.sections] == [title for title, _ in required]


@pytest.mark.parametrize("titles", [("Hebammen", "Rettungswege"), ("Rettungswege",), ("Rettungswege", "Personal")])
def test_explicit_required_sections_reject_changed_order_or_titles(titles):
    agent = _make_agent()
    agent.llm.chat_json.return_value = _response(titles)
    with pytest.raises(ValueError, match="required_sections"):
        plan_outline(agent, required_sections=[("Rettungswege", "Kapazität"), ("Hebammen", "Wechsel")])
