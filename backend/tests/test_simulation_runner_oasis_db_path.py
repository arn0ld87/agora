"""Sub-Slice 21 — OASIS_DB_PATH pro Sim, damit OASIS keine DB ins
read-only Site-Packages-Verzeichnis schreibt.

OASIS' ``get_db_path()`` (siehe oasis/social_platform/database.py) macht
ohne ``OASIS_DB_PATH``-ENV ein ``os.makedirs`` in
``site-packages/oasis/data/`` — auf einem read-only Container-FS
(Compose ``read_only: true``) crashed das mit
``OSError: [Errno 30] Read-only file system``.

Diese Tests verifizieren, dass ``SimulationRunner.start_simulation``
einen sim-spezifischen ``OASIS_DB_PATH`` ins Subprozess-Env injiziert
und das Verzeichnis vorher anlegt (sodass OASIS' kein-mkdir-Pfad bei
gesetztem ENV greift).
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def runner_module():
    from app.services import simulation_runner
    return simulation_runner


def test_oasis_db_env_helper_returns_sim_specific_path(runner_module, tmp_path):
    """Helper liefert ``<sim_dir>/oasis_db/social_media.db`` und legt
    das Verzeichnis an."""
    sim_dir = tmp_path / "sim_abc"
    sim_dir.mkdir()

    db_path = runner_module._compute_oasis_db_path(str(sim_dir))

    assert db_path.endswith("oasis_db/social_media.db") or db_path.endswith(
        "oasis_db\\social_media.db"
    )
    assert os.path.isdir(os.path.dirname(db_path)), (
        "OASIS-DB-Verzeichnis muss vor Subprozess-Start existieren — sonst "
        "scheitert OASIS' get_db_path() ohne mkdir-Branch."
    )


def test_oasis_db_env_helper_is_idempotent(runner_module, tmp_path):
    """Mehrfacher Aufruf darf weder crashen noch den Pfad ändern."""
    sim_dir = tmp_path / "sim_abc"
    sim_dir.mkdir()

    p1 = runner_module._compute_oasis_db_path(str(sim_dir))
    p2 = runner_module._compute_oasis_db_path(str(sim_dir))
    assert p1 == p2


def test_oasis_db_env_helper_user_override_wins(runner_module, tmp_path, monkeypatch):
    """Wenn der User selbst ``OASIS_DB_PATH`` setzt (z. B. via .env oder
    Compose-Env), respektiert der Helper das und überschreibt nicht."""
    sim_dir = tmp_path / "sim_abc"
    sim_dir.mkdir()
    monkeypatch.setenv("OASIS_DB_PATH", "/explicit/user/path.db")

    # Simuliere die Inject-Funktion: passt den env-Dict so an wie sie es
    # auch im Runner tun würde.
    env = os.environ.copy()
    runner_module._inject_oasis_db_env(env, str(sim_dir))

    assert env["OASIS_DB_PATH"] == "/explicit/user/path.db"


def test_oasis_db_env_helper_injects_when_unset(runner_module, tmp_path, monkeypatch):
    """Default-Pfad: User hat nichts gesetzt → Helper setzt sim-spezifischen
    Pfad ins env."""
    sim_dir = tmp_path / "sim_xyz"
    sim_dir.mkdir()
    monkeypatch.delenv("OASIS_DB_PATH", raising=False)

    env = {}
    runner_module._inject_oasis_db_env(env, str(sim_dir))

    assert "OASIS_DB_PATH" in env
    assert env["OASIS_DB_PATH"].startswith(str(sim_dir))
    assert env["OASIS_DB_PATH"].endswith("social_media.db")
    # Verzeichnis muss bereits existieren
    assert os.path.isdir(os.path.dirname(env["OASIS_DB_PATH"]))
