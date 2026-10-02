"""Ratchet und Schönungs-Check fuer das Backend-Coverage-Gate (Issue #1671).

Entscheidung #1667: Die Coverage-Schwellen duerfen gegenueber ``v0.9.6`` nur
steigen, und die Quote darf nicht durch Scope-Verkleinerung geschoent werden
(neue ``omit``-Eintraege, engere ``source``, mehr ``pragma: no cover`` oder
Test-Skips ohne begruendeten Allowlist-Eintrag).

Geprueft wird ``scripts/check_coverage.py --integrity`` gegen zwei
eingespeiste Verzeichnisbaeume: Referenzstand und Iststand. Der echte
Vergleich gegen den Git-Tag laeuft als eigener CI-Step.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_coverage.py"
CI_WORKFLOW = REPO_ROOT.parent / ".github" / "workflows" / "ci.yml"
PRE_PUSH_GATE = REPO_ROOT.parent / "scripts" / "pre-push-gate.sh"

_PYPROJECT = """\
[project]
name = "fixture"

[tool.coverage.run]
source = ["app"]
{run_extra}

[tool.coverage.report]
show_missing = true
"""

_APP = """\
def answer() -> int:
    return 42


if __name__ == "__main__":{pragma}
    answer()
"""

_TEST = """\
import pytest

from app.core import answer

{marker}def test_answer() -> None:
    assert answer() == 42
