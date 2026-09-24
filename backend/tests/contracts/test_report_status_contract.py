"""Contract-Tests fuer ReportStatusResponse (Issue #1174, Codex-Finding 1+2).

Vorher lieferten vier der fuenf Stufen von ``ReportStatusService.get_status``
handgeschriebene Dicts an der API-Grenze aus, und die Run-Registry-Stufe
(hoechste Prioritaet) hatte gar kein ``message_key`` — sie reichte den
Backend-Klartext roh durch. Diese Tests bewachen den Vertrag: strikte
Validierung, das vollstaendige ``message_key``-Set aus #1174 und das
erhaltene Bestandsverhalten (unbesetzte optionale Felder erscheinen nicht
als ``null`` im JSON).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_status_contract import ReportStatusResponse


def test_completed_payload_round_trips():
    payload = ReportStatusResponse(
        simulation_id="sim_1",
        report_id="rep_1",
        status="completed",
        progress=100,
        message="Report generated",
        message_key="report.generated",
        already_completed=True,
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    assert dumped == {
        "simulation_id": "sim_1",
        "report_id": "rep_1",
        "status": "completed",
        "progress": 100,
        "message": "Report generated",
        "message_key": "report.generated",
        "already_completed": True,
    }


def test_run_registry_payload_carries_outline_and_sections():
    payload = ReportStatusResponse(
        simulation_id="sim_1",
        report_id="rep_1",
        run_id="run_1",
        status="processing",
        progress=42,
        message="Section 3 wird generiert",
        message_key="report.generating",
        missing_sections=[],
        outline={"title": "Report", "summary": "—", "sections": []},
        sections={1: {"content": "eins"}},
        current_section_index=1,
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    # JSON-Objektschluessel sind immer Strings — auch vor diesem Contract galt
    # das schon auf dem Draht nach `jsonify()`.
    assert dumped["sections"] == {"1": {"content": "eins"}}
    assert dumped["outline"] == {"title": "Report", "summary": "—", "sections": []}


def test_unset_optional_fields_are_excluded_from_serialization():
    """Bewacht das Bestandsverhalten der literalen Kurzschluesse (z. B.
    `_acknowledge_polling`): `run_id`/`error`/`outline`/`sections`/
    `already_completed` duerfen im JSON nicht als `null` auftauchen."""
    payload = ReportStatusResponse(
        report_id="rep_12",
        status="generating",
        progress=0,
        message="Task handle unknown — waiting for report completion",
        message_key="report.awaiting_task",
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    assert "simulation_id" not in dumped
    for absent_field in (
        "run_id", "error", "outline", "sections", "current_section_index",
        "missing_sections", "already_completed",
    ):
        assert absent_field not in dumped


def test_message_key_is_optional_for_uncovered_statuses():
    """"incomplete"/"stopped" tragen (noch) keinen Schluessel — bewusste
    Grenze dieses Fixes (siehe report_status.py::_RUN_REGISTRY_MESSAGE_KEYS)."""
    payload = ReportStatusResponse(
        report_id="rep_1",
        status="incomplete",
        progress=100,
        message="Report generated with degraded claims",
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    assert "message_key" not in dumped


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        ReportStatusResponse(
            report_id="rep_1",
            status="completed",
            progress=100,
            message="x",
            unexpected_field=True,
        )


def test_unknown_status_value_rejected():
    with pytest.raises(ValidationError):
        ReportStatusResponse(report_id="rep_1", status="unbekannt", progress=0, message="x")


def test_unknown_message_key_rejected():
    with pytest.raises(ValidationError):
        ReportStatusResponse(
            report_id="rep_1",
            status="completed",
            progress=100,
            message="x",
            message_key="report.unbekannt",
        )
