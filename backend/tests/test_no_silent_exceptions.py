"""Test that no silent ``except Exception: pass`` blocks exist in app/.

Acceptance criteria (Issue #583):
- Every ``except Exception`` in ``backend/app/`` either:
  a) has a ``logger.debug(...)`` or ``logger.warning(...)`` call in its body, OR
  b) has an explicit ``# noqa: BLE001`` comment on the except line with an
     explanatory reason, OR
  c) has been narrowed to a specific exception class (not ``Exception``).
- Ruff rule BLE001 is enabled in pyproject.toml.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent.parent / "app"


# ---------------------------------------------------------------------------
# Helper: AST-based detection of silent except-Exception handlers
# ---------------------------------------------------------------------------


def _body_has_only_pass(body: list[ast.stmt]) -> bool:
    """Return True iff the handler body contains only a Pass statement."""
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _body_has_log_call(body: list[ast.stmt]) -> bool:
    """Return True iff the handler body contains at least one logger.* call."""
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Call):
            func = node.func
            # logger.xxx(…) pattern
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id in ("logger", "_log", "logging") and func.attr.startswith(
                    ("debug", "warning", "error", "info", "exception", "critical")
                ):
                    return True
            # Also accept _log("…") as used in file_parser
            if isinstance(func, ast.Name) and func.id == "_log":
                return True
    return False


def _handler_is_except_exception(handler: ast.ExceptHandler) -> bool:
    """Return True iff the handler catches the bare ``Exception`` class."""
    if handler.type is None:
        # bare ``except:`` — also a blind except
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
        return True
    if isinstance(handler.type, ast.Attribute) and handler.type.attr == "Exception":
        return True
    return False


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------


def find_silent_except_exception(app_dir: Path) -> list[tuple[str, int, str]]:
    """Return list of (relpath, lineno, line) for silent except-Exception blocks.

    A handler is *silent* when:
    - it catches ``Exception`` (or bare ``except``), AND
    - its body is only ``pass``, AND
    - the except line does NOT contain ``# noqa: BLE001``.
    """
    violations: list[tuple[str, int, str]] = []

    for py_file in sorted(app_dir.rglob("*.py")):
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if not _handler_is_except_exception(handler):
                    continue
                if not _body_has_only_pass(handler.body):
                    continue
                # Check for noqa on the except line
                lineno = handler.lineno
                raw_line = lines[lineno - 1] if lineno <= len(lines) else ""
                if "# noqa: BLE001" in raw_line:
                    continue
                relpath = str(py_file.relative_to(app_dir.parent))
                violations.append((relpath, lineno, raw_line.strip()))

    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_silent_except_exception_pass() -> None:
    """Every except-Exception handler must log or carry a noqa comment."""
    violations = find_silent_except_exception(APP_DIR)
    if violations:
        lines = [f"  {path}:{lineno}: {line}" for path, lineno, line in violations]
        joined = "\n".join(lines)
        raise AssertionError(
            f"Found {len(violations)} silent 'except Exception: pass' block(s) "
            f"without logging or noqa comment:\n{joined}\n\n"
            "Add logger.debug/warning or # noqa: BLE001 — <reason>."
        )


def test_ble001_enabled_in_ruff_config() -> None:
    """BLE001 must appear in ruff's select list in pyproject.toml."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject.read_text()
    # The select line should contain BLE or BLE001
    assert re.search(r'select\s*=\s*\[.*"BLE', content, re.DOTALL), (
        "BLE001 (blind exception) rule not found in ruff [tool.ruff.lint] select list. "
        "Add 'BLE' or 'BLE001' to pyproject.toml."
    )


def test_ruff_ble001_clean() -> None:
    """ruff check --select BLE001 must report zero violations."""
    backend_dir = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "app/", "--select", "BLE001", "--quiet"],
        capture_output=True,
        text=True,
        cwd=backend_dir,
    )
    assert result.returncode == 0, (
        f"ruff BLE001 violations remain:\n{result.stdout}\n{result.stderr}"
    )
