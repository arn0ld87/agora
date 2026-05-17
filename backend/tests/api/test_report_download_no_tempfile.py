"""Tests für download_report ohne Tempfile-Leak.

Baustein A — Hardening PR 5
Stellt sicher, dass bei fehlendem Markdown-Dateipfad kein NamedTemporaryFile
angelegt wird, sondern ein direktes flask.Response aus markdown_content.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import report_bp


VALID_REPORT_ID = "report_abcdef123456"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _make_mock_report(content: str = "# Inhalt\n\nBericht."):
    mock = MagicMock()
    mock.report_id = VALID_REPORT_ID
    mock.markdown_content = content
    return mock


class TestDownloadReportNoTempfile:
    def test_download_report_streams_markdown_content_when_file_missing(self, client):
        """Wenn md_path nicht existiert, liefert der Endpoint 200 mit markdown_content."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_report",
                return_value=_make_mock_report("# Test\n\nInhalt."),
            ),
            patch(
                "app.api.report.ReportManager._get_report_markdown_path",
                return_value="/nonexistent/path/report.md",
            ),
            patch("app.api.report.os.path.exists", return_value=False),
        ):
            resp = client.get(
                f"/api/report/{VALID_REPORT_ID}/download",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200
        assert b"# Test" in resp.data
        cd = resp.headers.get("Content-Disposition", "")
        assert f"{VALID_REPORT_ID}.md" in cd
        assert "attachment" in cd

    def test_download_report_uses_send_file_when_path_exists(self, client, tmp_path):
        """Wenn md_path existiert, wird send_file aufgerufen (kein markdown_content im Body)."""
        md_file = tmp_path / f"{VALID_REPORT_ID}.md"
        md_file.write_text("# Gespeicherter Bericht")

        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_report",
                return_value=_make_mock_report("# Unterschiedlicher Inhalt"),
            ),
            patch(
                "app.api.report.ReportManager._get_report_markdown_path",
                return_value=str(md_file),
            ),
        ):
            resp = client.get(
                f"/api/report/{VALID_REPORT_ID}/download",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200
        assert b"# Gespeicherter Bericht" in resp.data
        # markdown_content des Mocks ("# Unterschiedlicher Inhalt") wurde NICHT geliefert
        assert b"# Unterschiedlicher Inhalt" not in resp.data

    def test_download_report_does_not_create_tempfile(self, client):
        """Im File-Missing-Branch wird NamedTemporaryFile NICHT aufgerufen."""
        tempfile_spy = MagicMock()

        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_report",
                return_value=_make_mock_report("# Kein Tempfile bitte"),
            ),
            patch(
                "app.api.report.ReportManager._get_report_markdown_path",
                return_value="/nonexistent/path/report.md",
            ),
            patch("app.api.report.os.path.exists", return_value=False),
            patch("tempfile.NamedTemporaryFile", tempfile_spy),
        ):
            resp = client.get(
                f"/api/report/{VALID_REPORT_ID}/download",
                headers={"Authorization": "Bearer dummy"},
            )

        assert resp.status_code == 200
        tempfile_spy.assert_not_called()

    def test_download_report_404_when_no_report(self, client):
        """404 wenn report nicht gefunden."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch("app.api.report.ReportManager.get_report", return_value=None),
        ):
            resp = client.get(
                f"/api/report/{VALID_REPORT_ID}/download",
                headers={"Authorization": "Bearer dummy"},
            )
        assert resp.status_code == 404
