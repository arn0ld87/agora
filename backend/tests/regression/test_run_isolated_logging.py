"""Ein Report-Artefakt enthält nur den eigenen Lauf.

Die ``console_log.txt`` des Referenzlaufs ``report_cc2ef45da5e9`` enthielt
gleichzeitig Einträge zu ``report_e5734b31241d``. Die Ursache: der
``ReportConsoleLogger`` hängt seinen FileHandler an die globalen Logger
``agora.report_agent`` und ``agora.graph_tools``. Laufen zwei Reports parallel,
hängen beide Handler dort, und jede Zeile landet in beiden Dateien.

Für eine Forensik ist ein Log, das fremde Läufe mitschreibt, schlechter als
keins: man kann ihm nicht mehr trauen.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.services.report_logger import (
    ReportConsoleLogger,
    ReportScopeFilter,
    current_report_id,
)


@pytest.fixture
def report_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    return tmp_path


def _console_log(root: Path, report_id: str) -> str:
    path = root / "reports" / report_id / "console_log.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- Der Filter selbst ------------------------------------------------------


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        "agora.report_agent", logging.INFO, __file__, 1, message, None, None
    )


def test_a_record_from_another_report_is_dropped(report_root: Path):
    logger = ReportConsoleLogger("report_own")
    try:
        assert current_report_id() == "report_own"
        assert ReportScopeFilter("report_other").filter(_record("x")) is False
    finally:
        logger.close()


def test_a_record_from_the_own_report_passes(report_root: Path):
    logger = ReportConsoleLogger("report_own")
    try:
        assert ReportScopeFilter("report_own").filter(_record("x")) is True
    finally:
        logger.close()


def test_an_unassigned_record_passes():
    """``ThreadPoolExecutor.submit`` kopiert den Kontext nicht.

    Ein Worker-Thread ohne gesetzten Kontext würde sonst still aus dem Log
    fallen. Unscharf ist besser als abwesend — falsch wäre nur ein *fremder*
    Eintrag.
    """
    assert ReportScopeFilter("report_own").filter(_record("x")) is True


def test_the_scope_is_released_after_close(report_root: Path):
    ReportConsoleLogger("report_own").close()

    assert current_report_id() == ""


# --- Zwei parallele Reports -------------------------------------------------


def test_two_parallel_reports_do_not_write_into_each_others_log(report_root: Path):
    """Der Regressionstest aus der Spezifikation."""
    agent_logger = logging.getLogger("agora.report_agent")

    first = ReportConsoleLogger("report_aaaaaaaaaaaa")
    second = ReportConsoleLogger("report_bbbbbbbbbbbb")
    try:
        # Der zweite Logger hält den Kontext — er wurde zuletzt gesetzt.
        agent_logger.info("Meldung aus dem zweiten Lauf")
    finally:
        second.close()
        first.close()

    assert "Meldung aus dem zweiten Lauf" in _console_log(
        report_root, "report_bbbbbbbbbbbb"
    )
    assert "Meldung aus dem zweiten Lauf" not in _console_log(
        report_root, "report_aaaaaaaaaaaa"
    )


def test_a_single_report_still_captures_its_own_logs(report_root: Path):
    """Die Isolation darf das Log nicht leerräumen."""
    logger = ReportConsoleLogger("report_solo00000000")
    try:
        logging.getLogger("agora.report_agent").info("Abschnitt 1 beginnt")
        logging.getLogger("agora.graph_tools").info("Graph-Abfrage läuft")
    finally:
        logger.close()

    content = _console_log(report_root, "report_solo00000000")
    assert "Abschnitt 1 beginnt" in content
    assert "Graph-Abfrage läuft" in content


def test_no_foreign_report_id_appears_in_an_exported_artifact(report_root: Path):
    """Die Invariante, an der der Referenzlauf scheiterte."""
    agent_logger = logging.getLogger("agora.report_agent")

    first = ReportConsoleLogger("report_cc2ef45da5e9")
    second = ReportConsoleLogger("report_e5734b31241d")
    try:
        agent_logger.info("Bericht report_e5734b31241d: Abschnitt fertig")
    finally:
        second.close()
        first.close()

    assert "report_e5734b31241d" not in _console_log(report_root, "report_cc2ef45da5e9")
