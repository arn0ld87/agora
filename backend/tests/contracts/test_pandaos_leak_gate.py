"""Leak-Gate fuer den lokalen PandaOS-Block in AGENTS.md.

PandaOS schreibt lokal einen Block zwischen
``<!-- >>> pandaos-managed (do not edit) >>> -->`` und
``<!-- <<< pandaos-managed <<< -->`` an den Anfang von ``AGENTS.md``:
Codex-Session-Anweisungen mit maschinenspezifischen Hosts und Pfaden. Im
Haupt-Checkout versteckt ``skip-worktree`` die Aenderung vor ``git status``,
frische Worktrees haben das Bit nicht. PR #1539 hat den Block so ins
oeffentliche Repo committet.

``scripts/check_pandaos_managed_leak.sh`` prueft deshalb den Index, nicht die
Arbeitskopie. Diese Tests pinnen genau diese Semantik an einem Wegwerf-Repo
und zusaetzlich, dass das Gate in jedem Scope von ``pre-push-gate.sh`` und im
Pflicht-PR-Gate der CI laeuft.

Liegt in ``tests/contracts/``, weil nur dieses Verzeichnis im verpflichtenden
PR-Gate laeuft. Nur stdlib, aus demselben Grund wie in
``test_ci_gate_parity.py``.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LEAK_SCRIPT = REPO_ROOT / "scripts" / "check_pandaos_managed_leak.sh"
PRE_PUSH_GATE_PATH = REPO_ROOT / "scripts" / "pre-push-gate.sh"
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

MANAGED_BLOCK = (
    "<!-- >>> pandaos-managed (do not edit) >>> -->\n"
    "# PandaOS — Codex Session\n"
    "<!-- <<< pandaos-managed <<< -->\n\n"
)
REPO_RULES = "# AGENTS.md\n\nVerbindliche Regeln.\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, env=_isolated_env(repo), check=True, capture_output=True
    )


def _isolated_env(repo: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"HOME": str(repo), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return env


def _run_gate(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(LEAK_SCRIPT)],
        cwd=repo,
        env=_isolated_env(repo),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "AGENTS.md").write_text(REPO_RULES, encoding="utf-8")
    _git(tmp_path, "add", "AGENTS.md")
    return tmp_path


def test_clean_index_passes(repo: Path) -> None:
    result = _run_gate(repo)

    assert result.returncode == 0, result.stderr


def test_staged_managed_block_fails_and_names_the_file(repo: Path) -> None:
    (repo / "AGENTS.md").write_text(MANAGED_BLOCK + REPO_RULES, encoding="utf-8")
    _git(repo, "add", "AGENTS.md")

    result = _run_gate(repo)

    assert result.returncode == 1
    assert "AGENTS.md" in result.stderr


def test_managed_block_only_in_worktree_passes(repo: Path) -> None:
    # PandaOS darf den Block lokal pflegen; nur der Index zaehlt.
    (repo / "AGENTS.md").write_text(MANAGED_BLOCK + REPO_RULES, encoding="utf-8")

    result = _run_gate(repo)

    assert result.returncode == 0, result.stderr


def test_marker_quoted_inline_in_docs_passes(repo: Path) -> None:
    doc = repo / "runbook.md"
    doc.write_text(
        "Der Block beginnt mit `<!-- >>> pandaos-managed (do not edit) >>> -->`.\n",
        encoding="utf-8",
    )
    _git(repo, "add", "runbook.md")

    result = _run_gate(repo)

    assert result.returncode == 0, result.stderr


def _scope_dispatch_lines() -> dict[str, str]:
    text = PRE_PUSH_GATE_PATH.read_text(encoding="utf-8")
    block = text[text.index('case "$SCOPE" in') : text.index("esac")]
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"^\s*([a-z]+)\)\s*(.+?);;\s*$", block, re.MULTILINE)
    }


def test_every_pre_push_scope_runs_the_leak_gate() -> None:
    scopes = _scope_dispatch_lines()

    assert {"all", "backend", "frontend", "schemas", "routing"} <= scopes.keys()
    missing = [scope for scope, body in scopes.items() if "run_leak" not in body]
    assert missing == [], f"Scopes ohne run_leak: {missing}"


def test_ci_pr_gate_runs_the_leak_gate() -> None:
    lines = CI_WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    start = lines.index("  backend-pr-gate:")
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^  [A-Za-z0-9_-]+:$", lines[i])),
        len(lines),
    )

    assert any("scripts/check_pandaos_managed_leak.sh" in line for line in lines[start:end])
