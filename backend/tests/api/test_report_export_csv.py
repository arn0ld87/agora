"""Tests für den CSV-Export-Endpoint und die csv_export-Helper.

Sub-Slice P4.2 — Refs PLAN.md §5.2

Abgedeckt:
- csv_export.personas_to_csv RFC-4180-Quoting (Komma im Feld)
- csv_export.segments_to_csv Header + Zeilen
- csv_export.claims_to_csv aus evidence-map-Sections
- GET /api/report/<report_id>/export?format=csv&table=personas → 200 text/csv
- GET /api/report/<report_id>/export?format=csv&table=segments → 200 text/csv
- GET /api/report/<report_id>/export?format=csv&table=claims → 200 text/csv
- 404 bei unbekanntem report_id
- 422/400 bei format=xml
- 422/400 bei table=foo
"""

from __future__ import annotations

import csv
import io
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import report_bp
from app.services.report_agent.csv_export import (
    claims_to_csv,
    personas_to_csv,
    segments_to_csv,
)


# ---------------------------------------------------------------------------
# Unit-Tests: csv_export helper
# ---------------------------------------------------------------------------


class TestPersonasToCsv:
    def test_header_row(self):
        out = personas_to_csv([])
        reader = csv.reader(io.StringIO(out))
        header = next(reader)
        assert header[0] == "id"
        assert "beruf" in header
        assert "region" in header

    def test_single_persona(self):
        personas = [
            {
                "id": "P1",
                "voice_register": "neutral-de",
                "alter_range": "35–50",
                "beruf": "Ingenieur",
                "region": "Bayern",
            }
        ]
        out = personas_to_csv(personas)
        rows = list(csv.reader(io.StringIO(out)))
        assert len(rows) == 2  # header + 1 data
        assert rows[1][0] == "P1"
        assert rows[1][4] == "Bayern"

    def test_rfc4180_quoting_comma_in_field(self):
        personas = [
            {
                "id": "P1",
                "voice_register": "neutral-de",
                "alter_range": "35–50",
                "beruf": "Dev, Senior",
                "region": "DACH",
            }
        ]
        out = personas_to_csv(personas)
        assert '"Dev, Senior"' in out

    def test_list_fields_joined_with_semicolon(self):
        personas = [
            {
                "id": "P2",
                "voice_register": "formal-de",
                "alter_range": "25–35",
                "beruf": "Analyst",
                "region": "Österreich",
                "needs": ["Sicherheit", "Transparenz"],
                "values": ["Qualität"],
            }
        ]
        out = personas_to_csv(personas)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][7] == "Sicherheit;Transparenz"
        assert rows[1][8] == "Qualität"

    def test_none_optional_fields(self):
        personas = [
            {
                "id": "P3",
                "voice_register": "technical-de",
                "alter_range": "40–55",
                "beruf": "Arzt",
                "region": "Schweiz",
                "bildungsgrad": None,
                "haushaltseinkommen": None,
            }
        ]
        out = personas_to_csv(personas)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][5] == ""
        assert rows[1][6] == ""


class TestSegmentsToCsv:
    def test_header_row(self):
        out = segments_to_csv([])
        reader = csv.reader(io.StringIO(out))
        header = next(reader)
        assert "id" in header
        assert "name" in header
        assert "persona_ids" in header

    def test_single_segment(self):
        segments = [
            {
                "id": "S1",
                "name": "Entscheider",
                "beschreibung": "Oberes Management",
                "persona_ids": ["P1", "P2"],
                "kontaktwahrscheinlichkeit_prozent": 42.5,
            }
        ]
        out = segments_to_csv(segments)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][0] == "S1"
        assert rows[1][3] == "P1;P2"
        assert rows[1][4] == "42.5"

    def test_none_kontaktwahrscheinlichkeit(self):
        segments = [
            {
                "id": "S2",
                "name": "Anwender",
                "beschreibung": "Endnutzer",
                "persona_ids": [],
                "kontaktwahrscheinlichkeit_prozent": None,
            }
        ]
        out = segments_to_csv(segments)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][4] == ""


