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
from unittest.mock import MagicMock

import pytest

from app.contracts.report_contract import RunDegradationModel
from app.models.report import Report, ReportStatus
from app.services.report_agent.manager import ReportManager
from app.services.report_agent.workflow import generate_section_metadata
from app.services.report_agent.run_degradation import (
    apply_run_degradation_downgrade,
    assert_run_invariants,
    collect_run_degradations,
    events_for,
    mark_forced_final,
    mark_metadata_failure,
    mark_work_traces_removed,
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


def test_removed_work_traces_are_recorded_as_a_warning():
    """Issue #1321: eine still bereinigte Section ist im Bericht nicht von einer
    unangetasteten zu unterscheiden. Die Entfernung wird zur Warnung — ohne
    Statusabstieg, der Abschnittsinhalt selbst ist ja erhalten."""
    found = collect_run_degradations(work_trace_removed_section_indices=[7])

    assert _reasons(found) == ["1_sections_sanitized"]
    assert "7" in found[0]["detail"]
    assert found[0]["severity"] == "warning"


def test_contract_validation_errors_are_blocking():
    found = collect_run_degradations(contract_validation_errors=["missing field"])

    assert found[0]["component"] == "contract_export"
    assert found[0]["severity"] == "blocking"


# --- Ereignisse aus dem laufenden Bericht -----------------------------------


def test_forced_final_and_metadata_failures_are_collected_per_agent():
    """Beide Ereignisse standen im Referenzlauf nur im Log.

    Ein Abschnitt, der erst nach erzwungener Endgenerierung entstand, sieht im
    Bericht aus wie jeder andere — dem Agenten waren die Schritte ausgegangen,
    und niemand erfuhr es.
    """
    class _Agent:
        pass

    agent = _Agent()
    mark_forced_final(agent, 3)
    mark_forced_final(agent, 3)
    mark_metadata_failure(agent, 5)

    events = events_for(agent)
    assert events.forced_final_sections == {3}
    assert events.metadata_failed_sections == {5}


def test_the_event_log_is_shared_across_lookups():
    class _Agent:
        pass

    agent = _Agent()

    assert events_for(agent) is events_for(agent)


def test_a_clean_run_records_no_events():
    class _Agent:
        pass

    events = events_for(_Agent())

    assert events.forced_final_sections == set()
    assert events.metadata_failed_sections == set()


def test_collected_events_reach_the_degradation_list():
    class _Agent:
        pass

    agent = _Agent()
    mark_forced_final(agent, 2)
    mark_metadata_failure(agent, 4)

    found = collect_run_degradations(
        forced_final_section_indices=events_for(agent).forced_final_sections,
        metadata_failed_section_indices=events_for(agent).metadata_failed_sections,
    )

    assert _reasons(found) == [
        "1_sections_forced_final",
        "1_sections_without_metadata",
    ]
    # Beides sind Warnungen: der Abschnitt existiert, er ist nur schwächer
    # zustande gekommen. Ein Statusabstieg wäre hier unverhältnismäßig.
    assert {entry["severity"] for entry in found} == {"warning"}


def test_a_failed_metadata_extraction_marks_its_section():
    """Der Vermerk entsteht dort, wo der Fehlschlag passiert.

    Ohne diesen Test wäre nur belegt, dass das Register funktioniert — nicht,
    dass es jemand befüllt. Genau diese Lücke hatte der Referenzlauf: das
    Ereignis war da, die Meldung fehlte.
    """
    agent = MagicMock()
    agent.llm.chat_json.side_effect = RuntimeError("Extraktion gescheitert")

    result = generate_section_metadata(
        agent,
        section_title="Ausgangslage",
        section_content="Ein Abschnitt mit Inhalt.",
        section_index=4,
    )

    assert result == {}
    assert events_for(agent).metadata_failed_sections == {4}


def test_a_successful_metadata_extraction_marks_nothing():
    agent = MagicMock()
    agent.llm.chat_json.return_value = {}

    generate_section_metadata(
        agent,
        section_title="Ausgangslage",
        section_content="Ein Abschnitt mit Inhalt.",
        section_index=4,
    )

    assert events_for(agent).metadata_failed_sections == set()


def test_marking_work_trace_removal_reaches_the_degradation_list():
    class _Agent:
        pass

    agent = _Agent()
    mark_work_traces_removed(agent, 7)
    mark_work_traces_removed(agent, 7)

    assert events_for(agent).work_trace_removed_sections == {7}

    found = collect_run_degradations(
        work_trace_removed_section_indices=events_for(
            agent
        ).work_trace_removed_sections,
    )

    assert _reasons(found) == ["1_sections_sanitized"]


def test_finalize_content_records_removed_work_traces_on_the_agent():
    """Issue #1321: `_finalize_content` entfernte Arbeitsspur-Segmente bisher
    nur ins Server-Log — im Bericht sah der Abschnitt aus wie jeder andere.
    Mit ``agent`` trägt der Lauf das Ereignis in sein Ereignisregister."""
    from app.services.report_agent.workflow import _finalize_content

    class _Agent:
        pass

    agent = _Agent()
    body = "Der Markt für Arbeitsplanung verändert sich spürbar. " * 5
    response = f"Thought: Ich sollte jetzt die Personas zusammenstellen.\n## Ausgangslage\n{body}"

    content = _finalize_content(
        response,
        section_title="Ausgangslage",
        section_index=3,
        agent=agent,
    )

    assert events_for(agent).work_trace_removed_sections == {3}
    assert "Thought:" not in content
    assert content.startswith("## Ausgangslage")


def test_finalize_content_without_agent_stays_quiet():
    """Ohne ``agent`` (alter Aufrufpfad, Tests) verhält sich der Sanitizer
    unverändert — kein Crash, kein Marker."""
    from app.services.report_agent.workflow import _finalize_content

    class _Agent:
        pass

    agent = _Agent()
    body = "Der Markt für Arbeitsplanung verändert sich spürbar. " * 5
    response = f"Thought: Ich sollte jetzt die Personas zusammenstellen.\n## Ausgangslage\n{body}"

    content = _finalize_content(
        response,
        section_title="Ausgangslage",
        section_index=3,
    )

    assert "Thought:" not in content
    assert events_for(agent).work_trace_removed_sections == set()


def test_a_fully_rejected_output_is_not_double_marked():
    """Wirft der Final-Content-Contract den ganzen Output weg, endet der
    Abschnitt im Fallback-Text — und der ist über ``generation_failed``
    bzw. ``failed_section_indices`` sichtbar. Der Sanitization-Marker bleibt
    dem Pfad mit erhaltenem Inhalt vorbehalten, sonst zählt derselbe
    Abschnitt doppelt."""
    from app.services.report_agent.workflow import _finalize_content
    from app.services.report_agent.output_contract import is_fallback_content

    class _Agent:
        pass

    agent = _Agent()

    result = _finalize_content(
        "Thought: Ich sollte zuerst das Graph-Werkzeug fragen.",
        section_title="Ausgangslage",
        section_index=2,
        agent=agent,
    )

    assert is_fallback_content(result)
    assert events_for(agent).work_trace_removed_sections == set()


def test_a_budget_abort_is_not_swallowed_as_a_metadata_failure():
    """Ein erschöpftes Budget beendet den Lauf, es degradiert ihn nicht."""
    from app.services.run_budget import BudgetExceededError

    agent = MagicMock()
    agent.llm.chat_json.side_effect = BudgetExceededError("tokens", 1000, 500)

    with pytest.raises(BudgetExceededError):
        generate_section_metadata(
            agent,
            section_title="Ausgangslage",
            section_content="Ein Abschnitt mit Inhalt.",
            section_index=4,
        )


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


def test_a_warning_alone_does_not_downgrade():
    """Sonst wäre jeder Bericht über eine laufende Simulation unvollständig."""
    warning_only = collect_run_degradations(
        simulation_snapshot={
            "rounds_completed": 12,
            "total_rounds": 48,
            "simulation_running": True,
            "simulation_status": "running",
        }
    )

    assert [entry["severity"] for entry in warning_only] == ["warning"]
    assert (
        apply_run_degradation_downgrade(ReportStatus.COMPLETED, warning_only)
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
    assert len(report.to_dict()["run_degradations"]) == 2
    # ``degraded`` ist ableitbar und gehört nicht in den Payload: ReportModel
    # verbietet unbekannte Felder, und ein zusätzlicher Schlüssel ließ den
    # Export mit 400 antworten.
    assert "degraded" not in report.to_dict()


def test_degradations_survive_a_save_and_load_round_trip(tmp_path, monkeypatch):
    """Ohne Rücklesen meldet jede API-Antwort einen gesunden Lauf.

    ``Report.to_dict()`` schrieb die Mängel in ``meta.json``, aber
    ``get_report()`` baute den Report mit einer festen kwarg-Liste neu, die
    dort aufhörte — ``GET /api/report/<id>`` lieferte auch für den
    gescheiterten Lauf ``run_degradations: []``.
    """
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    report = Report(
        report_id="report_roundtrip",
        simulation_id="sim_x",
        graph_id="graph_x",
        simulation_requirement="Test",
        status=ReportStatus.INCOMPLETE,
        run_degradations=collect_run_degradations(
            simulation_snapshot=REFERENCE_SNAPSHOT
        ),
    )
    ReportManager.save_report(report)

    loaded = ReportManager.get_report("report_roundtrip")

    assert loaded is not None
    assert loaded.degraded is True
    assert _reasons(loaded.run_degradations) == ["simulation_failed", "45_of_48_rounds"]


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
        work_trace_removed_section_indices=[6],
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


def test_a_blocking_degradation_may_not_call_itself_completed():
    violations = assert_run_invariants(
        status="completed",
        run_degradations=[{
            "component": "simulation",
            "reason": "simulation_failed",
            "severity": "blocking",
        }],
    )

    assert "degraded_run_reported_as_completed" in violations


def test_a_warning_alone_does_not_contradict_completed():
    """Ein Bericht über einen laufenden Lauf ist nicht unvollständig.

    Der Zwischenstand steht in ``run_degradations`` und wird ausgewiesen —
    aber ein ausdrücklich unterstützter Ablauf darf nicht dauerhaft
    ``incomplete`` erzeugen.
    """
    violations = assert_run_invariants(
        status="completed",
        run_degradations=[{
            "component": "simulation",
            "reason": "45_of_48_rounds",
            "severity": "warning",
        }],
    )

    assert violations == []


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
                {"component": "simulation", "reason": "simulation_failed"},
                {"component": "interview_agents", "reason": "0_successful_interviews"},
            ],
            simulation_status="failed",
            interviews_requested=8,
            interviews_succeeded=0,
        )
        == []
    )
