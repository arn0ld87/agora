"""Tests for optional ReportAgent web tools."""

from __future__ import annotations

import json

from app.services.settings_layer import SettingsService
from app.services.web_tools import WebToolsService


def test_web_tools_read_tavily_secret_from_settings_file(tmp_path, monkeypatch):
    service = SettingsService(instance_path=tmp_path / "settings.json")
    service.instance_path.parent.mkdir(parents=True, exist_ok=True)
    service.instance_path.write_text(
        json.dumps({
            "ENABLE_WEB_TOOLS": True,
            "TAVILY_API_KEY": "tvly-test-key",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.settings_layer.get_default_service",
        lambda: service,
    )

    tools = WebToolsService()

    assert tools.api_key == "tvly-test-key"
    assert tools.is_available() is True


def test_web_tools_disabled_when_flag_false_even_with_key(tmp_path, monkeypatch):
    service = SettingsService(instance_path=tmp_path / "settings.json")
    service.instance_path.parent.mkdir(parents=True, exist_ok=True)
    service.instance_path.write_text(
        json.dumps({
            "ENABLE_WEB_TOOLS": False,
            "TAVILY_API_KEY": "tvly-test-key",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.settings_layer.get_default_service",
        lambda: service,
    )

    assert WebToolsService().is_available() is False