class TestClaimsToCsv:
    def test_header_row(self):
        out = claims_to_csv([])
        reader = csv.reader(io.StringIO(out))
        header = next(reader)
        assert "claim_id" in header
        assert "section_index" in header

    def test_claims_from_sections(self):
        sections = [
            {
                "section_index": 1,
                "section_title": "Einleitung",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Nutzer bevorzugen X",
                        "confidence_label": "medium",
                        "confidence_score": 0.65,
                        "evidence": [{"type": "graph_fact", "source": "s", "snippet": "x"}],
                        "notes": "Kurzhinweis",
                    }
                ],
            }
        ]
        out = claims_to_csv(sections)
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][0] == "claim_01"
        assert rows[1][2] == "medium"
        assert rows[1][4] == "1"
        assert rows[1][5] == "Einleitung"
        assert rows[1][6] == "1"  # evidence_count
        assert rows[1][7] == "Kurzhinweis"

    def test_empty_sections(self):
        out = claims_to_csv([])
        rows = list(csv.reader(io.StringIO(out)))
        assert len(rows) == 1  # only header


# ---------------------------------------------------------------------------
# Endpoint-Tests: GET /api/report/<report_id>/export?format=csv&table=...
# ---------------------------------------------------------------------------

VALID_REPORT_ID = "report_abcdef123456"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _make_mock_report():
    mock = MagicMock()
    mock.report_id = VALID_REPORT_ID
    return mock


def _make_evidence_map():
    return {
        "schema_version": 2,
        "report_id": VALID_REPORT_ID,
        "simulation_id": "sim_0123456789ab",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Kontext",
                "section_summary": "Zusammenfassung",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Nutzer bevorzugen A",
                        "confidence_label": "low",
                        "confidence_score": 0.4,
                        "evidence": [],
                        "audit_trail": [],
                        "notes": None,
                    }
                ],
                "hypotheses": [],
                "data_gaps": [],
            }
        ],
    }


def _make_report_v3():
    return {
        "schema_version": 3,
        "report_id": VALID_REPORT_ID,
        "generated_at": "2026-05-10T12:00:00",
        "personas": [
            {
                "id": "P1",
                "voice_register": "neutral-de",
                "alter_range": "30–45",
                "beruf": "Entwickler",
                "region": "Bayern",
            }
        ],
        "segments": [
            {
                "id": "S1",
                "name": "Tech-Affinität",
                "beschreibung": "Technik-begeisterte Nutzer",
                "persona_ids": ["P1"],
                "kontaktwahrscheinlichkeit_prozent": 55.0,
            }
        ],
        "claims": [],
        "multipliers": [],
        "friction_points": [],
        "trust_signals": [],
        "change_recommendations": [],
        "project_impacts": [],
        "positioning_variants": [],
        "content_ideas": [],
        "data_gaps": [],
    }


class TestCsvExportEndpoint:
    def test_personas_csv_200(self, client):
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
            patch("app.api.report.ReportManager.get_report_v3", return_value=_make_report_v3()),
            patch("app.api.report.ReportManager.get_evidence_map", return_value=_make_evidence_map()),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=csv&table=personas")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        assert b"id,voice_register" in resp.data
        assert b"P1" in resp.data

    def test_segments_csv_200(self, client):
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
            patch("app.api.report.ReportManager.get_report_v3", return_value=_make_report_v3()),
            patch("app.api.report.ReportManager.get_evidence_map", return_value=_make_evidence_map()),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=csv&table=segments")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        assert b"id,name" in resp.data
        assert b"S1" in resp.data

    def test_claims_csv_200(self, client):
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
            patch("app.api.report.ReportManager.get_report_v3", return_value=_make_report_v3()),
            patch("app.api.report.ReportManager.get_evidence_map", return_value=_make_evidence_map()),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=csv&table=claims")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        assert b"claim_id" in resp.data

    def test_404_unknown_report_id(self, client):
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=None),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=csv&table=personas")
        assert resp.status_code == 404

    def test_400_invalid_format_xml(self, client):
        with patch("app.api.report.validate_report_id", return_value=True):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=xml&table=personas")
        assert resp.status_code == 400

    def test_400_invalid_table(self, client):
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=csv&table=foo")
        assert resp.status_code == 400

    def test_content_disposition_header(self, client):
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
            patch("app.api.report.ReportManager.get_report_v3", return_value=_make_report_v3()),
            patch("app.api.report.ReportManager.get_evidence_map", return_value=_make_evidence_map()),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=csv&table=personas")
        cd = resp.headers.get("Content-Disposition", "")
        assert "attachment" in cd
        assert f"agora-report-{VALID_REPORT_ID}-personas.csv" in cd
