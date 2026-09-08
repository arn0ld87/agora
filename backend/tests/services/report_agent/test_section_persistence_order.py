"""Regression-Tests für Sektions-Persistenz-Reihenfolge (B6).

Die Sektionen werden atomar geschrieben: Evidence zuerst, dann Markdown.
Der Markdown-Datei ist der Commit-Marker — existiert sie, existiert auch die Evidence.
"""

import errno
import json
import os
import stat as stat_module
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

    def test_process_section_raises_when_orphan_removal_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex-Review PR #1475, Runde 2, Finding 1: Ein ``OSError`` beim
        Entfernen der verwaisten Markdown-Datei propagiert, BEVOR neue
        Evidence geschrieben wird. Der zuvor geschluckte Fehler hätte die
        Waise liegen lassen, während trotzdem neue Evidence persistiert
        worden wäre — genau die Inkonsistenz, die dieser Slice beseitigt.
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

        def _failing_remove(_path: str) -> None:
            raise OSError("Permission denied (simulated)")

        monkeypatch.setattr(
            "app.services.report_agent.section_pipeline.os.remove",
            _failing_remove,
        )

        with pytest.raises(OSError):
            process_section(agent, section, ctx, section_index=1)

        # Weder neue Inhaltsgenerierung noch neue Evidence noch neues
        # Markdown — der Fehler bricht ab, bevor irgendein Folgeschritt läuft.
        generate_section.assert_not_called()
        assert evidence_calls == []
        assert fake_manager.save_section_calls == 0
        # Die Waise liegt weiterhin unverändert auf der Platte.
        assert section_path.exists()
        assert "OLD STALE CONTENT" in section_path.read_text(encoding='utf-8')

    def test_process_section_treats_missing_orphan_file_as_already_removed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CodeRabbit-Review PR #1475, Runde 3, Finding 2: verschwindet die
        Waise zwischen ``os.path.exists`` und ``os.remove`` (TOCTOU, z. B.
        weil der DELETE-Endpunkt den Report-Ordner per ``shutil.rmtree``
        gelöscht hat), ist der gewünschte Endzustand bereits erreicht — die
        Sektion muss trotzdem sauber regeneriert werden, statt an einer
        ``FileNotFoundError`` zu scheitern.
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

        original_remove = os.remove

        def _racy_remove(path: str) -> None:
            # Simuliert einen Konkurrenzprozess (z. B. das DELETE-Endpunkt
            # ``shutil.rmtree``), der die Waise zwischen der
            # ``os.path.exists``-Prüfung und diesem Aufruf bereits entfernt
            # hat — der Effekt (Datei weg) tritt real ein, os.remove sieht
            # aber trotzdem eine bereits verschwundene Datei.
            if os.path.exists(path):
                original_remove(path)
            raise FileNotFoundError(
                errno.ENOENT, "No such file or directory (simulated TOCTOU)", path
            )

        monkeypatch.setattr(
            "app.services.report_agent.section_pipeline.os.remove",
            _racy_remove,
        )

        result = process_section(agent, section, ctx, section_index=1)

        assert result.restored is False
        generate_section.assert_called_once()
        assert len(evidence_calls) == 1
        assert fake_manager.save_section_calls == 1
        assert "NEW GENERATED CONTENT" in section_path.read_text(encoding='utf-8')


