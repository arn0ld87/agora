"""Was sich abzählen lässt, gehört nicht in einen Prompt.

Das LLM-Red-Team des Referenzlaufs ``report_cc2ef45da5e9`` erkannte einige
Probleme, übersah aber: null erfolgreiche Interviews, wiederholte Aufrufe nach
einem terminalen Ausfall, eine gescheiterte Simulation bei 45 von 48 Runden
und einen leeren Degradation-Log über all dem.

Jeder dieser Befunde ist eine Zählung. Ein Sprachmodell kann sie übersehen,
eine Invariante nicht — und sie kostet keinen Aufruf, weshalb sie auch dann
läuft, wenn das LLM-Red-Team übersprungen wird.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

from app.models.report import Report, ReportStatus
from app.services.report_agent.tool_circuit_breaker import breaker_for
from app.services.report_agent.workflow import _deterministic_red_team_findings

REFERENCE_SNAPSHOT: Dict[str, Any] = {
    "rounds_completed": 45,
    "total_rounds": 48,
    "simulation_running": False,
    "simulation_status": "failed",
}


def _agent(*, interview_requests: int = 0, interview_records: int = 0) -> Any:
    agent = MagicMock()
    agent.evidence_map = {
        "evidence_index": {
            f"ev_{i}": {
                "evidence_id": f"ev_{i}",
                "source_kind": "agent_quote",
                # Der Typ entscheidet, nicht die Quellengattung: ``agent_post``
                # und ``agent_interview`` fallen beide auf ``agent_quote``.
                "type": "agent_interview",
            }
            for i in range(interview_records)
        }
    }
    agent._tool_circuit_breaker = None
    breaker = breaker_for(agent)
    for _ in range(interview_requests):
        breaker.record_request("interview_agents")
    return agent


def _report(**overrides: Any) -> Report:
    payload: Dict[str, Any] = {
        "report_id": "report_x",
        "simulation_id": "sim_x",
        "graph_id": "graph_x",
        "simulation_requirement": "Test",
        "status": ReportStatus.COMPLETED,
    }
    payload.update(overrides)
    return Report(**payload)


def test_the_reference_run_is_flagged_on_every_count():
    """Genau die Konstellation, die das Red Team durchgehen ließ."""
    findings = _deterministic_red_team_findings(
        _agent(interview_requests=8, interview_records=0),
        _report(simulation_snapshot=REFERENCE_SNAPSHOT),
    )

    assert any("Interviews waren Teil des Plans" in f for f in findings)
    assert any("Simulation endete nicht regulär" in f for f in findings)


def test_a_healthy_run_is_flagged_on_nothing():
    findings = _deterministic_red_team_findings(
        _agent(interview_requests=3, interview_records=3),
        _report(
            simulation_snapshot={
                "rounds_completed": 48,
                "total_rounds": 48,
                "simulation_status": "completed",
            }
        ),
    )

    assert findings == []


def test_a_run_that_admits_its_degradation_is_not_flagged_twice():
    """Wer die Einschränkung ausweist, wird dafür nicht gerügt."""
    findings = _deterministic_red_team_findings(
        _agent(interview_requests=8, interview_records=0),
        _report(
            status=ReportStatus.INCOMPLETE,
            simulation_snapshot=REFERENCE_SNAPSHOT,
            run_degradations=[
                {
                    "component": "simulation",
                    "reason": "simulation_failed",
                    "severity": "blocking",
                }
            ],
        ),
    )

    assert findings == []


def test_a_degraded_run_calling_itself_completed_is_flagged():
    findings = _deterministic_red_team_findings(
        _agent(),
        _report(
            status=ReportStatus.COMPLETED,
            run_degradations=[
                {
                    "component": "simulation",
                    "reason": "simulation_failed",
                    "severity": "blocking",
                }
            ],
        ),
    )

    assert any("gilt trotzdem als vollständig" in f for f in findings)


def test_simulation_posts_do_not_count_as_interviews():
    """Der Referenzlauf hatte Simulationsbeiträge und null Interviews.

    Zählte man nach ``source_kind``, wäre die Interview-Invariante genau dann
    still, wenn eine Simulation lief — also im Regelfall.
    """
    agent = _agent(interview_requests=8)
    agent.evidence_map = {
        "evidence_index": {
            "ev_0": {
                "evidence_id": "ev_0",
                "source_kind": "agent_quote",
                "type": "agent_post",
            }
        }
    }

    findings = _deterministic_red_team_findings(agent, _report())

    assert any("Interviews waren Teil des Plans" in f for f in findings)


def test_a_report_that_never_asked_for_interviews_is_not_flagged():
    findings = _deterministic_red_team_findings(_agent(), _report())

    assert findings == []


def test_the_findings_are_human_readable():
    """Sie stehen im Bericht neben den LLM-Befunden."""
    findings = _deterministic_red_team_findings(
        _agent(interview_requests=8, interview_records=0), _report()
    )

    assert findings
    assert all(
        finding[0].isupper() and finding.endswith(".") for finding in findings
    ), findings
