"""HTTP-level tests for the unified report export endpoint (Slice 5.1)."""

from __future__ import annotations

import json

import pytest
from flask import Flask

from app.api import report_bp
from app.services.report_agent import (
    Report,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)


REPORT_ID = "report_abcdef123456"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path / "reports"))

    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")

    yield app.test_client()


def _persist_report(*, with_evidence: bool = False) -> None:
    report = Report(
        report_id=REPORT_ID,
        simulation_id="sim_abcdef123456",
        graph_id="graph_abcdef123456",
        simulation_requirement="Test requirement",
        status=ReportStatus.COMPLETED,
        outline=ReportOutline(
            title="Demo",
            summary="Summary",
            sections=[
                ReportSection(title="Intro", content="Body"),
                ReportSection(title="Outlook", content="Trend"),
            ],
        ),
        markdown_content="# Demo\n\nBody",
        created_at="2026-04-29T10:00:00",
        completed_at="2026-04-29T10:05:00",
    )
    ReportManager.save_report(report)
    if with_evidence:
        # Sub-Slice 02b: persist a v2-contract-compliant evidence map so the
        # strict ReportContractModel envelope round-trips through the export.
        ReportManager.save_evidence_map(REPORT_ID, {
            "schema_version": 2,
            "report_id": REPORT_ID,
            "simulation_id": "sim_abcdef123456",
            "global_evidence": [],
            "sections": [
                {
                    "section_index": 1,
                    "section_title": "Intro",
                    "section_summary": "Initial framing",
                    "claims": [
                        {
                            "claim_id": "claim_01",
                            "claim_text": "Demo claim text long enough",
                            "confidence_score": 0.8,
                            "confidence_label": "high",
                            "evidence": [
                                {
                                    "type": "graph_metric",
                                    "source": "simulation_metrics",
                                    "snippet": "echo_chamber_index: 0.42",
                                    "match_score": 0.7,
                                    "supports_claim": True,
                                }
                            ],
                            "audit_trail": [],
                        }
                    ],
                }
            ],
        })


def test_export_rejects_invalid_report_id(env):
    response = env.get("/api/report/not-a-valid-id/export?format=json")
    assert response.status_code == 400


def test_export_rejects_unknown_format(env):
    _persist_report()
    response = env.get(f"/api/report/{REPORT_ID}/export?format=xml")
    assert response.status_code == 400


def test_export_returns_404_when_report_missing(env):
    response = env.get(f"/api/report/{REPORT_ID}/export?format=json")
    assert response.status_code == 404


def test_export_md_returns_markdown_attachment(env):
    _persist_report()
    response = env.get(f"/api/report/{REPORT_ID}/export?format=md")
    assert response.status_code == 200
    assert response.mimetype == "text/markdown"
    disposition = response.headers.get("Content-Disposition", "")
    assert f"agora-report-{REPORT_ID}.md" in disposition
    assert b"Demo" in response.data


def test_export_md_is_default_format(env):
    _persist_report()
    response = env.get(f"/api/report/{REPORT_ID}/export")
    assert response.status_code == 200
    assert response.mimetype == "text/markdown"


def test_export_json_returns_combined_envelope(env):
    _persist_report(with_evidence=True)
    response = env.get(f"/api/report/{REPORT_ID}/export?format=json")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    disposition = response.headers.get("Content-Disposition", "")
    assert f"agora-report-{REPORT_ID}.json" in disposition

    payload = json.loads(response.data)
    # Sub-Slice 02b: Export-Envelope ist ein ReportContractModel — schema_version
    # ist auf v2 fix-getypt (Literal[2]) und kann nicht mehr driften.
    assert payload["schema_version"] == 2
    assert payload["evidence"]["schema_version"] == 2
    assert payload["exported_at"]
    assert payload["report"]["report_id"] == REPORT_ID
    assert payload["report"]["status"] == "completed"
    assert payload["report"]["schema_version"] == 2
    assert payload["evidence"]["report_id"] == REPORT_ID
    assert payload["evidence"]["sections"][0]["claims"][0]["claim_id"] == "claim_01"


def test_export_json_without_evidence_returns_null_evidence(env):
    _persist_report(with_evidence=False)
    response = env.get(f"/api/report/{REPORT_ID}/export?format=json")
    assert response.status_code == 200
    payload = json.loads(response.data)
    assert payload["report"]["report_id"] == REPORT_ID
    assert payload["evidence"] is None
