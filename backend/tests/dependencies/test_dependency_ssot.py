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
UV_LOCK = BACKEND_DIR / "uv.lock"

# Dateien mit produktiven Installations- oder Build-Pfaden, die auf keinen
# Fall eine eingecheckte `backend/requirements.txt` referenzieren dürfen.
# Alle `.github/workflows/*.yml` statt nur der zwei bekannten Workflows, damit
# ein künftig neu hinzugefügter Workflow nicht unentdeckt am Guard vorbeikommt.
# `uv export ... --output-file /tmp/...`-Snapshots in CI sind ausdrücklich
# erlaubt (sie generieren die Datei deterministisch zur Laufzeit und
# schreiben sie nicht ins Repo zurück).
PRODUCTIVE_PATH_CANDIDATES = [
    REPO_ROOT / "Dockerfile",
    REPO_ROOT / "install.sh",
    REPO_ROOT / "package.json",
    *sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")),
]

# Matched z. B. "backend/requirements.txt", "-r requirements.txt" (wenn
# cwd bereits backend/ ist) oder "pip install -r requirements.txt". Segmente
# mit "/tmp/" oder dem CI-Snapshot-Namen werden vor dem Regex-Check bereits
# aus der Prüfung ausgeschlossen (siehe Schleife unten) — pro Kommando-Segment,
# nicht pro Zeile, damit ein legitimer `uv export`-Snapshot und ein verbotener
# `pip install -r backend/requirements.txt` in derselben verketteten Shell-Zeile
# (z. B. per `&&`) nicht gemeinsam übersehen werden.
COMMITTED_REQUIREMENTS_PATTERN = re.compile(r"\brequirements\.txt\b")
COMMAND_SEPARATOR_PATTERN = re.compile(r"&&|;|\|")


def _nltk_pin_from_pyproject() -> str:
    data = tomllib.loads(PYPROJECT_TOML.read_text(encoding="utf-8"))
    candidates = list(data["project"]["dependencies"])
    candidates += data.get("tool", {}).get("uv", {}).get("override-dependencies", [])
    for entry in candidates:
        if entry.startswith("nltk=="):
            return entry.split("==", 1)[1]
    raise AssertionError("nltk-Pin nicht in backend/pyproject.toml gefunden")


def _nltk_pin_from_uv_lock() -> str:
    data = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    for package in data.get("package", []):
        if package.get("name") == "nltk":
            return package["version"]
    raise AssertionError("nltk-Paket nicht in backend/uv.lock gefunden")


def test_requirements_txt_is_not_manually_maintained() -> None:
    """`backend/requirements.txt` ist entfernt — pyproject.toml/uv.lock sind SSoT.

    Kein produktiver Pfad darf die Datei je wieder eingecheckt referenzieren.
    Ein Installationspfad, der eine `requirements.txt`-Form braucht, generiert
    sie ausschließlich als flüchtigen Laufzeit-Snapshot außerhalb des Repos
    (z. B. per `uv export --frozen --no-hashes --output-file /tmp/...`), nie
    als eingecheckte Datei in `backend/`.
    """
    assert not REQUIREMENTS_TXT.exists(), (
        "backend/requirements.txt existiert wieder als handgepflegte Datei. "
        "SSoT ist ausschließlich backend/pyproject.toml + backend/uv.lock "
        "(Issue #762). Ein produktiver Pfad darf höchstens einen "
        "flüchtigen Laufzeit-Snapshot außerhalb des Repos erzeugen "
        "(z. B. `uv export --frozen --no-hashes --output-file /tmp/...`) — "
        "niemals eine eingecheckte, manuell gepflegte backend/requirements.txt."
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


def test_pyproject_and_uv_lock_nltk_pin_match() -> None:
    """`backend/pyproject.toml` und `backend/uv.lock` müssen densselben nltk-Pin tragen.

    Der ursprüngliche Drift-Befund betraf `requirements.txt` vs. `pyproject.toml`
    (siehe `test_requirements_txt_nltk_pin_matches_pyproject_if_present`). Diese
    beiden Dateien sind jetzt gemeinsam die SSoT (Issue #762) — ein Drift
    zwischen ihnen selbst muss deshalb unabhängig davon erkannt werden.
    """
    pyproject_pin = _nltk_pin_from_pyproject()
    lock_pin = _nltk_pin_from_uv_lock()
    assert lock_pin == pyproject_pin, (
        f"backend/uv.lock pinnt nltk=={lock_pin}, "
        f"backend/pyproject.toml pinnt nltk=={pyproject_pin}. "
        "Beide SSoT-Dateien müssen denselben Pin tragen (Issue #762)."
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
            # Pro Kommando-Segment prüfen, nicht pro Zeile: eine verkettete Shell-Zeile
            # kann einen erlaubten `uv export`-Snapshot UND einen verbotenen
            # `pip install -r backend/requirements.txt`-Aufruf gemeinsam enthalten
            # (z. B. per `&&`) — dann darf nur das Snapshot-Segment ausgenommen werden.
            for segment in COMMAND_SEPARATOR_PATTERN.split(line):
                if "/tmp/" in segment or "agora-backend-requirements.txt" in segment:
                    continue
                if "--format" in segment:
                    continue  # `--format requirements-txt` ist ein uv-Formatname, kein Dateipfad.
                if COMMITTED_REQUIREMENTS_PATTERN.search(segment):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
                    break

    assert not violations, (
        "Produktive Pfade referenzieren eine eingecheckte "
        "backend/requirements.txt statt uv sync --frozen bzw. eines "
        "frisch generierten uv-export-Snapshots (Issue #762):\n"
        + "\n".join(violations)
    )
