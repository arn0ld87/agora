"""Selektiert ein deterministisches, schnelles PR-Test-Subset fuer Agora.

Kombiniert:
1. Eine verpflichtende Core-Suite (Contracts, Regression, Unit, Security,
   Dependencies, Report-Agent-Pipeline, Confidence, Evidence-Binder, LLM, Storage).
2. Dynamisch erkannte Tests fuer geaenderte Dateien (Git-Diff gegen Basis-Branch,
   z. B. origin/main oder HEAD~1).

Verhindert, dass PRs die gesamte ~10.000-Test-Suite sequentiell ausfuehren,
waehrend alle fuer den PR relevanten Aenderungen vollstaendig abgedeckt bleiben.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Basis-Verzeichnisse relativ zu diesem Skript
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

# Verpflichtende Core-Test-Pfade (relativ zu backend/)
CORE_TEST_TARGETS: tuple[str, ...] = (
    "tests/contracts",
    "tests/regression",
    "tests/unit",
    "tests/security",
    "tests/dependencies",
    "tests/services/report_agent",
    "tests/test_confidence_calculator.py",
    "tests/test_evidence_binder.py",
    "tests/llm",
    "tests/storage",
)


def resolve_base_ref(explicit_base: str | None = None) -> str | None:
    """Ermittelt den besten verfuegbaren Git-Basis-Ref fuer den Diff."""
    if explicit_base:
        return explicit_base

    candidates = (
        "origin/main",
        "refs/remotes/origin/main",
        "main",
        "HEAD~1",
    )
    for ref in candidates:
        res = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return ref
    return None


def get_changed_files(base_ref: str | None) -> list[str]:
    """Liest geaenderte Dateien im Vergleich zum Basis-Ref via git diff."""
    if not base_ref:
        return []

    # Versuche Drei-Punkt-Diff (Merge-Base)
    cmd = ["git", "diff", "--name-only", f"{base_ref}...HEAD"]
    res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        cmd = ["git", "diff", "--name-only", base_ref, "HEAD"]
        res = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if res.returncode != 0:
            return []

    lines = res.stdout.strip().splitlines()
    return [line.strip() for line in lines if line.strip()]


def _map_test_path(norm: str) -> list[str]:
    """Mappt Aenderungen unter tests/."""
    rel = norm[len("backend/") :] if norm.startswith("backend/") else norm
    target = BACKEND_DIR / rel
    if target.is_file() and target.name.startswith("test_") and target.suffix == ".py":
        return [rel]
    if target.is_dir():
        return [rel]
    parent = target.parent
    rel_parent = str(parent.relative_to(BACKEND_DIR))
    if parent.exists() and rel_parent != ".":
        return [rel_parent]
    return []


def _search_fallback_tests(stem: str) -> list[str]:
    """Sucht Unit-, Service-, API- und Regressions-Tests nach Stem oder 2-Token-Prefix."""
    matches: list[str] = []
    tokens = [tok for tok in stem.split("_") if tok]
    search_keys = [stem]
    if len(tokens) >= 2:
        search_keys.append(f"{tokens[0]}_{tokens[1]}")
    for key in search_keys:
        for pattern in (
            f"tests/unit/**/test_*{key}*.py",
            f"tests/regression/**/test_*{key}*.py",
            f"tests/services/**/test_*{key}*.py",
            f"tests/api/**/test_*{key}*.py",
            f"tests/test_*{key}*.py",
        ):
            for path in BACKEND_DIR.glob(pattern):
                rel = str(path.relative_to(BACKEND_DIR))
                if rel not in matches:
                    matches.append(rel)
        if matches:
            break
    return matches


def _map_api_path(stem: str) -> list[str]:
    """Mappt Aenderungen unter app/api/."""
    candidates = (
        f"tests/api/test_{stem}.py",
        f"tests/test_{stem}.py",
    )
    for c in candidates:
        if (BACKEND_DIR / c).exists():
            return [c]
    matches = [
        str(p.relative_to(BACKEND_DIR))
        for p in BACKEND_DIR.glob(f"tests/api/**/test_*{stem}*.py")
    ]
    if matches:
        return matches
    if (BACKEND_DIR / "tests/api").exists():
        return ["tests/api"]
    return []


def _map_services_path(parts: list[str], stem: str) -> list[str]:
    """Mappt Aenderungen unter app/services/."""
    targets: list[str] = []
    if len(parts) > 2:
        subfolder = parts[1]
        test_dir = BACKEND_DIR / "tests/services" / subfolder
        if test_dir.exists():
            targets.append(f"tests/services/{subfolder}")

    for c in (f"tests/services/test_{stem}.py", f"tests/test_{stem}.py"):
        if (BACKEND_DIR / c).exists():
            targets.append(c)

    if not targets:
        for p in BACKEND_DIR.glob(f"tests/services/**/test_*{stem}*.py"):
            targets.append(str(p.relative_to(BACKEND_DIR)))

    if not targets:
        targets.extend(_search_fallback_tests(stem))

    return targets


def _map_app_path(rel_app: str) -> list[str]:
    """Mappt Aenderungen unter app/."""
    parts = rel_app.split("/")
    pkg = parts[0]
    stem = Path(rel_app).stem

    if pkg in ("contracts", "security", "llm", "storage"):
        return []

    if pkg == "api":
        return _map_api_path(stem)

    if pkg == "services":
        return _map_services_path(parts, stem)

    # Root-Dateien unter app/ (z. B. config.py, app.py)
    candidates = (
        f"tests/test_{stem}.py",
        f"tests/test_app_{stem}.py",
    )
    targets = [c for c in candidates if (BACKEND_DIR / c).exists()]
    if not targets:
        targets.extend(_search_fallback_tests(stem))
    return targets


def _map_scripts_path(norm: str) -> list[str]:
    """Mappt Aenderungen unter scripts/."""
    stem = Path(norm).stem
    candidates = (
        f"tests/scripts/test_{stem}.py",
        f"tests/scripts/test_{stem}_script.py",
    )
    for c in candidates:
        if (BACKEND_DIR / c).exists():
            return [c]
    matches = [
        str(p.relative_to(BACKEND_DIR))
        for p in BACKEND_DIR.glob(f"tests/scripts/**/test_*{stem}*.py")
    ]
    if matches:
        return matches
    return _search_fallback_tests(stem)


def map_changed_file_to_tests(changed_file: str) -> list[str]:
    """Mappt eine geaenderte Datei auf Test-Targets (relativ zu backend/)."""
    norm = changed_file.replace("\\", "/")

    if norm.startswith("backend/tests/") or norm.startswith("tests/"):
        return _map_test_path(norm)

    if norm.startswith("backend/app/"):
        rel_app = norm[len("backend/app/") :]
        return _map_app_path(rel_app)

    if norm.startswith("backend/scripts/"):
        return _map_scripts_path(norm)

    if norm in ("backend/pyproject.toml", "backend/uv.lock"):
        return ["tests/dependencies"]

    return []


def _filter_existing_targets(
    candidates: set[str],
    ignore_contracts: bool,
) -> list[str]:
    """Filtert Targets nach Existenz auf Dateisystem und Vertrags-Option."""
    valid: list[str] = []
    for t in candidates:
        if ignore_contracts and (t == "tests/contracts" or t.startswith("tests/contracts/")):
            continue
        if (BACKEND_DIR / t).exists():
            valid.append(t)
    return valid


def _deduplicate_subpaths(valid_targets: list[str]) -> list[str]:
    """Entfernt Einzeldateien, deren Elternverzeichnis bereits gelistet ist."""
    dirs = [t for t in valid_targets if (BACKEND_DIR / t).is_dir()]
    final_targets: list[str] = []
    for t in sorted(valid_targets):
        if (BACKEND_DIR / t).is_file():
            parent_rel = str((BACKEND_DIR / t).parent.relative_to(BACKEND_DIR))
            if any(parent_rel == d or parent_rel.startswith(d + "/") for d in dirs):
                continue
        final_targets.append(t)
    return final_targets


def select_tests(
    base_ref: str | None = None,
    ignore_contracts: bool = False,
) -> list[str]:
    """Ermittelt alle auszufuehrenden Test-Pfade."""
    selected: set[str] = set(CORE_TEST_TARGETS)

    base = resolve_base_ref(base_ref)
    for f in get_changed_files(base):
        for t in map_changed_file_to_tests(f):
            selected.add(t)

    valid = _filter_existing_targets(selected, ignore_contracts)
    return _deduplicate_subpaths(valid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=None,
        help="Git Base-Ref fuer den Diff (z. B. origin/main)",
    )
    parser.add_argument(
        "--ignore-contracts",
        action="store_true",
        help="Schliesst tests/contracts aus (z. B. wenn vorher separat ausgefuehrt)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Gibt die Test-Targets als JSON-Array aus",
    )
    parser.add_argument(
        "--count",
        action="store_true",
        help="Gibt nur die Anzahl der selektierten Targets aus",
    )
    args = parser.parse_args()

    targets = select_tests(base_ref=args.base, ignore_contracts=args.ignore_contracts)

    if args.count:
        sys.stdout.write(f"{len(targets)}\n")
    elif args.json:
        sys.stdout.write(f"{json.dumps(targets, indent=2)}\n")
    else:
        sys.stdout.write(f"{' '.join(targets)}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
