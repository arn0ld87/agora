"""Constraint guard for Issue #13: services/ and api/ may not import json_io.

Only the SimulationArtifactStore adapter (``services/artifact_store.py``) and
the Run-Registry file adapter ``services/file_run_store.py`` (#1579; the I/O
moved there out of ``run_registry.py``) and the personaset file adapter
``services/file_persona_set_store.py`` (#1807, behind PersonaSetRepository)
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
    # Run-Registry-Adapter hinter dem RunRepository-Port (#1579): eigenes
    # Ablageverzeichnis, eigenes Nebenlaeufigkeitsmodell. run_registry.py
    # selbst importiert json_io seitdem nicht mehr.
    REPO_ROOT / "app" / "services" / "file_run_store.py",
    # Personasatz-Dateiadapter hinter dem PersonaSetRepository-Port (#1807).
    # Domain-Service und API duerfen weiterhin kein json_io importieren.
    REPO_ROOT / "app" / "services" / "file_persona_set_store.py",
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
        "json_io must only be consumed by explicitly allowlisted file adapters. "
        "Offenders: " + ", ".join(offenders)
    )


def test_persona_set_file_adapter_is_an_explicit_port_boundary():
    """The file adapter is allowed, never its domain service or API consumer."""
    adapter = REPO_ROOT / "app" / "services" / "file_persona_set_store.py"
    assert adapter in ALLOWED
    assert _imports_json_io(adapter)
    assert REPO_ROOT / "app" / "services" / "persona_set_service.py" not in ALLOWED
    assert REPO_ROOT / "app" / "api" / "persona_sets.py" not in ALLOWED


@pytest.mark.parametrize("path", sorted(ALLOWED))
def test_allowlisted_file_exists(path):
    """Sanity-check the allowlist itself (broken paths would silently weaken the test)."""
    assert path.exists(), f"Allowlisted path missing: {path}"
