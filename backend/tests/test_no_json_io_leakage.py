"""Constraint guard for Issue #13: services/ and api/ may not import json_io.

Only the SimulationArtifactStore adapter (``services/artifact_store.py``) and
the explicitly-out-of-scope ``services/run_registry.py`` (separate refactor PR)
are allowed consumers. The smoke test fails fast if anything else starts
calling ``utils.json_io`` directly again.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [REPO_ROOT / "app" / "services", REPO_ROOT / "app" / "api"]

# Files that are explicitly allowed to import json_io. Keep this list tiny.
ALLOWED = {
    REPO_ROOT / "app" / "services" / "artifact_store.py",
    # run_registry is migrated in a separate PR (different storage root, own
    # concurrency model). Tracked in the Issue #13 plan as out-of-scope.
    REPO_ROOT / "app" / "services" / "run_registry.py",
}


def _imports_json_io(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "json_io" in node.module:
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "json_io" in alias.name:
                    return True
    return False


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_DIRS:
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_no_json_io_imports_in_services_or_api():
    offenders = []
    for path in _python_files():
        if path in ALLOWED:
            continue
        if _imports_json_io(path):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "json_io must only be consumed by the SimulationArtifactStore adapter. "
        "Offenders: " + ", ".join(offenders)
    )


@pytest.mark.parametrize("path", sorted(ALLOWED))
def test_allowlisted_file_exists(path):
    """Sanity-check the allowlist itself (broken paths would silently weaken the test)."""
    assert path.exists(), f"Allowlisted path missing: {path}"