"""

# Zusammengesetzt, damit diese Datei selbst nicht als neue Ausnahme zaehlt:
# der Schönungs-Check liest den Quelltext, nicht den Syntaxbaum.
_PRAGMA = "  # " + "pragma: no cover"
_SKIP = "@pytest.mark." + 'skipif(True, reason="fixture")\n'
_IMPERATIVE_SKIP = "    pytest." + 'skip("fixture")\n'


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("check_coverage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_coverage"] = module
    spec.loader.exec_module(module)
    return module


def _tree(
    root: Path,
    *,
    run_extra: str = "",
    pragma: bool = False,
    skip: bool = False,
    line_min: float = 82.8,
    branch_min: float = 70.9,
    baseline_extra: dict | None = None,
) -> Path:
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text(_PYPROJECT.format(run_extra=run_extra), encoding="utf-8")
    (root / "app" / "core.py").write_text(
        _APP.format(pragma=_PRAGMA if pragma else ""), encoding="utf-8"
    )
    (root / "tests" / "test_core.py").write_text(
        _TEST.format(marker=_SKIP if skip else ""), encoding="utf-8"
    )
    baseline = {"line_min": line_min, "branch_min": branch_min, **(baseline_extra or {})}
    (root / "coverage-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    return root


def _check(gate, reference: Path, current: Path) -> int:
    return gate.main(
        ["--integrity", "--root", str(current), "--reference-dir", str(reference)]
    )


@pytest.fixture
def reference(tmp_path: Path) -> Path:
    return _tree(tmp_path / "reference")


class TestUnchangedScopePasses:
    def test_identical_trees_pass(self, gate, reference, tmp_path) -> None:
        current = _tree(tmp_path / "current")

        assert _check(gate, reference, current) == 0

    def test_raised_thresholds_pass(self, gate, reference, tmp_path) -> None:
        current = _tree(tmp_path / "current", line_min=84.0, branch_min=72.0)

        assert _check(gate, reference, current) == 0


class TestCoverageConfigCannotShrink:
    def test_new_omit_entry_fails(self, gate, reference, tmp_path, capsys) -> None:
        current = _tree(tmp_path / "current", run_extra='omit = ["app/legacy/*"]')

        assert _check(gate, reference, current) == 1
        assert "app/legacy/*" in capsys.readouterr().out

    def test_narrowed_source_fails(self, gate, reference, tmp_path) -> None:
        current = _tree(tmp_path / "current")
        pyproject = current / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8").replace(
                'source = ["app"]', 'source = ["app/api"]'
            ),
            encoding="utf-8",
        )

        assert _check(gate, reference, current) == 1

    def test_new_exclude_line_fails(self, gate, reference, tmp_path) -> None:
        current = _tree(tmp_path / "current")
        pyproject = current / "pyproject.toml"
        pyproject.write_text(
            pyproject.read_text(encoding="utf-8")
            + 'exclude_also = ["def __repr__"]\n',
            encoding="utf-8",
        )

        assert _check(gate, reference, current) == 1

    def test_new_coveragerc_fails(self, gate, reference, tmp_path) -> None:
        """Eine ``.coveragerc`` hat Vorrang vor ``pyproject.toml`` und koennte
        den Scope an der Pruefung vorbei verkleinern."""
        current = _tree(tmp_path / "current")
        (current / ".coveragerc").write_text("[run]\nomit = app/*\n", encoding="utf-8")

        assert _check(gate, reference, current) == 1


class TestExclusionsCannotGrowSilently:
    def test_additional_pragma_fails(self, gate, reference, tmp_path, capsys) -> None:
        current = _tree(tmp_path / "current", pragma=True)

        assert _check(gate, reference, current) == 1
        assert "app/core.py" in capsys.readouterr().out

    def test_additional_skip_mark_fails(self, gate, reference, tmp_path) -> None:
        current = _tree(tmp_path / "current", skip=True)

        assert _check(gate, reference, current) == 1

    def test_additional_imperative_skip_fails(self, gate, reference, tmp_path) -> None:
        """Ein Skip-Aufruf im Testkoerper ist derselbe Hebel wie die Marke."""
        current = _tree(tmp_path / "current")
        test = current / "tests" / "test_core.py"
        test.write_text(
            test.read_text(encoding="utf-8").replace(
                "    assert answer()", _IMPERATIVE_SKIP + "    assert answer()"
            ),
            encoding="utf-8",
        )

        assert _check(gate, reference, current) == 1

    def test_allowlisted_pragma_with_reason_passes(self, gate, reference, tmp_path) -> None:
        current = _tree(
            tmp_path / "current",
            pragma=True,
            baseline_extra={
                "scope_allowlist": [
                    {
                        "file": "app/core.py",
                        "kind": "pragma",
                        "count": 1,
                        "reason": "CLI-Einstieg, nur manuell ausgefuehrt",
                    }
                ]
            },
        )

        assert _check(gate, reference, current) == 0

    def test_allowlist_entry_without_reason_fails(self, gate, reference, tmp_path) -> None:
        current = _tree(
            tmp_path / "current",
            pragma=True,
            baseline_extra={
                "scope_allowlist": [
                    {"file": "app/core.py", "kind": "pragma", "count": 1, "reason": " "}
                ]
            },
        )

        assert _check(gate, reference, current) == 1

    def test_stale_allowlist_entry_fails(self, gate, reference, tmp_path) -> None:
        """Ein Eintrag fuer eine Ausnahme, die es nicht mehr gibt, waere
        Freibetrag fuer die naechste — er muss mit der Ausnahme verschwinden."""
        current = _tree(
            tmp_path / "current",
            baseline_extra={
                "scope_allowlist": [
                    {
                        "file": "app/core.py",
                        "kind": "pragma",
                        "count": 1,
                        "reason": "laengst entfernt",
                    }
                ]
            },
        )

        assert _check(gate, reference, current) == 1


class TestThresholdRatchet:
    def test_lowered_line_threshold_fails(self, gate, reference, tmp_path, capsys) -> None:
        current = _tree(tmp_path / "current", line_min=80.0)

        assert _check(gate, reference, current) == 1
        assert "line_min" in capsys.readouterr().out

    def test_lowered_branch_threshold_fails(self, gate, reference, tmp_path) -> None:
        current = _tree(tmp_path / "current", branch_min=65.0)

        assert _check(gate, reference, current) == 1

    def test_lowering_with_maintainer_approval_passes(self, gate, reference, tmp_path) -> None:
        current = _tree(
            tmp_path / "current",
            line_min=80.0,
            baseline_extra={
                "lowering_approval": {
                    "approved_by": "arn0ld87",
                    "reason": "Grosse Neumodule ohne Altlast-Tests, Plan in #9999",
                }
            },
        )

        assert _check(gate, reference, current) == 0

    def test_lowering_approval_without_reason_fails(self, gate, reference, tmp_path) -> None:
        current = _tree(
            tmp_path / "current",
            line_min=80.0,
            baseline_extra={"lowering_approval": {"approved_by": "arn0ld87", "reason": ""}},
        )

        assert _check(gate, reference, current) == 1


class TestWiring:
    def test_pr_gate_runs_the_integrity_check(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")
        pr_gate = workflow.split("  backend-pr-gate:", 1)[1].split("\n  frontend-pr-gate:", 1)[0]

        assert "scripts/check_coverage.py --integrity" in pr_gate
        assert "refs/tags/v0.9.6" in pr_gate

    def test_pre_push_gate_runs_the_integrity_check(self) -> None:
        assert "check_coverage.py --integrity" in PRE_PUSH_GATE.read_text(encoding="utf-8")
