"""
check_version_drift.py — Version-Drift-Checker for Agora.

Canonical source of truth is the repo-root ``VERSION`` file. All other
version-bearing locations are compared against it:

  1. VERSION                          (canonical/authoritative source)
  2. backend/pyproject.toml
  3. root package.json
  4. frontend/package.json
  5. README.md badge (if present)
  6. backend/app/__init__.__version__ (importlib.metadata or pyproject fallback)

Exit 0 — all consistent.
Exit 1 — at least one mismatch detected (prints details to stderr).

Usage:
  uv run python scripts/check_version_drift.py        # from backend/
  python backend/scripts/check_version_drift.py       # from repo root

Use ``--write`` (alias ``--fix``) to synchronize every non-canonical source
to the version recorded in ``VERSION``:

  uv run python scripts/check_version_drift.py --write

``backend/app/__init__.py`` is never written — its ``__version__`` is derived
from installed package metadata (pyproject), not a literal to edit.
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


# MAJOR.MINOR.PATCH mit optionalem SemVer-Pre-Release/Build-Suffix.
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def read_version_file(repo_root: Path) -> str:
    version_file = repo_root / "VERSION"
    text = version_file.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"VERSION file is empty at {version_file}")
    if not _SEMVER_RE.match(text):
        raise ValueError(
            f"VERSION={text!r} is not a valid SemVer string "
            f"(MAJOR.MINOR.PATCH[-prerelease][+build]) at {version_file}"
        )
    return text


def read_pyproject_version(repo_root: Path) -> str:
    pyproject = repo_root / "backend" / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise ValueError(f"version not found in {pyproject}")
    return m.group(1)


def write_pyproject_version(repo_root: Path, version: str) -> None:
    pyproject = repo_root / "backend" / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^version\s*=\s*"([^"]+)"',
        f'version = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError(f"version not found in {pyproject}")
    pyproject.write_text(new_text, encoding="utf-8")


def read_package_json_version(repo_root: Path) -> str:
    pkg = repo_root / "package.json"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    return str(data["version"])


def _write_package_json_version(pkg: Path, version: str) -> None:
    """Patch the `"version": "..."` line in-place, preserving the rest of the
    file byte-for-byte (formatting, key order, unicode escaping)."""
    text = pkg.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'("version"\s*:\s*")[^"]*(")',
        rf"\g<1>{version}\g<2>",
        text,
        count=1,
    )
    if count == 0:
        raise ValueError(f'"version" key not found in {pkg}')
    pkg.write_text(new_text, encoding="utf-8")


def write_package_json_version(repo_root: Path, version: str) -> None:
    _write_package_json_version(repo_root / "package.json", version)


def read_frontend_package_json_version(repo_root: Path) -> str:
    pkg = repo_root / "frontend" / "package.json"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    return str(data["version"])


def write_frontend_package_json_version(repo_root: Path, version: str) -> None:
    _write_package_json_version(repo_root / "frontend" / "package.json", version)


def read_readme_badge_version(repo_root: Path) -> str | None:
    readme = repo_root / "README.md"
    text = readme.read_text(encoding="utf-8")
    # Matches: [![Version](https://img.shields.io/badge/Version-1.0.0-blue?...)](...)
    # (.+?) fasst auch Bindestrich-Versionen (Pre-Releases wie 0.8.0-rc.1),
    # da bis zum abschliessenden Farb-Suffix vor '?'/')' nicht-gierig gematcht wird.
    m = re.search(r"img\.shields\.io/badge/Version-(.+?)-\w+(?=[?)])", text)
    return m.group(1) if m else None


def write_readme_badge_version(repo_root: Path, version: str) -> None:
    readme = repo_root / "README.md"
    text = readme.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r"(img\.shields\.io/badge/Version-).+?(-\w+(?=[?)]))",
        rf"\g<1>{version}\g<2>",
        text,
        count=1,
    )
    if count == 0:
        # No badge present — nothing to write, not an error.
        return
    readme.write_text(new_text, encoding="utf-8")


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


def _collect_sources(repo_root: Path) -> tuple[dict[str, str], list[str]]:
    """Read every version source. Returns (sources, errors)."""
    errors: list[str] = []
    sources: dict[str, str] = {}

    try:
        sources["VERSION"] = read_version_file(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"VERSION: {exc}")

    try:
        sources["pyproject.toml"] = read_pyproject_version(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pyproject.toml: {exc}")

    try:
        sources["package.json"] = read_package_json_version(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"package.json: {exc}")

    try:
        sources["frontend/package.json"] = read_frontend_package_json_version(repo_root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"frontend/package.json: {exc}")

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

    return sources, errors


def write_all(repo_root: Path, version: str) -> None:
    """Synchronize every writable, non-canonical source to ``version``.

    ``backend/app/__init__.py`` is intentionally excluded — its
    ``__version__`` is derived from installed package metadata, not a
    literal to overwrite.
    """
    write_pyproject_version(repo_root, version)
    write_package_json_version(repo_root, version)
    write_frontend_package_json_version(repo_root, version)
    write_readme_badge_version(repo_root, version)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    do_write = "--write" in args or "--fix" in args

    repo_root = _repo_root()

    if do_write:
        try:
            write_target_version = read_version_file(repo_root)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR reading canonical VERSION file: {exc}", file=sys.stderr)
            return 1
        write_all(repo_root, write_target_version)
        print(f"OK: wrote version {write_target_version!r} to all non-canonical sources")
        return 0

    sources, errors = _collect_sources(repo_root)

    if errors:
        for e in errors:
            print(f"ERROR reading version source: {e}", file=sys.stderr)
        return 1

    canonical = sources.get("VERSION")
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
