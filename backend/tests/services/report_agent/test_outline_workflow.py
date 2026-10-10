"""Issue #1832: Fehler vor Erfolgsereignissen, echte Resume-Planung."""
from unittest.mock import MagicMock

import pytest

from app.models.report import Report, ReportOutline, ReportSection, ReportStatus
from app.services.report_agent import workflow
from app.services.run_budget import BudgetExceededError


def _outline(titles=("Rettungswege bei Nacht", "Hebammenwechsel")):
    return ReportOutline(title="Geburtshilfe", summary="Versorgung im Landkreis", sections=[
        ReportSection(title=title, description="Quellen und Stimmen prüfen") for title in titles
    ])


@pytest.fixture
def stack(monkeypatch, tmp_path):
    agent = MagicMock()
    agent.simulation_id = "sim_outline"
    agent.graph_id = "graph_outline"
    agent.simulation_requirement = "Geburtshilfe bündeln"
    agent.persona_ids = ["p1", "p2", "p3", "p4", "p5"]
    manager = MagicMock()
    manager.get_report.return_value = None
    manager._ensure_report_folder.return_value = str(tmp_path)
    manager.load_fallback_outline_used.return_value = False
    monkeypatch.setattr(workflow, "ReportManager", manager)
    monkeypatch.setattr(workflow, "capture_simulation_snapshot", lambda _: None)
    monkeypatch.setattr(workflow, "migrate_v1_to_v2", lambda _: None)
    monkeypatch.setattr(workflow, "normalize_persisted_evidence_map", lambda _: {})
    monkeypatch.setattr(workflow, "_compute_stance_analysis", lambda *_: None)
    monkeypatch.setattr(workflow, "_is_cancel_requested", lambda _: True)
    monkeypatch.setattr(workflow, "_build_partial_report", lambda report, **_: report)
    return agent, manager


@pytest.mark.parametrize("error", [RuntimeError("Provider offline"), ValueError("Invalid JSON format from LLM")])
def test_workflow_failure_prevents_outline_success_and_section_calls(stack, monkeypatch, error):
    agent, manager = stack
    planner = MagicMock(side_effect=error)
    section = MagicMock()
    monkeypatch.setattr(workflow, "plan_outline_impl", planner)
    monkeypatch.setattr(workflow, "process_section", section)

    result = workflow.generate_report(agent, report_id="report_outline")

    assert result.status == ReportStatus.FAILED
    assert str(error) in result.error
    agent.ReportLogger.return_value.log_planning_complete.assert_not_called()
    manager.save_outline.assert_not_called()
    section.assert_not_called()


def test_workflow_rejects_invalid_plan_before_persisting_success(stack, monkeypatch):
    agent, manager = stack
    monkeypatch.setattr(workflow, "plan_outline_impl", MagicMock(return_value=_outline(("Hebammen", " HEBAMMEN "))))
    result = workflow.generate_report(agent, report_id="report_outline")
    assert result.status == ReportStatus.FAILED
    agent.ReportLogger.return_value.log_planning_complete.assert_not_called()
    manager.save_outline.assert_not_called()


def test_workflow_budget_abort_reaches_job_owner(stack, monkeypatch):
    agent, manager = stack
    error = BudgetExceededError("calls", 10, 10)
    monkeypatch.setattr(workflow, "plan_outline_impl", MagicMock(side_effect=error))
    with pytest.raises(BudgetExceededError, match="10 >= 10") as caught:
        workflow.generate_report(agent, report_id="report_outline")
    assert caught.value is error
    manager.save_outline.assert_not_called()


@pytest.mark.parametrize("fallback, titles, must_plan", [
    (True, ("Evaluation Scenario and Core Findings",), True),
    (False, ("Hebammen", " HEBAMMEN "), True),
    (False, (), True),
    (False, ("Rettungswege bei Nacht", "Hebammenwechsel"), False),
])
def test_resume_replans_only_historical_fallback_or_invalid_structure(stack, monkeypatch, fallback, titles, must_plan):
    agent, manager = stack
    existing = Report(report_id="report_outline", simulation_id=agent.simulation_id,
                      graph_id=agent.graph_id, simulation_requirement=agent.simulation_requirement,
                      status=ReportStatus.INCOMPLETE, outline=_outline(titles))
    manager.get_report.return_value = existing
    manager.load_fallback_outline_used.return_value = fallback
    replacement = _outline()
    planner = MagicMock(return_value=replacement)
    monkeypatch.setattr(workflow, "plan_outline_impl", planner)

    result = workflow.generate_report(agent, report_id="report_outline")

    assert result.outline is (replacement if must_plan else existing.outline)
    assert planner.call_count == int(must_plan)
    assert manager.save_outline.call_count == int(must_plan)
    if must_plan:
        manager.save_fallback_outline_used.assert_called_with("report_outline", False)
