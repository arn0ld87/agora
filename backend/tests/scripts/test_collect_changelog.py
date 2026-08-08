"""Regressionstests für ``scripts/collect-changelog.py``.

Der Collector ist destruktiv: er faltet ``changelog.d/``-Fragmente unter
``## [Unreleased]`` in ``CHANGELOG.md`` und löscht sie danach. Jeder Defekt
hier verliert Release-Historie. Die Tests laufen deshalb gegen eine
Repo-Attrappe unter ``tmp_path`` — das echte Skript wird hineinkopiert, weil
es seine Pfade relativ zu seiner eigenen Position auflöst.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "collect-changelog.py"

CHANGELOG_TEMPLATE = """# Changelog

## [Unreleased]

## [0.9.0] — 2026-07-01

- Bestehender Eintrag.
"""


def _make_repo(tmp_path: Path, *, changelog: str | None = CHANGELOG_TEMPLATE) -> Path:
    """Repo-Attrappe mit kopiertem Skript, CHANGELOG.md und changelog.d/."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(SCRIPT, scripts_dir / SCRIPT.name)
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "README.md").write_text(
        "# Konvention\n", encoding="utf-8"
    )
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / SCRIPT.name), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _fragment(repo: Path, name: str, body: str) -> Path:
    p = repo / "changelog.d" / name
    p.write_text(body, encoding="utf-8")
    return p


def test_collects_fragments_and_removes_them(tmp_path):
    repo = _make_repo(tmp_path)
    _fragment(repo, "1140-feature.md", "### Added\n- Feature aus PR 1140.")
    _fragment(repo, "1139-fix.md", "### Fixed\n- Fix aus PR 1139.")

    result = _run(repo)

    assert result.returncode == 0, result.stderr
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Feature aus PR 1140." in text
    assert "Fix aus PR 1139." in text
    # Fragmente sind eingesammelt, README bleibt liegen.
    remaining = sorted(p.name for p in (repo / "changelog.d").iterdir())
    assert remaining == ["README.md"]
    # Einfügung liegt unter [Unreleased], vor dem alten Release-Block.
    assert text.index("## [Unreleased]") < text.index("Feature aus PR 1140.")
    assert text.index("Fix aus PR 1139.") < text.index("## [0.9.0]")


def test_orders_numerically_not_lexicographically(tmp_path):
    """``1140`` ist neuer als ``999`` — lexikografisch stünde 999 zuerst."""
    repo = _make_repo(tmp_path)
    _fragment(repo, "999-alt.md", "- Eintrag PR 999.")
    _fragment(repo, "1140-neu.md", "- Eintrag PR 1140.")

    result = _run(repo)

    assert result.returncode == 0, result.stderr
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.index("Eintrag PR 1140.") < text.index("Eintrag PR 999.")


def test_check_mode_reports_open_fragments(tmp_path):
    repo = _make_repo(tmp_path)
    _fragment(repo, "1140-feature.md", "- Eintrag.")

    result = _run(repo, "--check")

    assert result.returncode == 1
    assert "1140-feature.md" in result.stdout
    # --check verändert nichts.
    assert (repo / "changelog.d" / "1140-feature.md").exists()
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG_TEMPLATE


def test_check_mode_green_without_fragments(tmp_path):
    repo = _make_repo(tmp_path)

    result = _run(repo, "--check")

    assert result.returncode == 0


def test_missing_unreleased_marker_aborts_and_keeps_fragments(tmp_path):
    repo = _make_repo(tmp_path, changelog="# Changelog\n\n## [0.9.0]\n")
    _fragment(repo, "1140-feature.md", "- Eintrag.")

    result = _run(repo)

    assert result.returncode == 2
    assert "[Unreleased]" in result.stderr
    assert (repo / "changelog.d" / "1140-feature.md").exists()


def test_empty_fragment_aborts_without_writing_or_deleting(tmp_path):
    """Ein leeres Fragment ist ein kaputtes PR-Artefakt — harter Abbruch.

    Vor dem Fix wurde die leere Datei still gelöscht und der Lauf endete
    grün; der zugehörige Eintrag war damit unwiederbringlich verloren.
    """
    repo = _make_repo(tmp_path)
    _fragment(repo, "1140-leer.md", "   \n\n")
    _fragment(repo, "1139-ok.md", "- Gültiger Eintrag.")

    result = _run(repo)

    assert result.returncode == 2
    assert "1140-leer.md" in result.stderr
    # Nichts wurde gelöscht, nichts geschrieben.
    remaining = sorted(p.name for p in (repo / "changelog.d").iterdir())
    assert remaining == ["1139-ok.md", "1140-leer.md", "README.md"]
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG_TEMPLATE


def test_noop_without_fragments(tmp_path):
    repo = _make_repo(tmp_path)

    result = _run(repo)

    assert result.returncode == 0
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == CHANGELOG_TEMPLATE
