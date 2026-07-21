"""Dependency-SSoT-Drift-Guard (Issue #762).

`backend/pyproject.toml` + `backend/uv.lock` sind die einzige
handgepflegte Backend-Dependency-Quelle. `backend/requirements.txt`
wurde entfernt, weil kein produktiver Pfad (Dockerfile, CI-Workflows,
install.sh, package.json) sie referenziert — CI erzeugt bei Bedarf ihre
eigene, per `uv export` deterministisch generierte Kopie zur Laufzeit
nach `/tmp`.

Diese Tests verhindern zwei Rückfälle:

1. Eine neue, handgepflegte `backend/requirements.txt` schleicht sich
   wieder ein und driftet erneut von `pyproject.toml`/`uv.lock` ab
   (konkret geschehen: `nltk==3.10.0` in requirements.txt vs.
   `nltk==3.9.4` in pyproject.toml/uv.lock, PYSEC-2026-597).
2. Ein produktiver Pfad (Dockerfile, CI-Workflow, install.sh,
   package.json) beginnt wieder, eine eingecheckte
   `backend/requirements.txt` als Install-Quelle zu referenzieren,
   statt `uv sync --frozen` bzw. einen frisch generierten
   `uv export`-Snapshot zu nutzen.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
REQUIREMENTS_TXT = BACKEND_DIR / "requirements.txt"
PYPROJECT_TOML = BACKEND_DIR / "pyproject.toml"

# Dateien mit produktiven Installations- oder Build-Pfaden, die auf keinen
# Fall eine eingecheckte `backend/requirements.txt` referenzieren dürfen.
# `uv export ... --output-file /tmp/...`-Snapshots in CI sind ausdrücklich
# erlaubt (sie generieren die Datei deterministisch zur Laufzeit und
# schreiben sie nicht ins Repo zurück).
PRODUCTIVE_PATH_CANDIDATES = [
    REPO_ROOT / "Dockerfile",
    REPO_ROOT / "install.sh",
    REPO_ROOT / "package.json",
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "cve-monitor.yml",
]

# Matched z. B. "backend/requirements.txt", "-r requirements.txt" (wenn
# cwd bereits backend/ ist) oder "pip install -r requirements.txt". Zeilen
# mit "/tmp/" oder dem CI-Snapshot-Namen werden vor dem Regex-Check bereits
# aus der Prüfung ausgeschlossen (siehe Schleife unten).
COMMITTED_REQUIREMENTS_PATTERN = re.compile(r"\brequirements\.txt\b")


def _nltk_pin_from_pyproject() -> str:
    data = tomllib.loads(PYPROJECT_TOML.read_text(encoding="utf-8"))
    candidates = list(data["project"]["dependencies"])
    candidates += data.get("tool", {}).get("uv", {}).get("override-dependencies", [])
    for entry in candidates:
        if entry.startswith("nltk=="):
            return entry.split("==", 1)[1]
    raise AssertionError("nltk-Pin nicht in backend/pyproject.toml gefunden")


def test_requirements_txt_is_not_manually_maintained() -> None:
    """`backend/requirements.txt` ist entfernt — pyproject.toml/uv.lock sind SSoT.

    Falls die Datei künftig doch wieder per `uv export --frozen --no-hashes`
    generiert würde, müsste sie exakt den pyproject.toml-Pin spiegeln — das
    prüft `test_requirements_txt_nltk_pin_matches_pyproject_if_present`
    zusätzlich als Sicherheitsnetz.
    """
    assert not REQUIREMENTS_TXT.exists(), (
        "backend/requirements.txt existiert wieder als handgepflegte Datei. "
        "SSoT ist ausschließlich backend/pyproject.toml + backend/uv.lock "
        "(Issue #762). Falls ein produktiver Pfad eine requirements.txt "
        "braucht, muss sie deterministisch per "
        "`uv export --frozen --no-hashes -o backend/requirements.txt` "
        "generiert werden, nie manuell editiert."
    )


def test_requirements_txt_nltk_pin_matches_pyproject_if_present() -> None:
    """Falls requirements.txt doch existiert, darf ihr nltk-Pin nicht abweichen.

    Das ist der ursprüngliche Drift-Befund: requirements.txt zeigte
    `nltk==3.10.0`, pyproject.toml/uv.lock pinnen `nltk==3.9.4`
    (PYSEC-2026-597, Issue #661, keine Upstream-Fix-Version verfügbar).
    """
    if not REQUIREMENTS_TXT.exists():
        pytest.skip("backend/requirements.txt existiert nicht (SSoT-Fix aktiv)")

    expected = _nltk_pin_from_pyproject()
    content = REQUIREMENTS_TXT.read_text(encoding="utf-8")
    match = re.search(r"^nltk==([^\s#]+)", content, flags=re.MULTILINE)
    assert match is not None, "requirements.txt enthält keinen nltk==-Pin"
    assert match.group(1) == expected, (
        f"requirements.txt pinnt nltk=={match.group(1)}, "
        f"pyproject.toml/uv.lock pinnen nltk=={expected}. "
        "Divergenz zwischen Backend-Dependency-Quellen (Issue #762)."
    )


def test_no_productive_path_references_committed_requirements_txt() -> None:
    """Dockerfile, CI-Workflows, install.sh, package.json dürfen keine
    eingecheckte `backend/requirements.txt` als Install-Quelle nutzen.

    Laufzeit-Snapshots via `uv export ... --output-file /tmp/...` sind
    erlaubt und werden hier bewusst nicht als Verstoß gewertet.
    """
    violations: list[str] = []
    for path in PRODUCTIVE_PATH_CANDIDATES:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # Prosa-Kommentare sind kein produktiver Installationspfad.
            if "/tmp/" in line or "agora-backend-requirements.txt" in line:
                continue
            if "--format" in line:
                continue  # `--format requirements.txt` ist ein uv-Formatname, kein Dateipfad.
            if COMMITTED_REQUIREMENTS_PATTERN.search(line):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")

    assert not violations, (
        "Produktive Pfade referenzieren eine eingecheckte "
        "backend/requirements.txt statt uv sync --frozen bzw. eines "
        "frisch generierten uv-export-Snapshots (Issue #762):\n"
        + "\n".join(violations)
    )
