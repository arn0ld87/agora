"""HTTP-level tests for the unified report export endpoint (Slice 5.1)."""

from __future__ import annotations

import json

import pytest
from flask import Flask

from app.api import report_bp
from app.api.report import _can_reuse_existing_report
from app.services.report_agent import (
    Report,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)
from app.services.report_prompts import DEFAULT_REPORT_SECTIONS
from app.utils.rate_limit import report_rate_limiter


REPORT_ID = "report_abcdef123456"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path / "reports"))

    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")

    yield app.test_client()


@pytest.fixture(autouse=True)
def _reset_report_rate_limiter():
    report_rate_limiter.reset_for_tests()
    yield
    report_rate_limiter.reset_for_tests()


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
                ReportSection(title=title, content=description)
                for title, description in DEFAULT_REPORT_SECTIONS
            ],
        ),
        markdown_content="# Demo\n\nBody",
        created_at="2026-04-29T10:00:00",
        completed_at="2026-04-29T10:05:00",
    )
    if with_evidence:
        # MAI-06: Evidence zuerst speichern, damit save_report → save_report_v3
        # das v3-Artefakt (report-v3.json) bei COMPLETED-Reports schreibt.
        ReportManager._ensure_report_folder(REPORT_ID)
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
                            # ADR-0002 Anker 4 (Sub-Slice M11.7b): high verlangt
                            # 2 Stakeholder-Gruppen via agent_quote — Demo-Fixture
                            # bleibt auf medium, ein Cross-Stakeholder-Setup ist
                            # nicht im Scope des Export-Tests.
                            "confidence_label": "medium",
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
    ReportManager.save_report(report)


def _persist_report_with_hypotheses() -> None:
    outline = ReportOutline(
        title="Demo",
        summary="Summary",
        sections=[
            ReportSection(title=title, content=description)
            for title, description in DEFAULT_REPORT_SECTIONS
        ],
    )
    ReportManager.save_section(
        REPORT_ID,
        1,
        ReportSection(title="Executive Summary", content="Body"),
    )
    ReportManager.save_evidence_map(REPORT_ID, {
        "schema_version": 2,
        "report_id": REPORT_ID,
        "simulation_id": "sim_abcdef123456",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Executive Summary",
                "section_summary": "Initial framing",
                "claims": [],
                "hypotheses": [
                    {
                        "hypothesis_id": "hypothesis_01",
                        "hypothesis_text": "Indizien legen eine zweite Zielgruppe nahe.",
                        "rationale": "Es gibt Signale im Abschnitt, aber noch keine direkte Evidence.",
                        "suggested_evidence": ["weitere Persona-Quote"],
                    }
                ],
                "data_gaps": [],
            }
        ],
    })
    markdown = ReportManager.assemble_full_report(REPORT_ID, outline)
    report = Report(
        report_id=REPORT_ID,
        simulation_id="sim_abcdef123456",
        graph_id="graph_abcdef123456",
        simulation_requirement="Test requirement",
        status=ReportStatus.COMPLETED,
        outline=outline,
        markdown_content=markdown,
        created_at="2026-04-29T10:00:00",
        completed_at="2026-04-29T10:05:00",
    )
    ReportManager.save_report(report)


def _rate_limited_report_app():
    app = Flask(__name__)
    app.config["AGORA_REPORT_RATE_LIMIT_MAX"] = 2
    app.config["AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app


def test_report_generate_endpoint_rate_limits_requests(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    client = _rate_limited_report_app().test_client()

    for _ in range(2):
        response = client.post("/api/report/generate", json={})
        assert response.status_code == 400

    response = client.post("/api/report/generate", json={})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    payload = response.get_json()
    assert payload["code"] == "rate_limited"
    assert payload["retry_after_seconds"] == 60


def test_report_chat_endpoint_rate_limits_requests(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    client = _rate_limited_report_app().test_client()

    for _ in range(2):
        response = client.post("/api/report/chat", json={})
        assert response.status_code == 400

    response = client.post("/api/report/chat", json={})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    payload = response.get_json()
    assert payload["code"] == "rate_limited"
    assert payload["retry_after_seconds"] == 60


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


def test_get_report_returns_contract_shaped_payload(env):
    _persist_report()
    response = env.get(f"/api/report/{REPORT_ID}")
    assert response.status_code == 200

    payload = response.get_json()["data"]
    assert payload["schema_version"] == 2
    assert payload["report_id"] == REPORT_ID
    assert payload["outline"]["sections"][0] == {
        "title": "Executive Summary",
        "description": "Maximal 12 Sätze, was die Simulation gezeigt hat.",
    }
    assert "content" not in payload["outline"]["sections"][0]


def test_explicit_model_override_disables_existing_report_reuse():
    assert _can_reuse_existing_report(False, None) is True
    assert _can_reuse_existing_report(False, "gemini-3-flash-preview:cloud") is False
    assert _can_reuse_existing_report(True, None) is False


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


def test_hypotheses_in_markdown_and_json(env):
    _persist_report_with_hypotheses()

    md_response = env.get(f"/api/report/{REPORT_ID}/export?format=md")
    assert md_response.status_code == 200
    markdown = md_response.data.decode("utf-8")
    assert "Hypothesen ohne Evidence" in markdown
    # Slice 3 (Issue #495): stabile Re-ID → H{section_idx}_{slot:02d}
    assert "H1_01" in markdown
    assert "weitere Persona-Quote" in markdown

    json_response = env.get(f"/api/report/{REPORT_ID}/export?format=json")
    assert json_response.status_code == 200
    payload = json.loads(json_response.data)
    hypothesis = payload["evidence"]["sections"][0]["hypotheses"][0]
    assert hypothesis["hypothesis_id"] == "hypothesis_01"
    assert hypothesis["suggested_evidence"] == ["weitere Persona-Quote"]


def test_export_md_prefers_report_v3_markdown(env):
    """MAI-06: format=md rendert on-demand aus report-v3.json, keine pre-rendered .md-Datei."""
    _persist_report(with_evidence=True)
    # report-v3.json wurde durch save_report → save_report_v3 geschrieben.
    # Der Export rendert daraus dynamisch — eine manuell abgelegte report-v3.md
    # wird ignoriert (kein send_file mehr, MAI-06).
    response = env.get(f"/api/report/{REPORT_ID}/export?format=md")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    # render_report_v3 erzeugt diesen Header und den Mode-Banner
    assert "# Agora ReportV3" in body
    assert "**Report-Modus:**" in body
