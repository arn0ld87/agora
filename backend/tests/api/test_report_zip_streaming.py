"""Tests für ZIP-Bundle-Streaming + Size-Cap.

Baustein D — Hardening PR 5
- ≤ 50 MB: bytes-Response (BytesIO-Pfad)
- > 50 MB und ≤ 500 MB: Streaming-Response
- > 500 MB: 413
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import report_bp
from app.api.report import _ZIP_HARD_CAP_BYTES, _ZIP_STREAM_THRESHOLD_BYTES


VALID_REPORT_ID = "report_abcdef123456"
_50_MB = 50 * 1024 * 1024
_100_MB = 100 * 1024 * 1024
_600_MB = 600 * 1024 * 1024


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _make_mock_report():
    mock = MagicMock()
    mock.report_id = VALID_REPORT_ID
    mock.markdown_content = "# Report"
    return mock


class TestZipStreamingConstants:
    def test_threshold_is_50mb(self):
        assert _ZIP_STREAM_THRESHOLD_BYTES == _50_MB

    def test_hard_cap_is_500mb(self):
        assert _ZIP_HARD_CAP_BYTES == 500 * 1024 * 1024


class TestZipUnder50MB:
    def test_zip_under_50mb_returns_bytes_response(self, client):
        """Kleine ZIP-Größe → BytesIO-Pfad, keine Streaming-Header."""
        fake_zip_bytes = b"PK\x03\x04" + b"\x00" * 100  # Minimal ZIP-Header Dummy

        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_report",
                return_value=_make_mock_report(),
            ),
            patch(
                "app.api.report.ReportManager._get_report_v3_path",
                return_value="/nonexistent/v3.json",
            ),
            patch("app.api.report.os.path.exists", return_value=False),
            patch(
                "app.api.report._estimate_zip_size",
                return_value=1 * 1024 * 1024,  # 1 MB
            ),
            patch(
                "app.api.report._build_zip_bundle",
                return_value=fake_zip_bytes,
            ),
        ):
            resp = client.get(
                f"/api/report/{VALID_REPORT_ID}/export?format=zip"
            )

        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        # Bei BytesIO-Pfad kein chunked Transfer
        te = resp.headers.get("Transfer-Encoding", "")
        assert te != "chunked"


class TestZipOver50MB:
    def test_zip_over_50mb_uses_streaming_response(self, client):
        """100 MB Schätzung → Streaming-Generator-Pfad."""

        def _fake_stream_gen():
            yield b"PK\x03\x04"
            yield b"\x00" * 1024

        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_report",
                return_value=_make_mock_report(),
            ),
            patch(
                "app.api.report.ReportManager._get_report_v3_path",
                return_value="/nonexistent/v3.json",
            ),
            patch("app.api.report.os.path.exists", return_value=False),
            patch(
                "app.api.report._estimate_zip_size",
                return_value=_100_MB,
            ),
            patch(
                "app.api.report._stream_zip_bundle",
                return_value=_fake_stream_gen(),
            ),
        ):
            resp = client.get(
                f"/api/report/{VALID_REPORT_ID}/export?format=zip"
            )

        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        # Streaming: response generiert Daten aus Generator
        assert len(resp.data) > 0


class TestZipOver500MB:
    def test_zip_over_500mb_returns_413(self, client):
        """600 MB Schätzung überschreitet Hard-Cap → 413."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_report",
                return_value=_make_mock_report(),
            ),
            patch(
                "app.api.report.ReportManager._get_report_v3_path",
                return_value="/nonexistent/v3.json",
            ),
            patch("app.api.report.os.path.exists", return_value=False),
            patch(
                "app.api.report._estimate_zip_size",
                return_value=_600_MB,
            ),
        ):
            resp = client.get(
                f"/api/report/{VALID_REPORT_ID}/export?format=zip"
            )

        assert resp.status_code == 413
