"""Test-Isolation der echten Datenverzeichnisse (#1632).

Auf armserver lagen in ``backend/uploads/run_registry/`` zwei Manifeste mit
der Fixture-ID ``sim_abcdef012345``, Status ``failed`` ("Prozess-Neustart
während des Runs"). Zwei Wege führten dorthin:

1. ``Config.UPLOAD_FOLDER`` zeigte in jedem Test auf das echte
   ``backend/uploads``; isoliert war nur ``AGORA_DATA_DIR``.
2. Der ``atexit``-Hook der Job-Terminalisierung (``process_shutdown``) lief
   nach dem letzten Test, als alle Patches schon zurückgenommen waren, und
   schrieb die noch "laufenden" Test-Runs in die echte Registry.

Dieses Modul prüft die Isolation (``_isolated_upload_dirs``), die
Schreibsperre (``tests/_real_data_guard.py``) samt negativer Gegenprobe und
das Abmelden der Shutdown-Hooks.
"""
from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests._real_data_guard import BACKEND_DIR, RealDataWriteError, active_guard

REAL_UPLOADS = BACKEND_DIR / "uploads"
REAL_DATA = BACKEND_DIR / "data"
FIXTURE_SIM_ID = "sim_abcdef012345"
FIXTURE_PROJECT_ID = "proj_abcdef012345"
PROBE_NAME = "agora-1632-guard-probe"

_SUBPROCESS_MARKER = "_AGORA_1632_GUARD_PROBE"


@contextmanager
def _expect_blocked(target: Path):
    """Erwartet, dass der Guard einen Schreibzugriff auf ``target`` abweist.

    Der erwartete Verstoß wird danach verworfen, damit der autouse-Fixture
    diesen Test nicht scheitern lässt. Hätte der Guard versagt und die Datei
    angelegt, räumt der ``finally``-Block nur diese eine Probe-Datei weg.
    """
    guard = active_guard()
    mark = guard.mark()
    try:
        with pytest.raises(RealDataWriteError, match="#1632"):
            yield
    finally:
        taken = guard.discard_since(mark)
        if target.exists() or target.is_symlink():
            guard.armed = False
            try:
                if target.is_dir():
                    target.rmdir()
                else:
                    target.unlink()
            finally:
                guard.armed = True
    # ``os.makedirs`` scheitert schon am ersten fehlenden Elternverzeichnis.
    assert taken and all(
        os.fspath(target).startswith(path) for _event, path, _thread in taken
    ), taken
    assert not target.exists(), f"Guard hat {target} nicht verhindert"


# -- Isolation -------------------------------------------------------------


def test_upload_folder_and_derived_dirs_point_into_tmp(tmp_path, _isolated_upload_dirs) -> None:
    from app.config import Config
    from app.models.project import ProjectManager
    from app.services.report_agent.manager import ReportManager
    from app.services.run_registry import RunRegistry
    from app.services.simulation_manager import SimulationManager
    from app.services.simulation_runner import SimulationRunner

    uploads = _isolated_upload_dirs
    assert uploads.is_dir()
    assert uploads.resolve().is_relative_to(tmp_path.parent.parent.resolve())
    assert not uploads.resolve().is_relative_to(BACKEND_DIR)
    assert Config.UPLOAD_FOLDER == str(uploads)
    assert Config.OASIS_SIMULATION_DATA_DIR == str(uploads / "simulations")
    assert RunRegistry.REGISTRY_DIR == str(uploads / "run_registry")
    assert ProjectManager.PROJECTS_DIR == str(uploads / "projects")
    assert ReportManager.REPORTS_DIR == str(uploads / "reports")
    assert SimulationManager.SIMULATION_DATA_DIR == str(uploads / "simulations")
    assert SimulationRunner.RUN_STATE_DIR == str(uploads / "simulations")
    assert os.environ["AGORA_DATA_DIR"] == str(tmp_path)


def test_run_manifest_with_fixture_ids_lands_in_tmp(_isolated_upload_dirs) -> None:
    """Der Weg aus dem Befund: ein Run für die Fixture-Simulation ohne eigenen Patch."""
    from app.services.run_registry import RunRegistry

    run = RunRegistry().create_run(
        "simulation_run",
        FIXTURE_SIM_ID,
        linked_ids={"project_id": FIXTURE_PROJECT_ID, "simulation_id": FIXTURE_SIM_ID},
        status="processing",
    )

    manifest = _isolated_upload_dirs / "run_registry" / f"{run['run_id']}.json"
    assert manifest.is_file()
    assert not (REAL_UPLOADS / "run_registry" / f"{run['run_id']}.json").exists()


# -- Schreibsperre: negative Gegenprobe ------------------------------------


def test_open_for_write_into_real_run_registry_is_blocked() -> None:
    target = REAL_UPLOADS / "run_registry" / f"{PROBE_NAME}.json"
    with _expect_blocked(target):
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("{}")


def test_makedirs_into_real_simulation_dir_is_blocked() -> None:
    target = REAL_UPLOADS / "simulations" / FIXTURE_SIM_ID / PROBE_NAME
    with _expect_blocked(target):
        os.makedirs(target)


def test_atomic_replace_into_real_data_dir_is_blocked(tmp_path) -> None:
    """``write_json_atomic`` schreibt per ``os.replace`` — auch das muss scheitern."""
    staged = tmp_path / "staged.json"
    staged.write_text("{}", encoding="utf-8")
    target = REAL_DATA / f"{PROBE_NAME}.json"
    with _expect_blocked(target):
        os.replace(staged, target)
    assert staged.exists()


