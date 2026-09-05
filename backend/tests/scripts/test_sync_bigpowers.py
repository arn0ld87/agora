"""Regressionstests fuer ``scripts/sync-bigpowers.sh`` (Codex-Review PR #1421).

Das Skript stellt das Bigpowers-Overlay auf einem Klon her: relative
Symlinks auf ``node_modules/bigpowers`` plus die passende Ausschlussliste in
``info/exclude``. Drei Befunde aus dem Review sind hier abgesichert:

  P1  In einem linked worktree ist ``.git`` eine Datei. Ein hartkodiertes
      ``$ROOT/.git/info/exclude`` scheitert dort an ``mkdir`` mit
      "Not a directory" — und das Repo arbeitet mit ueber zwanzig Worktrees.
  P2  ``--check`` prueft gegen die ERWARTETEN Links. Zuvor las es die
      vorhandenen und meldete bei komplett fehlendem Overlay "konsistent:
      0 Symlinks" mit Exit 0 — ein Gate, das seinen eigenen Ausfall nicht
      bemerkt.
  P3  Ein Bigpowers-Upgrade, das ein Skript entfernt, liess den alten Link
      als kaputten Rest stehen. ``--check`` meldete Drift und empfahl den
      Sync, der ihn nicht anfasste.

Die Tests bauen ein Minimal-Repo mit einer Attrappen-Dependency, statt die
echte zu benoetigen — das Skript kennt nur ``node_modules/bigpowers``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "sync-bigpowers.sh"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _run_script(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, GIT_CONFIG_GLOBAL=str(repo / ".gitconfig-none"))
    return subprocess.run(
        ["bash", str(repo / "scripts" / "sync-bigpowers.sh"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def _make_dependency(repo: Path, script_names: list[str], skill_names: list[str]) -> None:
    dep = repo / "node_modules" / "bigpowers"
    (dep / "scripts").mkdir(parents=True, exist_ok=True)
    (dep / "skills").mkdir(parents=True, exist_ok=True)
    (dep / "package.json").write_text(json.dumps({"name": "bigpowers", "version": "9.9.9"}))
    for name in script_names:
        target = dep / "scripts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env bash\n")
    for name in skill_names:
        (dep / "skills" / name).mkdir(parents=True, exist_ok=True)
        (dep / "skills" / name / "SKILL.md").write_text("# skill\n")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Minimal-Repo mit dem echten Skript und einer Attrappen-Dependency."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / ".claude" / "skills").mkdir(parents=True)
    (root / "scripts" / "sync-bigpowers.sh").write_text(SCRIPT.read_text())

    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.invalid", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / "README.md").write_text("# test\n")
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", "init", cwd=root)

    _make_dependency(root, ["bp-timing.sh", "lib/helper.sh"], ["develop-tdd", "audit-code"])
    return root


# --- Grundverhalten ---------------------------------------------------------


def test_sync_creates_relative_links(repo: Path):
    result = _run_script(repo)

    assert result.returncode == 0, result.stderr
    link = repo / "scripts" / "bp-timing.sh"
    assert link.is_symlink()
    assert not os.path.isabs(os.readlink(link)), "Links muessen relativ sein"
    assert link.resolve() == (repo / "node_modules/bigpowers/scripts/bp-timing.sh").resolve()
    assert (repo / ".claude" / "skills" / "develop-tdd").is_symlink()


def test_sync_never_overwrites_a_real_file(repo: Path):
    own = repo / "scripts" / "bp-timing.sh"
    own.write_text("# AGORA-eigen\n")

    result = _run_script(repo)

    assert result.returncode == 0
    assert not own.is_symlink()
    assert own.read_text() == "# AGORA-eigen\n"
    assert "KONFLIKT" in result.stdout


def test_sync_is_idempotent(repo: Path):
    _run_script(repo)
    exclude = repo / ".git" / "info" / "exclude"
    first = exclude.read_text()

    _run_script(repo)

    assert exclude.read_text() == first


def test_linked_symlinks_are_git_ignored(repo: Path):
    _run_script(repo)

    untracked = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout
    assert "bp-timing.sh" not in untracked
    assert "develop-tdd" not in untracked


# --- P1: linked worktree ----------------------------------------------------


def test_sync_works_in_a_linked_worktree(repo: Path, tmp_path: Path):
    """``.git`` ist dort eine Datei — der Bug war ein ``mkdir``-Abbruch."""
    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", "feature", str(worktree), cwd=repo)

    # Der Worktree teilt sich node_modules nicht; das Overlay braucht sie dort.
    _make_dependency(worktree, ["bp-timing.sh"], ["develop-tdd"])
    (worktree / ".claude" / "skills").mkdir(parents=True, exist_ok=True)

    assert (worktree / ".git").is_file(), "Vorbedingung: .git ist hier eine Datei"

    result = _run_script(worktree)

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "Not a directory" not in result.stderr
    assert (worktree / "scripts" / "bp-timing.sh").is_symlink()


def test_worktree_writes_into_the_shared_exclude(repo: Path, tmp_path: Path):
    """``info/exclude`` gehoert dem gemeinsamen Git-Verzeichnis, nicht dem Worktree."""
    worktree = tmp_path / "wt2"
    _git("worktree", "add", "-q", "-b", "feature2", str(worktree), cwd=repo)
    _make_dependency(worktree, ["bp-timing.sh"], [])
    (worktree / ".claude" / "skills").mkdir(parents=True, exist_ok=True)

    _run_script(worktree)

    shared = (repo / ".git" / "info" / "exclude").read_text()
    assert "/scripts/bp-timing.sh" in shared


# --- P2: --check gegen die erwarteten Links ---------------------------------


def test_check_is_green_after_a_sync(repo: Path):
    _run_script(repo)

    result = _run_script(repo, "--check")

    assert result.returncode == 0, result.stdout
    assert "konsistent" in result.stdout


def test_check_fails_when_the_overlay_was_never_created(repo: Path):
    """Der Befund, der zuvor als 'konsistent: 0 Symlinks' durchging."""
    result = _run_script(repo, "--check")

    assert result.returncode == 1
    assert "Link fehlt" in result.stdout
    assert "konsistent" not in result.stdout


def test_check_fails_when_a_link_was_deleted(repo: Path):
    _run_script(repo)
    (repo / "scripts" / "bp-timing.sh").unlink()

    result = _run_script(repo, "--check")

    assert result.returncode == 1
    assert "bp-timing.sh" in result.stdout


def test_check_fails_when_a_link_dangles(repo: Path):
    _run_script(repo)
    (repo / "node_modules" / "bigpowers" / "scripts" / "bp-timing.sh").unlink()

    result = _run_script(repo, "--check")

    assert result.returncode == 1
    assert "ins Leere" in result.stdout or "veralteter Link" in result.stdout


def test_check_reports_a_missing_dependency(repo: Path):
    import shutil

    shutil.rmtree(repo / "node_modules")

    result = _run_script(repo, "--check")

    assert result.returncode == 1
    assert "nicht installiert" in result.stdout


def test_a_conflicting_own_file_does_not_fail_the_check(repo: Path):
    """Eine bewusst uebersprungene AGORA-Datei ist kein Drift."""
    (repo / "scripts" / "bp-timing.sh").write_text("# AGORA-eigen\n")
    _run_script(repo)

    result = _run_script(repo, "--check")

    assert result.returncode == 0, result.stdout
    assert "AGORA-eigen" in result.stdout


# --- P3: Upgrade entfernt ein Skript ----------------------------------------


def test_sync_prunes_links_removed_from_the_dependency(repo: Path):
    """Der Deadlock: --check meldete Drift, der Sync konnte sie nicht beheben."""
    _run_script(repo)
    assert (repo / "scripts" / "bp-timing.sh").is_symlink()

    # Bigpowers-Upgrade entfernt ein Skript und eine Skill.
    (repo / "node_modules" / "bigpowers" / "scripts" / "bp-timing.sh").unlink()
    import shutil

    shutil.rmtree(repo / "node_modules" / "bigpowers" / "skills" / "audit-code")

    result = _run_script(repo)

    assert result.returncode == 0, result.stderr
    assert not (repo / "scripts" / "bp-timing.sh").exists(follow_symlinks=False)
    assert not (repo / ".claude" / "skills" / "audit-code").exists(follow_symlinks=False)
    assert "ENTFERNT" in result.stdout


def test_check_is_green_again_after_pruning(repo: Path):
    _run_script(repo)
    (repo / "node_modules" / "bigpowers" / "scripts" / "bp-timing.sh").unlink()

    assert _run_script(repo, "--check").returncode == 1
    _run_script(repo)

    result = _run_script(repo, "--check")
    assert result.returncode == 0, result.stdout


def test_pruning_leaves_own_files_alone(repo: Path):
    """Der Prune darf nur eigene Symlinks anfassen, keine echten Dateien."""
    _run_script(repo)
    own = repo / "scripts" / "eigenes-agora-skript.sh"
    own.write_text("# AGORA\n")

    _run_script(repo)

    assert own.exists()
    assert own.read_text() == "# AGORA\n"


def test_a_renamed_script_leaves_no_stale_link(repo: Path):
    _run_script(repo)
    dep_scripts = repo / "node_modules" / "bigpowers" / "scripts"
    (dep_scripts / "bp-timing.sh").rename(dep_scripts / "bp-timing-v2.sh")

    _run_script(repo)

    assert not (repo / "scripts" / "bp-timing.sh").exists(follow_symlinks=False)
    assert (repo / "scripts" / "bp-timing-v2.sh").is_symlink()
    assert _run_script(repo, "--check").returncode == 0
