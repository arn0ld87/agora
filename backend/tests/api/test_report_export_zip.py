"""Tests für den ZIP-Bundle-Export-Endpoint.

Sub-Slice P4.3 — Refs PLAN.md §5.3

Abgedeckt:
- GET /api/report/<report_id>/export?format=zip → 200 application/zip, 6 Einträge
- personas.csv Header startet mit 'id,voice_register'
- Content-Disposition enthält 'bundle.zip'
- 404 wenn weder report-v3.md noch report-v3.json vorhanden
- 400 bei format=xml (bereits via CSV-Tests gedeckt, hier explizit wiederholt)
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import report_bp


VALID_REPORT_ID = "report_abcdef123456"

_REPORT_V3_MD_CONTENT = "# Report V3\n\nInhalt des Berichts."
_REPORT_V3_JSON_CONTENT = '{"schema_version": 3, "report_id": "report_abcdef123456"}'


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _make_mock_report():
    mock = MagicMock()
    mock.report_id = VALID_REPORT_ID
    mock.markdown_content = None
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
        "schema_version": 4,
        "report_id": VALID_REPORT_ID,
        "generated_at": "2026-05-10T12:00:00",
        "evidence_index": {},
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
    }


class TestZipExportEndpoint:
    def test_export_zip_returns_zip_with_six_entries(self, client):
        """Vollständiger ZIP-Download: 6 Einträge, korrekter MIME-Type, Dateiname."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
            patch("app.api.report.ReportManager._get_report_v3_path", return_value="/some/v3.json"),
            patch("app.api.report.ReportManager._get_report_v3_markdown_path", return_value="/some/v3.md"),
            patch("app.api.report.os.path.exists", return_value=True),
            patch("builtins.open", side_effect=_fake_open),
            patch("app.api.report.ReportManager.get_evidence_map", return_value=_make_evidence_map()),
            patch("app.api.report.ReportManager.get_report_v3", return_value=_make_report_v3()),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=zip")

        assert resp.status_code == 200, resp.data
        assert resp.content_type == "application/zip"
        cd = resp.headers.get("Content-Disposition", "")
        assert "attachment" in cd
        assert "bundle.zip" in cd

        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        names = zf.namelist()
        assert len(names) == 6, f"Erwartet 6 Einträge, erhalten: {names}"

        prefix = f"agora-report-{VALID_REPORT_ID}"
        expected = {
            f"{prefix}/report-v3.md",
            f"{prefix}/report-v3.json",
            f"{prefix}/evidence-map.json",
            f"{prefix}/personas.csv",
            f"{prefix}/segments.csv",
            f"{prefix}/claims.csv",
        }
        assert set(names) == expected

    def test_export_zip_personas_csv_header(self, client):
        """personas.csv im ZIP beginnt mit 'id,voice_register'."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
            patch("app.api.report.ReportManager._get_report_v3_path", return_value="/some/v3.json"),
            patch("app.api.report.ReportManager._get_report_v3_markdown_path", return_value="/some/v3.md"),
            patch("app.api.report.os.path.exists", return_value=True),
            patch("builtins.open", side_effect=_fake_open),
            patch("app.api.report.ReportManager.get_evidence_map", return_value=_make_evidence_map()),
            patch("app.api.report.ReportManager.get_report_v3", return_value=_make_report_v3()),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=zip")

        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        prefix = f"agora-report-{VALID_REPORT_ID}"
        personas_csv = zf.read(f"{prefix}/personas.csv").decode("utf-8")
        first_line = personas_csv.splitlines()[0]
        assert first_line.startswith("id,voice_register"), (
            f"Header passt nicht: {first_line!r}"
        )

    def test_export_zip_404_when_no_v3(self, client):
        """Wenn weder report-v3.md noch report-v3.json existiert → 404 report_not_finalised."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=_make_mock_report()),
            patch("app.api.report.ReportManager._get_report_v3_path", return_value="/nonexistent/v3.json"),
            patch("app.api.report.ReportManager._get_report_v3_markdown_path", return_value="/nonexistent/v3.md"),
            patch("app.api.report.os.path.exists", return_value=False),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=zip")

        assert resp.status_code == 404
        data = resp.get_json()
        assert data is not None
        assert "report_not_finalised" in str(data)

    def test_export_zip_invalid_format_xml(self, client):
        """format=xml gibt 400 zurück."""
        with patch("app.api.report.validate_report_id", return_value=True):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=xml")
        assert resp.status_code == 400

    def test_export_zip_404_unknown_report(self, client):
        """Unbekannter report_id gibt 404 zurück."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=None),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/export?format=zip")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeFile:
    """Context-Manager-kompatibler Fake-File für unittest.mock.patch('builtins.open')."""

    def __init__(self, content: str) -> None:
        import io as _io
        self._inner = _io.StringIO(content)

    def __enter__(self):
        return self._inner

    def __exit__(self, *_):
        pass

    def read(self) -> str:
        return self._inner.read()

    def __iter__(self):
        return iter(self._inner)


def _fake_open(path: str, *args, **kwargs):
    """Simuliert open() für gemockte Pfade in _build_zip_bundle."""
    if path == "/some/v3.md":
        return _FakeFile(_REPORT_V3_MD_CONTENT)
    if path == "/some/v3.json":
        return _FakeFile(_REPORT_V3_JSON_CONTENT)
    raise FileNotFoundError(f"Unexpected open: {path}")
