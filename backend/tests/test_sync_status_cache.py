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
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sync-status.sh"
CACHE_FILE = REPO_ROOT / "backend" / ".cache" / "sync-status" / "backend-tests-collected"

MEASUREMENT_FAILED = 2


def _run_check_without_uv() -> subprocess.CompletedProcess[str]:
    """``--check`` mit einem PATH ohne ``uv``.

    Ohne ``uv`` ist eine Messung unmöglich. Exit 2 heißt deshalb „der Cache hat
    nicht getragen", jeder andere Code „die Zahl kam aus dem Cache".
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
    return subprocess.run(
        ["bash", str(SCRIPT), "--check"],
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
