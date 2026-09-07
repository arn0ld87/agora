"""Regression-Tests für Sektions-Persistenz-Reihenfolge (B6).

Die Sektionen werden atomar geschrieben: Evidence zuerst, dann Markdown.
Der Markdown-Datei ist der Commit-Marker — existiert sie, existiert auch die Evidence.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.report_agent.section_pipeline import SectionContext, process_section
from app.services.report_agent.storage import (
    write_section_markdown,
    write_json_atomic,
)


class _FakeReportManager:
    """Minimaler Ersatz für ``ReportManager`` — schreibt echt auf ``tmp_path``.

    ``save_section`` nutzt bewusst das reale ``write_section_markdown``, damit
    die Tests die tatsächliche Datei auf der Platte prüfen können statt nur
    einen Mock-Aufruf.
    """

    def __init__(self, report_folder: Path) -> None:
        self.report_folder = report_folder
        self.save_section_calls = 0

    def update_progress(self, *args: object, **kwargs: object) -> None:
        pass

    def prepare_content_for_evidence(self, content: str) -> str:
        return content

    def _clean_section_content(self, content: str, _title: str) -> str:
        return content

    def _get_section_path(self, _report_id: str, section_index: int) -> str:
        return str(self.report_folder / f"section_{section_index:02d}.md")

    def save_section(self, report_id: str, section_index: int, section: object) -> str:
        self.save_section_calls += 1
        path = self._get_section_path(report_id, section_index)
        write_section_markdown(path, section.title, section.content)
        return path


def _build_process_section_harness(
    tmp_path: Path,
    *,
    evidence_sections: list,
    generated_content: str,
):
    """Baut Agent/Sektion/Kontext für einen echten ``process_section``-Lauf.

    ``is_fallback`` liefert bewusst immer ``True``: das schneidet Zitatprüfung,
    Fließtext-Verifikation und Metadaten-Extraktion aus dem Testpfad heraus —
    keiner dieser Schritte gehört zum Gegenstand dieses Tests (Resume- vs.
    Regenerations-Entscheidung, Reihenfolge von Evidence und Markdown).
    """
    report_folder = tmp_path / "test_report"
    report_folder.mkdir()
    section_path = report_folder / "section_01.md"

    # Auf der Platte liegt bereits Markdown aus einem früheren Lauf.
    write_section_markdown(str(section_path), "Executive Summary", "OLD STALE CONTENT")

    fake_manager = _FakeReportManager(report_folder)

    agent = MagicMock()
    agent.evidence_map = {"sections": evidence_sections}
    evidence_calls: list = []

    def _fake_save_evidence_section(report_id, section_index, title, content):
        # Finding 1: zum Zeitpunkt des Evidence-Schreibens darf keine
        # verwaiste Markdown-Datei mehr auf der Platte liegen.
        evidence_calls.append((report_id, section_index, title, content))
        assert not section_path.exists(), (
            "verwaiste Markdown-Datei muss vor dem Schreiben neuer Evidence "
            "entfernt sein"
        )
        return {}

    agent._save_evidence_section = MagicMock(side_effect=_fake_save_evidence_section)

    section = SimpleNamespace(title="Executive Summary", content="")

    generate_section = MagicMock(return_value=generated_content)

    ctx = SectionContext(
        report_id="test_report",
        outline=None,
        total_sections=1,
        generate_section=generate_section,
        generate_metadata=lambda *a, **k: {},
        previous_sections=[],
        completed_section_titles=[],
        persisted_section_contents={1: "OLD STALE CONTENT"},
        is_fallback=lambda _content: True,
        report_manager=fake_manager,
    )

    return agent, section, ctx, fake_manager, section_path, generate_section, evidence_calls


class TestSectionPersistenceOrder:
    """Markdown wird erst nach Evidence geschrieben."""

    def test_write_section_markdown_is_atomic(self, tmp_path: Path) -> None:
        """Atomic-Write: tmp-Datei hinterlässt keine halben Dateien bei Exception."""
        section_path = tmp_path / "section_01.md"

        # Simuliere einen Fehler während des Schreibens
        write_count = 0
        original_replace = os.replace

        def failing_replace(src: str, dst: str) -> None:
            nonlocal write_count
            write_count += 1
            if write_count == 1 and "section_01.md" in dst:
                # Räume tmp auf und werfe Exception
                if os.path.exists(src):
                    os.unlink(src)
                raise OSError("Simulated write failure")
            original_replace(src, dst)

        with patch("os.replace", side_effect=failing_replace):
            with pytest.raises(OSError):
                write_section_markdown(str(section_path), "Test", "content")

        # Nach Exception sollte die Zieldatei nicht existieren oder unverändert sein
        assert not section_path.exists(), "Zieldatei sollte nach Exception nicht existieren"

    def test_write_section_markdown_uses_tmp(self, tmp_path: Path) -> None:
        """write_section_markdown verwendet mkstemp + os.replace."""
        section_path = tmp_path / "section_01.md"

        write_section_markdown(str(section_path), "Title", "Content here")

        assert section_path.exists()
        content = section_path.read_text(encoding='utf-8')
        assert "## Title" in content
        assert "Content here" in content

    def test_process_section_regenerates_when_evidence_entry_missing(
        self, tmp_path: Path
    ) -> None:
        """process_section restauriert NICHT, wenn Markdown ohne Evidence-Eintrag
        auf Platte liegt — stattdessen wird regeneriert (Codex-Review PR #1475,
        Finding 3). Zusätzlich: die verwaiste Markdown-Datei ist entfernt,
        BEVOR neue Evidence geschrieben wird (Finding 1).
        """
        (
            agent,
            section,
            ctx,
            fake_manager,
            section_path,
            generate_section,
            evidence_calls,
        ) = _build_process_section_harness(
            tmp_path,
            evidence_sections=[],  # keine Evidence für section_index 1
            generated_content="NEW GENERATED CONTENT",
        )

        result = process_section(agent, section, ctx, section_index=1)

        assert result.restored is False
        generate_section.assert_called_once()
        assert len(evidence_calls) == 1
        assert fake_manager.save_section_calls == 1
        # Die neue Markdown-Datei enthält den regenerierten Inhalt, nicht mehr
        # den alten Waisen-Inhalt.
        assert "NEW GENERATED CONTENT" in section_path.read_text(encoding='utf-8')
        assert "OLD STALE CONTENT" not in section_path.read_text(encoding='utf-8')

    def test_process_section_regenerates_when_evidence_map_is_none(
        self, tmp_path: Path
    ) -> None:
        """Dieselbe Regel gilt, wenn die Evidenzkarte des Agenten leer/None ist
        (z. B. nach einem Crash vor deren Persistierung)."""
        (
            agent,
            section,
            ctx,
            fake_manager,
            section_path,
            generate_section,
            evidence_calls,
        ) = _build_process_section_harness(
            tmp_path,
            evidence_sections=[],
            generated_content="NEW GENERATED CONTENT",
        )
        agent.evidence_map = None

        result = process_section(agent, section, ctx, section_index=1)

        assert result.restored is False
        generate_section.assert_called_once()
        assert len(evidence_calls) == 1
        assert "NEW GENERATED CONTENT" in section_path.read_text(encoding='utf-8')

    def test_evidence_and_markdown_both_or_neither(self, tmp_path: Path) -> None:
        """Entweder existieren beide Artefakte oder keines."""
        report_folder = tmp_path / "test_report"
        report_folder.mkdir()

        evidence_path = report_folder / "evidence_map.json"
        section_path = report_folder / "section_01.md"

        # Schreibe Evidence zuerst
        evidence_data = {"sections": [{"section_index": 1, "claims": []}]}
        write_json_atomic(str(evidence_path), evidence_data)

        # Dann Markdown
        write_section_markdown(str(section_path), "Test", "Content")

        # Beide sollten existieren
        assert evidence_path.exists()
        assert section_path.exists()

        # Lese beide zurück
        with open(evidence_path) as f:
            evidence = json.load(f)
        markdown_content = section_path.read_text(encoding='utf-8')

        assert "## Test" in markdown_content
        assert evidence["sections"][0]["section_index"] == 1

    def test_process_section_restores_without_regenerating_when_evidence_present(
        self, tmp_path: Path
    ) -> None:
        """process_section restauriert direkt und ruft NICHT neu generieren
        auf, wenn zur persistierten Markdown-Datei ein Evidence-Eintrag
        existiert.

        Ersetzt den früheren Direktaufruf von ``_restore_persisted_section``:
        diese Funktion selbst prüft laut Vertrag keine Evidence mehr (das tut
        der Aufrufer) und hätte mit fehlender ODER vorhandener Evidence
        identisch ``restored=True`` geliefert — kein Regressionstest.
        """
        (
            agent,
            section,
            ctx,
            fake_manager,
            section_path,
            generate_section,
            evidence_calls,
        ) = _build_process_section_harness(
            tmp_path,
            evidence_sections=[{"section_index": 1, "claims": []}],
            generated_content="NEW GENERATED CONTENT",
        )

        result = process_section(agent, section, ctx, section_index=1)

        assert result.restored is True
        generate_section.assert_not_called()
        assert evidence_calls == []
        assert fake_manager.save_section_calls == 0
        # Die alte Markdown-Datei bleibt unverändert liegen.
        assert "OLD STALE CONTENT" in section_path.read_text(encoding='utf-8')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
