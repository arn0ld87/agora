"""Regressionstest für die Fehlermeldung des Jev-Benchmark-Runners
(f005, Slice `jev-benchmark`, Review-Task `minimal-failure-check`).

Der Review dieses Slices hat zwei echte Mängel am Runner gefunden: er
beendete sich auch dann mit Exit-Code 0, wenn jeder einzelne Jev-Aufruf
fehlgeschlagen war, und er hätte bei TEILWEISEM Ausfall eine
Jev-Accuracy über nur die geglückten Aufrufe neben der Rule-Accuracy
über alle Fälle gedruckt — zwei verschiedene Grundgesamtheiten, die
nebeneinander vergleichbar aussehen. Beides ist hier festgenagelt.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "jev_benchmark_local_search.py"


def _load_script():
    """Muster aus ``test_check_complexity.py``: ``scripts/`` ist kein
    importierbares Paket, Skripte werden per Dateipfad geladen.

    Zusatz gegenüber dort: das Modul muss VOR ``exec_module`` in
    ``sys.modules`` stehen, weil ``@dataclass`` beim Verarbeiten der
    Klassen ``sys.modules[cls.__module__]`` nachschlägt — ohne den
    Eintrag scheitert der Import an einem ``AttributeError``.
    """
    spec = importlib.util.spec_from_file_location("jev_benchmark_local_search", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = mod  # type: ignore[union-attr]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_BENCH = _load_script()
BenchmarkCase = _BENCH.BenchmarkCase
CaseOutcome = _BENCH.CaseOutcome
_print_report = _BENCH._print_report


def _outcome(
    case_id: str,
    *,
    rule_correct: bool = True,
    jev_correct: bool | None = None,
    jev_error: str | None = None,
) -> CaseOutcome:
    """Baut ein Ergebnis so, wie ``run()`` es tatsächlich befüllt: ein
    gesetztes ``jev_correct`` kommt dort immer mit einem ``jev_result``,
    weil beide aus demselben geglückten Aufruf stammen."""
    jev_result = (
        SimpleNamespace(probability_yes=0.9 if jev_correct else 0.1)
        if jev_correct is not None
        else None
    )
    return CaseOutcome(
        case=BenchmarkCase(case_id, "Query", "Fakt", True),
        top_score=20,
        rule_probability_yes=1.0,
        rule_correct=rule_correct,
        jev_result=jev_result,
        jev_correct=jev_correct,
        jev_latency_ms=120 if jev_correct is not None else None,
        jev_cost_micros=13 if jev_correct is not None else None,
        jev_error=jev_error,
    )


@pytest.fixture(autouse=True)
def _capture_bench_logger(caplog: pytest.LogCaptureFixture):
    """``app.utils.logger`` setzt ``propagate = False`` auf ``agora`` —
    ``agora.jev_benchmark`` erreicht den Root-Handler von ``caplog`` dann
    nie. Den Handler deshalb direkt am Benchmark-Logger einhängen."""
    bench_logger = logging.getLogger("agora.jev_benchmark")
    bench_logger.addHandler(caplog.handler)
    yield
    bench_logger.removeHandler(caplog.handler)


class TestBenchmarkReportUsability:
    def test_abbreviation_expansion_is_relevant_despite_rule_miss(self) -> None:
        case = next(c for c in _BENCH._CASES if c.case_id == "abbreviation-mismatch")
        score = _BENCH._match_score(case.query, case.fact)
        state = _BENCH.DecisionState(
            use_case_id=_BENCH._USE_CASE_ID,
            state={"top_score": score},
            context_hash="bench-abbreviation-mismatch",
        )

        assert case.expected_relevant is True
        assert score == 0
        assert _BENCH._rule_fn(state, _BENCH.NoulQuestion()).probability_yes == 0.0

    def test_skipped_jev_arm_is_a_usable_run(self, caplog: pytest.LogCaptureFixture) -> None:
        """Kein gebundener Key ist der dokumentierte Normalfall ohne Zugang,
        kein Fehlschlag — der Lauf liefert dann nur die Rule-Baseline."""
        caplog.set_level(logging.INFO, logger="agora.jev_benchmark")
        usable = _print_report([_outcome("a"), _outcome("b")])

        assert usable is True
        assert "Jev übersprungen" in caplog.text

    def test_fully_failed_jev_arm_is_not_a_usable_run(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger="agora.jev_benchmark")
        outcomes = [
            _outcome("a", jev_error="TypeSafeAuthenticationError: 401"),
            _outcome("b", jev_error="TypeSafeAuthenticationError: 401"),
        ]

        usable = _print_report(outcomes)

        assert usable is False
        out = caplog.text
        assert "FEHLGESCHLAGEN" in out
        # Keine ausgewiesene Quote — der Erklaertext nennt "Jev-Accuracy"
        # selbst, geprueft wird deshalb auf die Zahl, nicht auf das Wort.
        assert "Jev-Accuracy:" not in out

    def test_partially_failed_jev_arm_reports_no_comparable_accuracy(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Der gefährlichere Fall: ein Teil der Aufrufe glückt. Eine Quote
        über nur diese Teilmenge neben der Rule-Baseline über alle Fälle
        wäre eine stille Falschaussage."""
        caplog.set_level(logging.INFO, logger="agora.jev_benchmark")
        outcomes = [
            _outcome("ok-1", jev_correct=True),
            _outcome("ok-2", jev_correct=True),
            _outcome("fail-1", jev_error="TypeSafeAPIError: 429"),
        ]

        usable = _print_report(outcomes)

        assert usable is False
        out = caplog.text
        assert "Jev-Accuracy:" not in out
        assert "429" in out

    def test_clean_jev_arm_reports_accuracy_and_is_usable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger="agora.jev_benchmark")
        outcomes = [
            _outcome("a", jev_correct=True),
            _outcome("b", jev_correct=False),
        ]

        usable = _print_report(outcomes)

        assert usable is True
        assert "Jev-Accuracy: 50% (1/2)" in caplog.text
