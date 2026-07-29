"""Regression: LLM_MAX_OUTPUT_TOKENS-Default in den Sim-Runnern.

Hintergrund: Mit 8192 als Default kam es bei Multi-Agent-Workloads und
großem num_ctx zu silent Truncation (CAMEL-Issue). Default seit
2026-05-16: 16384. Kein Subprocess-Spawn — die Konstante wird direkt
aus dem Source gelesen.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# _create_model ist mit dem SinglePlatformRunner-Refactor in die Basis
# sim_runtime/platform_runner.py gewandert; der Default lebt jetzt dort als
# Single Source of Truth (dünne Entry-Points erben unverändert).
SCRIPTS = (
    "backend/scripts/sim_runtime/platform_runner.py",
)

_PATTERN = re.compile(
    r'os\.environ\.get\(\s*"LLM_MAX_OUTPUT_TOKENS"\s*,\s*"(?P<default>\d+)"\s*\)'
)


@pytest.mark.parametrize("rel_path", SCRIPTS)
def test_llm_max_output_tokens_default_is_16384(rel_path: str) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    src = (repo_root / rel_path).read_text(encoding="utf-8")
    match = _PATTERN.search(src)
    assert match, f"LLM_MAX_OUTPUT_TOKENS-Default nicht gefunden in {rel_path}"
    assert match.group("default") == "16384", (
        f"{rel_path}: erwartet Default 16384, gefunden {match.group('default')!r}"
    )
