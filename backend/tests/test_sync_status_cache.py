"""Cache-Verhalten von ``scripts/sync-status.sh``.

Die Backend-Testanzahl in ``docs/STATUS.md`` kostet einen vollständigen
``pytest --collect-only``-Lauf — auf einer Entwicklermaschine Minuten. Das
Skript speichert die Zahl deshalb zwischen und misst nur neu, wenn eine
Python-Datei unter ``backend/`` oder die pytest-Konfiguration jünger ist als
der Cache.

Bricht diese Invalidierung, veraltet ``STATUS.md`` still — der teure Lauf würde
schlicht nie wieder stattfinden. Diese Tests nageln beide Richtungen fest.

Sie kommen ohne den teuren Collect aus: mit einem PATH ohne ``uv`` kann das
Skript gar nicht messen und meldet im ``--check``-Modus Exit-Code 2
(„Messfehler"). Ein Cache-Treffer liefert dagegen 0 oder 1. Der Exit-Code
verrät damit, welchen Zweig das Skript genommen hat.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sync-status.sh"
CACHE_FILE = REPO_ROOT / "backend" / ".cache" / "sync-status" / "backend-tests-collected"
STATUS_FILE = REPO_ROOT / "docs" / "STATUS.md"

MEASUREMENT_FAILED = 2


def _run_check_without_uv(
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """``--check`` mit einem PATH ohne ``uv``.

    Ohne ``uv`` ist eine Messung unmöglich. Exit 2 heißt deshalb „der Cache hat
    nicht getragen", jeder andere Code „die Zahl kam aus dem Cache" (oder die
    Messung wurde per ``--skip-backend-count`` erst gar nicht versucht).
    """
    env = dict(os.environ)
    uv_path = shutil.which("uv")
    if uv_path:
        pruned = [
            entry
            for entry in env.get("PATH", "").split(os.pathsep)
            if entry and not (Path(entry) / "uv").exists()
        ]
        env["PATH"] = os.pathsep.join(pruned)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT), "--check", *(extra_args or [])],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


class _CacheHarness:
    """Cache-Datei stellen und mtimes berührter Repo-Dateien zurückgeben.

    Ohne das Zurückgeben bliebe eine Quelldatei mit Zeitstempel in der Zukunft
    liegen — der Cache waere danach dauerhaft als veraltet zu lesen und der
    teure Collect-Lauf faende bei jedem Aufruf statt.
    """

    def __init__(self) -> None:
        self._touched: list[tuple[Path, float, float]] = []

    def write_fresh(self, value: str = "4321") -> None:
        """Cache mit Zeitstempel in der Zukunft — nichts ist jünger."""
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(f"{value}\n", encoding="utf-8")
        future = CACHE_FILE.stat().st_mtime + 3600
        os.utime(CACHE_FILE, (future, future))

    def make_newer_than_cache(self, path: Path) -> None:
        stat = path.stat()
        self._touched.append((path, stat.st_atime, stat.st_mtime))
        newer = CACHE_FILE.stat().st_mtime + 60
        os.utime(path, (newer, newer))

    def restore(self) -> None:
        for path, atime, mtime in reversed(self._touched):
            os.utime(path, (atime, mtime))
        self._touched.clear()


@pytest.fixture
def cache_state():
    """Sichert Cache und berührte Quelldateien und stellt beide wieder her."""
    original = CACHE_FILE.read_bytes() if CACHE_FILE.exists() else None
    original_mtime = CACHE_FILE.stat().st_mtime if CACHE_FILE.exists() else None
    harness = _CacheHarness()
    try:
        yield harness
    finally:
        harness.restore()
        if original is None:
            CACHE_FILE.unlink(missing_ok=True)
        else:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_bytes(original)
            if original_mtime is not None:
                os.utime(CACHE_FILE, (original_mtime, original_mtime))


def test_fresh_cache_skips_the_expensive_collect(cache_state):
    """Ist der Cache jünger als alle Quellen, wird nicht gemessen."""
    cache_state.write_fresh()

    result = _run_check_without_uv()

    assert result.returncode != MEASUREMENT_FAILED, (
        "Skript hat gemessen statt den Cache zu nutzen: " + result.stderr
    )


def test_touched_test_file_invalidates_the_cache(cache_state):
    """Eine jüngere Testdatei erzwingt eine Neumessung."""
    cache_state.write_fresh()
    cache_state.make_newer_than_cache(REPO_ROOT / "backend" / "tests" / "conftest.py")

    result = _run_check_without_uv()

    assert result.returncode == MEASUREMENT_FAILED, (
        "Cache galt trotz jüngerer Testdatei als frisch — STATUS.md würde still veralten"
    )


def test_touched_app_file_invalidates_the_cache(cache_state):
    """Auch Produktivcode zählt: Parametrisierungen lesen aus ``app/``."""
    cache_state.write_fresh()
    cache_state.make_newer_than_cache(REPO_ROOT / "backend" / "app" / "config.py")

    result = _run_check_without_uv()

    assert result.returncode == MEASUREMENT_FAILED, (
        "Cache galt trotz jüngerer App-Datei als frisch"
    )


def test_touched_pytest_config_invalidates_the_cache(cache_state):
    """Eine jüngere pytest-Konfiguration erzwingt eine Neumessung.

    Dieser Fall lief zuvor über ``[[ -nt ]]``. Die macOS-Systembash (3.2)
    vergleicht dort nur sekundengenau und verschluckte eine Änderung, die in
    derselben Sekunde wie der Cache-Schreibvorgang passierte.
    """
    cache_state.write_fresh()
    cache_state.make_newer_than_cache(REPO_ROOT / "backend" / "pyproject.toml")

    result = _run_check_without_uv()

    assert result.returncode == MEASUREMENT_FAILED, (
        "Cache galt trotz jüngerer pytest-Konfiguration als frisch"
    )


def test_no_cache_flag_forces_measurement(cache_state):
    """``--no-cache`` ignoriert einen frischen Cache."""
    cache_state.write_fresh()
    env = dict(os.environ)
    uv_path = shutil.which("uv")
    if uv_path:
        env["PATH"] = os.pathsep.join(
            entry
            for entry in env.get("PATH", "").split(os.pathsep)
            if entry and not (Path(entry) / "uv").exists()
        )

    result = subprocess.run(
        ["bash", str(SCRIPT), "--check", "--no-cache"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == MEASUREMENT_FAILED, (
        "--no-cache hat trotzdem den Cache verwendet"
    )


def test_skip_backend_count_flag_needs_neither_collect_nor_cache(cache_state):
    """``--skip-backend-count`` misst nicht und liest nicht aus dem Cache.

    Cache ist leer (kein Read moeglich) und ``uv`` ist vom PATH entfernt (kein
    Collect-Lauf moeglich) — ohne das Flag waere Exit 2 (Messfehler) die
    einzig moegliche Antwort. Mit Flag bleibt die Backend-Zeile unangetastet,
    das Skript vergleicht sie mit dem bestehenden Wert aus docs/STATUS.md.
    """
    CACHE_FILE.unlink(missing_ok=True)

    result = _run_check_without_uv(extra_args=["--skip-backend-count"])

    assert result.returncode != MEASUREMENT_FAILED, (
        "--skip-backend-count hat trotzdem versucht zu messen: " + result.stderr
    )


def test_skip_backend_count_env_var_equivalent_to_flag(cache_state):
    """``SYNC_STATUS_SKIP_BACKEND_COUNT=1`` wirkt wie ``--skip-backend-count``."""
    CACHE_FILE.unlink(missing_ok=True)

    result = _run_check_without_uv(
        extra_env={"SYNC_STATUS_SKIP_BACKEND_COUNT": "1"},
    )

    assert result.returncode != MEASUREMENT_FAILED, (
        "SYNC_STATUS_SKIP_BACKEND_COUNT=1 hat trotzdem versucht zu messen: " + result.stderr
    )


@pytest.fixture
def status_file_state():
    """Sichert docs/STATUS.md und stellt den Originalinhalt wieder her."""
    original = STATUS_FILE.read_bytes()
    try:
        yield
    finally:
        STATUS_FILE.write_bytes(original)


def test_skip_backend_count_still_catches_frontend_drift(cache_state, status_file_state):
    """``--skip-backend-count`` lässt nur die Backend-Zeile aus — der Rest bleibt scharf.

    Eine manipulierte Frontend-Zahl muss trotz Flag als Drift auffallen, sonst
    haette das Flag versehentlich die gesamte Autogen-Pruefung entschaerft
    statt nur die teure Backend-Messung zu sparen.
    """
    cache_state.write_fresh()
    text = STATUS_FILE.read_text(encoding="utf-8")
    corrupted, count = re.subn(
        r"(\| Frontend Test-Files \| )\d+( \|)",
        r"\g<1>999999\g<2>",
        text,
    )
    assert count == 1, "Testfixture konnte die Frontend-Zeile nicht eindeutig manipulieren"
    STATUS_FILE.write_text(corrupted, encoding="utf-8")

    result = subprocess.run(
        ["bash", str(SCRIPT), "--check", "--skip-backend-count"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 1, (
        "Frontend-Drift wurde trotz --skip-backend-count nicht erkannt: "
        + result.stdout
        + result.stderr
    )


def test_skip_counts_flag_needs_neither_collect_nor_cache(cache_state):
    """``--skip-counts`` misst weder Backend- noch Frontend-Zähler.

    Wie ``--skip-backend-count``: leerer Cache und PATH ohne ``uv`` — ohne
    das Flag wäre Exit 2 (Messfehler) die einzig mögliche Antwort.
    """
    CACHE_FILE.unlink(missing_ok=True)

    result = _run_check_without_uv(extra_args=["--skip-counts"])

    assert result.returncode != MEASUREMENT_FAILED, (
        "--skip-counts hat trotzdem versucht zu messen: " + result.stderr
    )


def test_skip_counts_env_var_equivalent_to_flag(cache_state):
    """``SYNC_STATUS_SKIP_COUNTS=1`` wirkt wie ``--skip-counts``."""
    CACHE_FILE.unlink(missing_ok=True)

    result = _run_check_without_uv(extra_env={"SYNC_STATUS_SKIP_COUNTS": "1"})

    assert result.returncode != MEASUREMENT_FAILED, (
        "SYNC_STATUS_SKIP_COUNTS=1 hat trotzdem versucht zu messen: " + result.stderr
    )


def test_skip_counts_carries_frontend_counter_over(cache_state, status_file_state):
    """``--skip-counts`` übernimmt den Frontend-Zähler 1:1 aus STATUS.md.

    Ein abweichender Frontend-Wert darf mit dem Flag NICHT als Drift auffallen
    — genau diese Zeile wird per Carry-over mit sich selbst verglichen. (Ohne
    Flag deckt ``test_skip_backend_count_still_catches_frontend_drift`` die
    Gegenrichtung ab.)
    """
    text = STATUS_FILE.read_text(encoding="utf-8")
    corrupted, count = re.subn(
        r"(\| Frontend Test-Files \| )\d+( \|)",
        r"\g<1>999999\g<2>",
        text,
    )
    assert count == 1, "Testfixture konnte die Frontend-Zeile nicht eindeutig manipulieren"
    STATUS_FILE.write_text(corrupted, encoding="utf-8")

    result = subprocess.run(
        ["bash", str(SCRIPT), "--check", "--skip-counts"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "--skip-counts hat den Frontend-Zähler nicht übernommen: "
        + result.stdout
        + result.stderr
    )


def test_skip_counts_still_catches_version_drift(cache_state, status_file_state):
    """``--skip-counts`` entschärft nur die Zähler — der Rest bleibt scharf.

    Eine manipulierte Backend-Version im Autogen-Block muss trotz Flag als
    Drift auffallen, sonst hätte das Flag die gesamte Prüfung deaktiviert.
    """
    text = STATUS_FILE.read_text(encoding="utf-8")
    corrupted, count = re.subn(
        r"(\| Backend \| `backend/pyproject\.toml` \| )[0-9.]+( \|)",
        r"\g<1>99.99.99\g<2>",
        text,
    )
    assert count == 1, "Testfixture konnte die Backend-Versionszeile nicht manipulieren"
    STATUS_FILE.write_text(corrupted, encoding="utf-8")

    result = subprocess.run(
        ["bash", str(SCRIPT), "--check", "--skip-counts"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 1, (
        "Versions-Drift wurde trotz --skip-counts nicht erkannt: "
        + result.stdout
        + result.stderr
    )
