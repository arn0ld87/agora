"""Tests für Track 3a/3b: Section-Loop-Fallback und ValidationError-Handling
in :mod:`app.services.report_agent.workflow`.

Vor Track 3 hat ein 401-unauthorized-Loop bei einzelnen Sections eine
Pydantic-``ValidationError`` ausgelöst (``sections.10.title missing``),
weil der Section-Loop leere/exception-werfende LLM-Calls unverändert
weiterreichte. Nach dem Fix:

  * :func:`_safe_generate_section_react` fängt Exceptions und leere
    Responses und liefert einen sichtbaren Fallback-Text.
  * ``ReportV3.model_validate`` ist mit ``try/except ValidationError``
    umrahmt und schreibt eine User-Message in ``report.error``.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.report_agent import workflow as workflow_mod
from app.services.report_agent.workflow import (
    SECTION_FALLBACK_BODY,
    SECTION_FALLBACK_TITLE,
    _safe_generate_section_react,
)


def _make_section(title: str = "Stakeholder-Analyse"):
    section = SimpleNamespace()
    section.title = title
    section.content = ""
    section.metadata = None
    return section


class TestSafeGenerateSectionReact:
    def test_propagates_valid_result_unchanged(self, monkeypatch):
        monkeypatch.setattr(
            workflow_mod,
            "generate_section_react",
            lambda *a, **kw: "## Echte Section\n\nMit reichlich Inhalt.",
        )
        result = _safe_generate_section_react(
            agent=MagicMock(),
            section=_make_section(),
            outline=MagicMock(),
            previous_sections=[],
            progress_callback=None,
            section_index=1,
            report_id="report_abc123",
        )
        assert result == "## Echte Section\n\nMit reichlich Inhalt."

    def test_returns_fallback_on_exception(self, monkeypatch):
        def _boom(*_a, **_kw):
            raise RuntimeError("simulated 401 unauthorized")

        monkeypatch.setattr(workflow_mod, "generate_section_react", _boom)
        result = _safe_generate_section_react(
            agent=MagicMock(),
            section=_make_section("Risiko-Matrix"),
            outline=MagicMock(),
            previous_sections=[],
            progress_callback=None,
            section_index=7,
            report_id="report_xyz",
        )
        # Pipeline darf nicht crashen: Fallback-Content trägt die User-Message
        # und die Identifier zur Diagnose.
        assert "report_xyz" in result
        assert "section_index=7" in result
        assert "LLM-Aufruf" in result

    @pytest.mark.parametrize("empty_value", ["", "   \n\t  ", None])
    def test_returns_fallback_on_empty_or_none(self, monkeypatch, empty_value):
        monkeypatch.setattr(
            workflow_mod,
            "generate_section_react",
            lambda *a, **kw: empty_value,
        )
        result = _safe_generate_section_react(
            agent=MagicMock(),
            section=_make_section(),
            outline=MagicMock(),
            previous_sections=[],
            progress_callback=None,
            section_index=3,
            report_id="report_abc",
        )
        assert "report_abc" in result
        assert "3" in result

    def test_returns_fallback_on_non_string_return_value(self, monkeypatch):
        # generate_section_react ist als ``-> str`` typisiert, aber wenn ein
        # zukünftiger Bug ein dict/int zurückgibt, soll der Wrapper trotzdem
        # ehrlich fallen, nicht still die Pipeline mit einem Sentinel füttern.
        monkeypatch.setattr(
            workflow_mod,
            "generate_section_react",
            lambda *a, **kw: {"unexpected": "dict"},
        )
        result = _safe_generate_section_react(
            agent=MagicMock(),
            section=_make_section(),
            outline=MagicMock(),
            previous_sections=[],
            progress_callback=None,
            section_index=1,
            report_id="report_dict",
        )
        assert "report_dict" in result

    def test_fallback_message_mentions_settings_recovery_path(self, monkeypatch):
        """User soll im Frontend lesen können, wo er den fehlenden Key setzt."""
        monkeypatch.setattr(
            workflow_mod, "generate_section_react", lambda *a, **kw: None
        )
        result = _safe_generate_section_react(
            agent=MagicMock(),
            section=_make_section(),
            outline=MagicMock(),
            previous_sections=[],
            progress_callback=None,
            section_index=1,
            report_id="report_abc",
        )
        assert "Settings" in result
        assert "LLM-Provider" in result

    def test_fallback_constants_exposed(self):
        """``SECTION_FALLBACK_BODY`` und ``SECTION_FALLBACK_TITLE`` sind Public-API
        (Worker/Frontend können daran erkennen, ob eine Section degraded ist)."""
        assert "{report_id}" in SECTION_FALLBACK_BODY
        assert "{section_index}" in SECTION_FALLBACK_BODY
        assert SECTION_FALLBACK_TITLE == "Section nicht generiert (LLM-Fehler)"
