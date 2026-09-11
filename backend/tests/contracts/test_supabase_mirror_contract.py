"""Contracts fuer den Supabase-Mirror (Phase 1)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import ReportStatus
from app.contracts.supabase_mirror_contract import (
    MAX_EVENT_MESSAGE_CHARS,
    DocumentMirrorRecord,
    ReportIndexRecord,
    RunEventMirrorRecord,
    RunMirrorRecord,
)


class TestRunMirrorRecord:
    def test_accepts_canonical_registry_manifest_shape(self):
        record = RunMirrorRecord(
            run_id="run_abc123",
            run_type="simulation",
            entity_id="sim_1",
            status="processing",
            progress=40,
            started_at="2026-09-11T10:00:00",
            updated_at="2026-09-11T10:01:00",
            parent_run_id=None,
            completed_at=None,
            project_id="proj_1",
            simulation_id="sim_1",
        )
        assert record.status == "processing"
        assert record.message == ""

    def test_rejects_unknown_status(self):
        with pytest.raises(ValidationError):
            RunMirrorRecord(
                run_id="run_abc123",
                run_type="simulation",
                entity_id="sim_1",
                status="running",  # nicht kanonisch — RunRegistry normalisiert
                started_at="2026-09-11T10:00:00",
                updated_at="2026-09-11T10:01:00",
            )

    def test_rejects_progress_out_of_bounds(self):
        with pytest.raises(ValidationError):
            RunMirrorRecord(
                run_id="run_abc123",
                run_type="simulation",
                entity_id="sim_1",
                status="processing",
                progress=101,
                started_at="2026-09-11T10:00:00",
                updated_at="2026-09-11T10:01:00",
            )

    def test_is_strict(self):
        with pytest.raises(ValidationError):
            RunMirrorRecord.model_validate(
                {
                    "run_id": "run_abc123",
                    "run_type": "simulation",
                    "entity_id": "sim_1",
                    "status": "pending",
                    "started_at": "2026-09-11T10:00:00",
                    "updated_at": "2026-09-11T10:01:00",
                    "not_in_contract": True,
                }
            )


class TestRunEventMirrorRecord:
    def test_message_limit_is_payload_guard(self):
        assert MAX_EVENT_MESSAGE_CHARS == 1000

    def test_progress_optional(self):
        record = RunEventMirrorRecord(
            run_id="run_abc123",
            seq=0,
            occurred_at="2026-09-11T10:00:00",
            event_type="created",
            status="pending",
        )
        assert record.progress is None
        assert record.message == ""


class TestReportIndexRecord:
    def test_defaults_reflect_no_evidence(self):
        record = ReportIndexRecord(
            report_id="rep_1",
            status="incomplete",
            artifact_path="reports/rep_1",
        )
        assert record.status is ReportStatus.INCOMPLETE
        assert record.evidence_ok is False
        assert record.evidence_sections == 0

    def test_accepts_every_report_status_value(self):
        # Der Spiegel darf keinen Status verlieren, den die Wahrheit kennt.
        for status in ReportStatus:
            record = ReportIndexRecord(
                report_id="rep_1",
                status=status.value,
                artifact_path="reports/rep_1",
            )
            assert record.status is status

    @pytest.mark.parametrize("status", ["unknown", "INCOMPLETE", "", "done"])
    def test_rejects_status_outside_report_contract(self, status):
        # Regression: status war ein freier String — "unknown" landete so
        # als erfundener Wert in agora.report_index.
        with pytest.raises(ValidationError):
            ReportIndexRecord(
                report_id="rep_1",
                status=status,
                artifact_path="reports/rep_1",
            )


class TestDocumentMirrorRecord:
    def test_enrichment_optional(self):
        record = DocumentMirrorRecord(
            project_id="proj_1",
            document_id="report",
            filename="report.md",
        )
        assert record.size_bytes is None
        assert record.sha256 is None
