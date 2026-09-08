"""Regressionstest: docs/backup-restore.md nennt den echten Reports-Pfad.

Defekt (Tech-Review 2026-09-07, Slice 8): Reports werden unter
``Config.UPLOAD_FOLDER/reports`` geschrieben (``backend/uploads/reports/``,
siehe ``report_logger.py``, ``artifact_locator.py``, ``report_agent/manager.py``).
``docs/backup-restore.md`` sprach an fünf Stellen fälschlich von
``./backend/reports/`` — einem Verzeichnis, das es nie gab.
"""

from __future__ import annotations

from pathlib import Path

BACKUP_RESTORE_MD = Path(__file__).resolve().parents[2] / "docs" / "backup-restore.md"


def test_backup_restore_doc_does_not_reference_nonexistent_reports_dir() -> None:
    text = BACKUP_RESTORE_MD.read_text(encoding="utf-8")
    assert "backend/reports" not in text, (
        "docs/backup-restore.md referenziert noch das nie existierende "
        "'backend/reports/' — der echte Pfad ist 'backend/uploads/reports/'."
    )


def test_backup_restore_doc_mentions_real_reports_path() -> None:
    text = BACKUP_RESTORE_MD.read_text(encoding="utf-8")
    assert "backend/uploads/reports/" in text
