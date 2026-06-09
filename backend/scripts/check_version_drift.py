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

import ast
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
    Read __version__ from app/__init__.py by parsing its AST and executing
    only the version-defining statement or block, avoiding heavy imports.
    """
    init_py = repo_root / "backend" / "app" / "__init__.py"
    if not init_py.exists():
        raise FileNotFoundError(f"__init__.py not found at {init_py}")

    tree = ast.parse(init_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    if isinstance(node.value, ast.Constant):
                        return str(node.value.value)
        elif isinstance(node, ast.Try):
            defines_version = any(
                isinstance(subnode, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "__version__"
                    for t in subnode.targets
                )
                for subnode in ast.walk(node)
            )
            if defines_version:
                mod = ast.Module(body=[node], type_ignores=[])
                ast.fix_missing_locations(mod)
                code_obj = compile(mod, filename=str(init_py), mode="exec")
                namespace: dict[str, object] = {"__file__": str(init_py)}
                try:
                    exec(code_obj, namespace)  # noqa: S102
                    version = namespace.get("__version__")
                    if isinstance(version, str):
                        return version
                except Exception:  # noqa: BLE001
                    pass
    return "unknown"


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