class TestParentDirectoryFsync:
    """CodeRabbit-Review PR #1475, Runde 2, Finding 3: nach ``os.replace``
    wird das Elternverzeichnis gefsynct, damit der Rename einen Stromausfall
    übersteht — ohne dabei auf Plattformen ohne Verzeichnis-fsync zu werfen.
    """

    def test_write_json_atomic_fsyncs_parent_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "evidence_map.json"
        fsync_calls: list[int] = []
        fsync_call_is_dir: list[bool] = []
        original_fsync = os.fsync

        def _tracking_fsync(fd: int) -> None:
            fsync_calls.append(fd)
            fsync_call_is_dir.append(stat_module.S_ISDIR(os.fstat(fd).st_mode))
            original_fsync(fd)

        monkeypatch.setattr(
            "app.services.report_agent.storage.os.fsync", _tracking_fsync
        )

        write_json_atomic(str(target), {"a": 1})

        assert target.exists()
        # Ein fsync für die Temp-Datei, ein weiterer für das Verzeichnis.
        assert len(fsync_calls) == 2
        # CodeRabbit-Review PR #1475, Runde 3, Finding 3: die Aufrufanzahl
        # allein deckt eine Regression mit zwei Datei-Deskriptoren nicht
        # auf — mindestens einer der gefsyncten Deskriptoren muss ein
        # Verzeichnis sein.
        assert any(fsync_call_is_dir), (
            "Kein gefsyncter Deskriptor war ein Verzeichnis, erhalten: "
            f"{fsync_call_is_dir}"
        )

    def test_write_section_markdown_fsyncs_parent_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "section_01.md"
        fsync_calls: list[int] = []
        fsync_call_is_dir: list[bool] = []
        original_fsync = os.fsync

        def _tracking_fsync(fd: int) -> None:
            fsync_calls.append(fd)
            fsync_call_is_dir.append(stat_module.S_ISDIR(os.fstat(fd).st_mode))
            original_fsync(fd)

        monkeypatch.setattr(
            "app.services.report_agent.storage.os.fsync", _tracking_fsync
        )

        write_section_markdown(str(target), "Title", "Content")

        assert target.exists()
        assert len(fsync_calls) == 2
        assert any(fsync_call_is_dir), (
            "Kein gefsyncter Deskriptor war ein Verzeichnis, erhalten: "
            f"{fsync_call_is_dir}"
        )

    def test_write_json_atomic_degrades_when_directory_fsync_unsupported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ein Verzeichnis-``fsync``, das mit einem "nicht unterstützt"-
        errno (z. B. ``EINVAL`` auf Plattformen ohne Verzeichnis-fsync)
        scheitert, darf den erfolgreichen Schreibvorgang nicht nachträglich
        als Fehler melden."""
        target = tmp_path / "evidence_map.json"
        original_fsync = os.fsync
        dir_fsync_attempted = False

        def _failing_dir_fsync(fd: int) -> None:
            nonlocal dir_fsync_attempted
            # Die Temp-Datei bekommt echtes fsync, das Verzeichnis-fsync
            # (danach, gleicher fd-Namespace) schlägt mit einem
            # "nicht unterstützt"-errno fehl.
            try:
                st = os.fstat(fd)
            except OSError:
                original_fsync(fd)
                return

            if stat_module.S_ISDIR(st.st_mode):
                dir_fsync_attempted = True
                raise OSError(
                    errno.EINVAL, "Verzeichnis-fsync nicht unterstützt (simuliert)"
                )
            original_fsync(fd)

        monkeypatch.setattr(
            "app.services.report_agent.storage.os.fsync", _failing_dir_fsync
        )

        write_json_atomic(str(target), {"a": 1})  # darf nicht werfen

        assert target.exists()
        with open(target, encoding="utf-8") as fh:
            assert json.load(fh) == {"a": 1}
        # Finding 3: ohne diese Assertion würde ein Mock, der nie am
        # Verzeichnis-Deskriptor scheitert, unbemerkt denselben Testnamen
        # tragen und trotzdem grün bleiben.
        assert dir_fsync_attempted, "Verzeichnis-fsync wurde nie versucht"

    def test_write_json_atomic_propagates_real_directory_fsync_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex-Review PR #1475, Runde 3, Finding 1: ein echter Storage-
        Fehler (hier ``ENOSPC``) beim Verzeichnis-fsync darf NICHT
        stillschweigend verschluckt werden — sonst meldet
        ``write_json_atomic`` einen Write als erfolgreich, dessen
        Commit-Marker-Rename einen Absturz danach nicht übersteht."""
        target = tmp_path / "evidence_map.json"
        original_fsync = os.fsync

        def _failing_dir_fsync(fd: int) -> None:
            try:
                st = os.fstat(fd)
            except OSError:
                original_fsync(fd)
                return

            if stat_module.S_ISDIR(st.st_mode):
                raise OSError(errno.ENOSPC, "No space left on device (simulated)")
            original_fsync(fd)

        monkeypatch.setattr(
            "app.services.report_agent.storage.os.fsync", _failing_dir_fsync
        )

        with pytest.raises(OSError) as exc_info:
            write_json_atomic(str(target), {"a": 1})

        assert exc_info.value.errno == errno.ENOSPC

    @pytest.mark.skipif(
        os.name == "nt", reason="Auf Windows ist EACCES beim Verzeichnis-Handle erwartet."
    )
    def test_write_json_atomic_propagates_directory_permission_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Codex-Review PR #1475, Runde 4: ``EACCES`` heisst auf POSIX
        Zugriffsverweigerung, nicht "Verzeichnis-fsync nicht unterstuetzt".

        Ein nur schreib-/ausfuehrbares Report-Verzeichnis laesst ``os.replace``
        zu, aber ``os.open(dir, O_RDONLY)`` scheitert mit ``EACCES`` — waere
        das in der Degradations-Liste, meldete ``write_json_atomic`` den Write
        faelschlich als dauerhaft."""
        target = tmp_path / "evidence_map.json"
        real_open = os.open

        def _denying_open(path, flags, *args, **kwargs):
            if os.path.isdir(path) and flags == os.O_RDONLY:
                raise OSError(errno.EACCES, "Permission denied (simuliert)")
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(
            "app.services.report_agent.storage.os.open", _denying_open
        )

        with pytest.raises(OSError) as exc_info:
            write_json_atomic(str(target), {"a": 1})

        assert exc_info.value.errno == errno.EACCES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
