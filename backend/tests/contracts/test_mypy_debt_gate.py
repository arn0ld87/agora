"""Vertragstests fuer das Typ-Schuld-Gate (Issue #1495, Befund M).

Das Gate repariert keine Typfehler — es macht die von ``ignore_errors``
verdeckte Schuld sichtbar und haelt sie am Wachsen. Diese Tests sichern genau
die drei Eigenschaften, die es dafuer braucht: eine reproduzierbare Messung,
eine eingecheckte Baseline und einen Riegel gegen das Ausweichen in die
``ignore_errors``-Liste.

Bewusst ohne echten mypy-Lauf (der dauert ~40 s): geprueft wird die Logik des
Skripts gegen eingespeiste Messwerte.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_mypy_debt.py"
CONFIG = REPO_ROOT / "mypy-debt.ini"
BASELINE = REPO_ROOT / "mypy-debt-baseline.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOW = REPO_ROOT.parent / ".github" / "workflows" / "contract-gates.yml"
PRE_PUSH = REPO_ROOT.parent / "scripts" / "pre-push-gate.sh"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("check_mypy_debt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_mypy_debt"] = module
    spec.loader.exec_module(module)
    return module


class TestArtefactsExist:
    def test_measurement_config_and_baseline_are_checked_in(self) -> None:
        assert CONFIG.exists(), "mypy-debt.ini fehlt — die Messung waere nicht reproduzierbar"
        assert BASELINE.exists(), "mypy-debt-baseline.txt fehlt — es gaebe nichts zu vergleichen"

    def test_measurement_config_does_not_reintroduce_ignore_errors(self) -> None:
        """Der Sinn der Datei ist genau, diesen Block *nicht* zu haben.

        Geprueft werden echte Settings, nicht die Kommentare — die erwaehnen
        ``ignore_errors`` naturgemaess mehrfach.
        """
        settings = [
            line.strip()
            for line in CONFIG.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith((";", "#"))
        ]

        assert not [line for line in settings if line.startswith("ignore_errors")]

    def test_baseline_carries_the_current_ignore_errors_modules(self, gate) -> None:
        _counts, modules = gate.parse_baseline()

        assert set(modules) == set(gate.ignored_modules()), (
            "Baseline und pyproject.toml sind auseinandergelaufen — Baseline neu "
            "schreiben (scripts/check_mypy_debt.py --write)"
        )

    def test_baseline_is_not_empty(self, gate) -> None:
        """Eine leere Baseline wuerde jedes Wachstum durchlassen und gleichzeitig
        so aussehen, als gaebe es keine Schuld."""
        counts, _modules = gate.parse_baseline()

        assert sum(counts.values()) > 0
        assert counts


class TestGrowthIsBlocked:
    """Die eigentliche Wirkung: mehr Schuld faellt durch, weniger nicht."""

    def _run(self, gate, monkeypatch, counts: dict[str, int], modules=None) -> int:
        baseline_counts, baseline_modules = gate.parse_baseline()
        monkeypatch.setattr(gate, "measure", lambda: Counter(counts))
        monkeypatch.setattr(
            gate, "ignored_modules", lambda: modules if modules is not None else baseline_modules
        )
        monkeypatch.setattr(sys, "argv", ["check_mypy_debt.py"])
        del baseline_counts
        return gate.main()

    def test_unchanged_debt_passes(self, gate, monkeypatch) -> None:
        counts, _ = gate.parse_baseline()

        assert self._run(gate, monkeypatch, dict(counts)) == 0

    def test_more_errors_in_a_known_file_fails(self, gate, monkeypatch) -> None:
        counts, _ = gate.parse_baseline()
        worse = dict(counts)
        path = next(iter(worse))
        worse[path] += 1

        assert self._run(gate, monkeypatch, worse) == 1

    def test_a_newly_failing_file_fails(self, gate, monkeypatch) -> None:
        counts, _ = gate.parse_baseline()
        worse = dict(counts)
        worse["app/services/brand_new_module.py"] = 1

        assert self._run(gate, monkeypatch, worse) == 1

    def test_fewer_errors_pass_and_do_not_silently_lower_the_baseline(
        self, gate, monkeypatch
    ) -> None:
        counts, _ = gate.parse_baseline()
        better = dict(counts)
        path = next(iter(better))
        better[path] = max(0, better[path] - 1)
        before = BASELINE.read_text(encoding="utf-8")

        assert self._run(gate, monkeypatch, better) == 0
        assert BASELINE.read_text(encoding="utf-8") == before

    def test_growing_the_ignore_errors_list_fails(self, gate, monkeypatch) -> None:
        """Der offensichtliche Umgehungsweg: Modul abschalten statt typisieren."""
        counts, modules = gate.parse_baseline()

        exit_code = self._run(
            gate, monkeypatch, dict(counts), modules=[*modules, "app.brand_new.*"]
        )

        assert exit_code == 1


class TestWiring:
    def test_ci_runs_the_gate(self) -> None:
        assert "scripts/check_mypy_debt.py" in WORKFLOW.read_text(encoding="utf-8"), (
            "Das Gate laeuft nicht in CI — dann haelt es nichts auf"
        )

    def test_pre_push_gate_runs_it_too(self) -> None:
        assert "scripts/check_mypy_debt.py" in PRE_PUSH.read_text(encoding="utf-8")

    def test_regular_mypy_gate_is_still_in_place(self) -> None:
        """Das Schuld-Gate ergaenzt `mypy app`, es ersetzt es nicht."""
        assert "uv run mypy app" in PRE_PUSH.read_text(encoding="utf-8")

    def test_ignore_errors_block_still_exists_and_is_unchanged_in_shape(self) -> None:
        """Falls jemand ignore_errors entfernt, statt die Schuld zu tilgen, wird
        dieses Gate gegenstandslos — dann soll es auffallen."""
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        overrides = data["tool"]["mypy"]["overrides"]

        assert any(o.get("ignore_errors") for o in overrides)
