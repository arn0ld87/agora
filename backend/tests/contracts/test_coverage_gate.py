"""Vertragstests fuer das Coverage-Gate (Issue #1495, Befund N).

Die alte Schwelle ``--cov-fail-under=60`` lag 24 Punkte unter dem tatsaechlichen
Ist und konnte deshalb keine Regression erkennen: die halbe Testsuite haette
wegfallen koennen, ohne dass CI rot wird. Branch-Coverage wurde gar nicht
gemessen.

Kein echter Coverage-Lauf hier (der dauert ~5 Minuten) — geprueft wird die
Gate-Logik gegen eingespeiste Reports plus die Verdrahtung in CI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_coverage.py"
BASELINE = REPO_ROOT / "coverage-baseline.json"
CI_WORKFLOW = REPO_ROOT.parent / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("check_coverage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_coverage"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _report(tmp_path: Path, *, line: float, branch: float) -> Path:
    statements, branches = 10_000, 10_000
    payload = {
        "totals": {
            "num_statements": statements,
            "covered_lines": round(statements * line / 100),
            "num_branches": branches,
            "covered_branches": round(branches * branch / 100),
        }
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(gate, monkeypatch, report: Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_coverage.py", "--report", str(report)])
    return gate.main()


class TestBaselineIsRealistic:
    def test_thresholds_are_close_to_the_measured_values(self, baseline) -> None:
        """"Realer Wert minus hoechstens ein Prozentpunkt" — eine Schwelle weit
        unter dem Ist erkennt keine Regression."""
        assert 82.0 <= baseline["line_min"] <= 83.82
        assert 70.0 <= baseline["branch_min"] <= 71.94

    def test_branch_threshold_is_not_a_wish_number(self, baseline) -> None:
        """71.94 % ist gemessen. 80 % waere erfunden und haette das Gate
        entweder sofort rot gefaerbt oder Tests provoziert, die Zweige
        beruehren statt Verhalten zu pruefen."""
        assert baseline["branch_min"] < 80

    def test_thresholds_are_clearly_above_the_old_sixty_percent(self, baseline) -> None:
        assert baseline["line_min"] > 60


class TestGateReactsToRegression:
    def test_current_values_pass(self, gate, baseline, monkeypatch, tmp_path) -> None:
        report = _report(tmp_path, line=83.82, branch=71.94)

        assert _run(gate, monkeypatch, report) == 0

    def test_line_coverage_below_threshold_fails(
        self, gate, baseline, monkeypatch, tmp_path
    ) -> None:
        report = _report(tmp_path, line=baseline["line_min"] - 0.5, branch=71.94)

        assert _run(gate, monkeypatch, report) == 1

    def test_branch_coverage_below_threshold_fails(
        self, gate, baseline, monkeypatch, tmp_path
    ) -> None:
        report = _report(tmp_path, line=83.82, branch=baseline["branch_min"] - 0.5)

        assert _run(gate, monkeypatch, report) == 1

    def test_a_sixty_percent_run_would_now_fail(
        self, gate, monkeypatch, tmp_path
    ) -> None:
        """Der Zustand, den die alte Schwelle noch durchgelassen haette."""
        report = _report(tmp_path, line=60.0, branch=45.0)

        assert _run(gate, monkeypatch, report) == 1

    def test_report_without_branch_data_is_rejected(
        self, gate, monkeypatch, tmp_path
    ) -> None:
        """Ein Lauf ohne --cov-branch darf nicht als bestanden durchgehen —
        sonst prueft das Gate stillschweigend nur die Haelfte."""
        path = tmp_path / "coverage.json"
        path.write_text(
            json.dumps(
                {
                    "totals": {
                        "num_statements": 100,
                        "covered_lines": 90,
                        "num_branches": 0,
                        "covered_branches": 0,
                    }
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(SystemExit):
            _run(gate, monkeypatch, path)


class TestWiring:
    def test_ci_measures_branch_coverage(self) -> None:
        assert "--cov-branch" in CI_WORKFLOW.read_text(encoding="utf-8")

    def test_ci_runs_the_gate(self) -> None:
        assert "scripts/check_coverage.py" in CI_WORKFLOW.read_text(encoding="utf-8")

    def test_the_old_blanket_threshold_is_gone(self) -> None:
        """Nur die ausgefuehrten Zeilen zaehlen — der Kommentar darueber nennt
        die alte Schwelle absichtlich, um die Aenderung zu begruenden."""
        executed = [
            line
            for line in CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("#")
        ]

        assert not [line for line in executed if "--cov-fail-under" in line]
