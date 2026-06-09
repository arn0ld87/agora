"""
check_version_drift.py — Version-Drift-Checker for Agora.

Compares version strings from:
  1. backend/pyproject.toml   (authoritative source)
  2. root package.json
  3. README.md badge (if present)
  4. backend/app/__init__.__version__ (importlib.metadata or pyproject fallback)

Exit 0 — all consistent.
Exit 1 — at least one mismatch detected (prints details to stderr).

Usage:
  uv run python scripts/check_version_drift.py        # from backend/
  python backend/scripts/check_version_drift.py       # from repo root
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _repo_root() -> Path:
    """Return the repository root regardless of cwd."""
    here = Path(__file__).resolve()
    # scripts/ -> backend/ -> repo root
    return here.parent.parent.parent


def read_pyproject_version(repo_root: Path) -> str:
    pyproject = repo_root / "backend" / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise ValueError(f"version not found in {pyproject}")
    return m.group(1)


def read_package_json_version(repo_root: Path) -> str:
    pkg = repo_root / "package.json"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    return data["version"]


def read_readme_badge_version(repo_root: Path) -> str | None:
    readme = repo_root / "README.md"
    text = readme.read_text(encoding="utf-8")
    # Matches: [![Version](https://img.shields.io/badge/Version-1.0.0-...)](...)
    m = re.search(r"img\.shields\.io/badge/Version-([^-]+)-", text)
    return m.group(1) if m else None


def read_init_version(repo_root: Path) -> str:
    """
    Read __version__ from app/__init__.py by importing it in a subprocess-free
    way: parse the dynamically resolved value via the same logic used at runtime
    (importlib.metadata with pyproject fallback).
    """
    # We replicate the fallback logic here without importing the full app
    # (which would require the full venv with heavy deps).
    try:
        from importlib.metadata import version, PackageNotFoundError  # noqa: PLC0415
        try:
            return version("agora-backend")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass

    # Fallback: parse pyproject.toml (same as app/__init__.py does)
    return read_pyproject_version(repo_root)


def main() -> int:
    repo_root = _repo_root()
    errors: list[str] = []
    sources: dict[str, str] = {}

    try:
        sources["pyproject.toml"] = read_pyproject_version(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pyproject.toml: {exc}")

    try:
        sources["package.json"] = read_package_json_version(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"package.json: {exc}")

    try:
        badge = read_readme_badge_version(repo_root)
        if badge is not None:
            sources["README.md badge"] = badge
        else:
            print("INFO: No version badge found in README.md — skipping badge check.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"README.md: {exc}")

    try:
        sources["app/__init__.__version__"] = read_init_version(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"app/__init__: {exc}")

    if errors:
        for e in errors:
            print(f"ERROR reading version source: {e}", file=sys.stderr)
        return 1

    canonical = sources.get("pyproject.toml")
    mismatches = [
        f"  {name!r} = {ver!r} (expected {canonical!r})"
        for name, ver in sources.items()
        if ver != canonical
    ]

    if mismatches:
        print("Version drift detected:", file=sys.stderr)
        for line in mismatches:
            print(line, file=sys.stderr)
        print("\nAll sources:", file=sys.stderr)
        for name, ver in sources.items():
            mark = "OK" if ver == canonical else "DRIFT"
            print(f"  [{mark}] {name} = {ver!r}", file=sys.stderr)
        return 1

    print(f"OK: all version sources agree on {canonical!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