def test_swallowed_write_is_still_recorded() -> None:
    """Anwendungscode fängt Fehler oft breit ab; der Verstoß bleibt trotzdem notiert."""
    guard = active_guard()
    mark = guard.mark()
    target = REAL_UPLOADS / "run_registry" / f"{PROBE_NAME}.json"
    try:
        open(target, "w", encoding="utf-8").close()  # noqa: SIM115
    except Exception:  # noqa: BLE001 — genau das Muster, das der Guard überstehen muss
        pass
    recorded = guard.discard_since(mark)
    assert [path for _event, path, _thread in recorded] == [os.fspath(target)]
    assert not target.exists()


def test_rmtree_of_tmp_tree_with_data_and_uploads_entries_is_allowed(
    tmp_path, monkeypatch
) -> None:
    """``shutil.rmtree`` löscht per ``dir_fd`` mit relativen Namen.

    Läuft die Suite mit cwd ``backend/``, darf ein ``data``- oder
    ``uploads``-Eintrag im tmp-Baum nicht als ``backend/data`` gelten.
    """
    import shutil

    monkeypatch.chdir(BACKEND_DIR)
    tree = tmp_path / "tree" / "x"
    (tree / "data").mkdir(parents=True)
    (tree / "data" / "file.json").write_text("{}", encoding="utf-8")
    (tree / "uploads").write_text("not a dir", encoding="utf-8")
    guard = active_guard()
    mark = guard.mark()

    shutil.rmtree(tmp_path / "tree")

    assert guard.violations_since(mark) == []
    assert not (tmp_path / "tree").exists()


def test_symlink_into_real_uploads_may_be_removed_but_not_written_through(tmp_path) -> None:
    """``unlink`` trifft den Link, ``open(..., "w")`` sein Ziel."""
    link = tmp_path / "link-into-uploads"
    link.symlink_to(REAL_UPLOADS / f"{PROBE_NAME}.json")
    target = REAL_UPLOADS / f"{PROBE_NAME}.json"
    guard = active_guard()

    mark = guard.mark()
    with pytest.raises(RealDataWriteError, match="#1632"):
        with open(link, "w", encoding="utf-8") as handle:
            handle.write("{}")
    assert [path for _event, path, _thread in guard.discard_since(mark)] == [os.fspath(link)]
    assert not target.exists()

    mark = guard.mark()
    link.unlink()
    assert guard.violations_since(mark) == []
    assert not link.is_symlink()


def test_reads_and_tmp_writes_stay_allowed(tmp_path) -> None:
    assert (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
    (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
    os.makedirs(tmp_path / "run_registry", exist_ok=True)


# -- Gegenprobe im Subprozess ----------------------------------------------


@pytest.mark.skipif(
    os.environ.get(_SUBPROCESS_MARKER) != "1",
    reason="Nur im Subprozess von test_leaking_test_fails_and_shutdown_writes_nothing.",
)
def test_probe_leaks_into_real_uploads() -> None:
    """Absichtlicher Verstoß, dessen Fehler der Code verschluckt."""
    try:
        with open(REAL_UPLOADS / "run_registry" / f"{PROBE_NAME}.json", "w") as handle:
            handle.write("{}")
    except Exception:  # noqa: BLE001
        pass


@pytest.mark.skipif(
    os.environ.get(_SUBPROCESS_MARKER) != "1",
    reason="Nur im Subprozess von test_leaking_test_fails_and_shutdown_writes_nothing.",
)
def test_probe_registers_shutdown_hook_with_running_run() -> None:
    """Wie ``create_app()``: Shutdown-Hook registrieren, ein Run bleibt "laufend"."""
    from app.services.run_registry import RunRegistry
    from app.services.simulation_runner import SimulationRunner

    RunRegistry().create_run(
        "simulation_prepare",
        FIXTURE_SIM_ID,
        linked_ids={"project_id": FIXTURE_PROJECT_ID, "simulation_id": FIXTURE_SIM_ID},
        status="processing",
    )
    SimulationRunner.register_cleanup()


@pytest.mark.skipif(
    os.environ.get(_SUBPROCESS_MARKER) == "1",
    reason="Läuft im Subprozess dieses Tests — würde sich sonst rekursiv starten.",
)
def test_leaking_test_fails_and_shutdown_writes_nothing() -> None:
    """Gegenprobe über die echte pytest-Maschinerie.

    Erwartet: der leckende Probe-Test scheitert trotz verschluckter Ausnahme
    (der autouse-Fixture meldet ihn im Teardown als ERROR), der
    Hook-Probe-Test besteht, und beim Prozessende versucht kein
    ``atexit``-Hook mehr, in das echte Upload-Verzeichnis zu schreiben.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"WERKZEUG_RUN_MAIN", "PYTEST_XDIST_WORKER"}
    }
    env.update({_SUBPROCESS_MARKER: "1", "FLASK_DEBUG": "false"})
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/contracts/test_real_data_guard.py::test_probe_leaks_into_real_uploads",
            "tests/contracts/test_real_data_guard.py::test_probe_registers_shutdown_hook_with_running_run",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
        ],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output[-3000:]
    assert "2 passed, 1 error" in result.stdout, output[-3000:]
    assert (
        "ERROR tests/contracts/test_real_data_guard.py::test_probe_leaks_into_real_uploads"
        in result.stdout
    ), output[-3000:]
    assert "echtes Datenverzeichnis" in result.stdout
    assert "Fehler beim Markieren der Jobs" not in output, output[-3000:]
    assert "RealDataWriteError" not in result.stderr, output[-3000:]
    assert not (REAL_UPLOADS / "run_registry" / f"{PROBE_NAME}.json").exists()
