"""Ein degradierter Lauf erscheint nicht mehr als vollständig gesund.

Der Referenzlauf ``report_cc2ef45da5e9`` ging als ``completed`` hinaus: die
Simulation war ``failed``, es lagen 45 von 48 Runden vor, und von acht
``interview_agents``-Aufrufen kam kein einziges Interview zustande. Der
``degradation_log`` blieb leer.

Jede Komponente tat, was sie sollte — niemand zog die Summe. Die Prüfungen
hier sind deterministisch abzählbar; das LLM-Red-Team des Referenzlaufs
übersah sie trotzdem alle.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.contracts.report_contract import RunDegradationModel
from app.models.report import Report, ReportStatus
from app.services.report_agent.run_degradation import (
    apply_run_degradation_downgrade,
    assert_run_invariants,
    collect_run_degradations,
)

#: Der Simulationsstand aus dem Referenzlauf.
REFERENCE_SNAPSHOT: Dict[str, Any] = {
    "rounds_completed": 45,
    "total_rounds": 48,
    "simulation_running": False,
    "simulation_status": "failed",
}


def _reasons(entries: List[Dict[str, Any]]) -> List[str]:
    return [entry["reason"] for entry in entries]


# --- Simulation -------------------------------------------------------------


def test_a_failed_simulation_is_a_blocking_degradation():
    found = collect_run_degradations(simulation_snapshot=REFERENCE_SNAPSHOT)

    assert "simulation_failed" in _reasons(found)
    assert any(
        entry["severity"] == "blocking"
        for entry in found
        if entry["reason"] == "simulation_failed"
    )


def test_incomplete_rounds_are_named_with_their_numbers():
    found = collect_run_degradations(simulation_snapshot=REFERENCE_SNAPSHOT)

    assert "45_of_48_rounds" in _reasons(found)


def test_a_complete_healthy_simulation_produces_nothing():
    assert (
        collect_run_degradations(
            simulation_snapshot={
                "rounds_completed": 48,
                "total_rounds": 48,
                "simulation_status": "completed",
            }
        )
        == []
    )


def test_an_unknown_total_round_count_is_not_treated_as_a_shortfall():
    """``total_rounds=0`` heißt "der Runner weiß es nicht", nicht "null Runden"."""
    found = collect_run_degradations(
        simulation_snapshot={
            "rounds_completed": 12,
            "total_rounds": 0,
            "simulation_status": "completed",
        }
    )

    assert found == []


def test_a_missing_snapshot_produces_nothing():
    assert collect_run_degradations(simulation_snapshot=None) == []


# --- Interviews -------------------------------------------------------------


def test_requested_interviews_without_a_single_result_are_a_degradation():
    found = collect_run_degradations(
        interviews_requested=8,
        interviews_succeeded=0,
        interview_disabled_reason="keine persistierten Agent-Personas",
    )

    assert _reasons(found) == ["0_successful_interviews"]
    assert "keine persistierten Agent-Personas" in found[0]["detail"]


def test_a_single_successful_interview_is_no_degradation():
    assert (
        collect_run_degradations(interviews_requested=8, interviews_succeeded=1) == []
    )


def test_a_report_that_never_asked_for_interviews_is_not_degraded_by_it():
    assert collect_run_degradations(interviews_requested=0, interviews_succeeded=0) == []


# --- Abschnitte und Export --------------------------------------------------


def test_failed_sections_are_named():
    found = collect_run_degradations(failed_section_indices=[2, 5])

    assert _reasons(found) == ["2_sections_failed"]
    assert "2, 5" in found[0]["detail"]


def test_forced_final_generation_is_recorded_as_a_warning():
    found = collect_run_degradations(forced_final_section_indices=[3])

    assert _reasons(found) == ["1_sections_forced_final"]
    assert found[0]["severity"] == "warning"


def test_contract_validation_errors_are_blocking():
    found = collect_run_degradations(contract_validation_errors=["missing field"])

    assert found[0]["component"] == "contract_export"
    assert found[0]["severity"] == "blocking"


# --- Statusabstufung --------------------------------------------------------


def test_a_degraded_run_never_stays_completed():
    found = collect_run_degradations(simulation_snapshot=REFERENCE_SNAPSHOT)

    assert (
        apply_run_degradation_downgrade(ReportStatus.COMPLETED, found)
        is ReportStatus.INCOMPLETE
    )


def test_a_clean_run_keeps_its_status():
    assert (
        apply_run_degradation_downgrade(ReportStatus.COMPLETED, [])
        is ReportStatus.COMPLETED
    )


def test_a_failed_status_is_never_upgraded():
    found = collect_run_degradations(simulation_snapshot=REFERENCE_SNAPSHOT)

    assert (
        apply_run_degradation_downgrade(ReportStatus.FAILED, found)
        is ReportStatus.FAILED
    )


# --- Der Report trägt den Zustand -------------------------------------------


def test_the_report_exposes_its_degradation():
    report = Report(
        report_id="report_x",
        simulation_id="sim_x",
        graph_id="graph_x",
        simulation_requirement="Test",
        status=ReportStatus.INCOMPLETE,
        run_degradations=collect_run_degradations(
            simulation_snapshot=REFERENCE_SNAPSHOT
        ),
    )

    assert report.degraded is True
    assert report.to_dict()["degraded"] is True
    assert len(report.to_dict()["run_degradations"]) == 2


def test_a_report_without_degradations_is_not_degraded():
    report = Report(
        report_id="report_x",
        simulation_id="sim_x",
        graph_id="graph_x",
        simulation_requirement="Test",
        status=ReportStatus.COMPLETED,
    )

    assert report.degraded is False


def test_every_collected_entry_validates_against_the_contract():
    found = collect_run_degradations(
        simulation_snapshot=REFERENCE_SNAPSHOT,
        interviews_requested=8,
        interviews_succeeded=0,
        failed_section_indices=[2],
        forced_final_section_indices=[3],
        metadata_failed_section_indices=[4],
        contract_validation_errors=["boom"],
    )

    assert [RunDegradationModel.model_validate(entry) for entry in found]


# --- Red-Team-Invarianten ---------------------------------------------------


def test_the_reference_run_violates_every_invariant():
    """Genau die Konstellation, die das LLM-Red-Team durchgehen ließ."""
    violations = assert_run_invariants(
        status="completed",
        run_degradations=[],
        simulation_status="failed",
        interviews_requested=8,
        interviews_succeeded=0,
    )

    assert "interviews_requested_but_none_succeeded_and_not_degraded" in violations
    assert "simulation_unhealthy_and_degradation_log_empty" in violations


def test_a_degraded_run_may_not_call_itself_completed():
    violations = assert_run_invariants(
        status="completed",
        run_degradations=[{"component": "simulation", "reason": "simulation_failed"}],
    )

    assert "degraded_run_reported_as_completed" in violations


def test_a_healthy_run_violates_nothing():
    assert (
        assert_run_invariants(
            status="completed",
            run_degradations=[],
            simulation_status="completed",
            interviews_requested=3,
            interviews_succeeded=3,
        )
        == []
    )


def test_a_degraded_run_marked_incomplete_violates_nothing():
    assert (
        assert_run_invariants(
            status="incomplete",
            run_degradations=[
                {"component": "simulation", "reason": "simulation_failed"}
            ],
            simulation_status="failed",
            interviews_requested=8,
            interviews_succeeded=0,
        )
        == []
    )
