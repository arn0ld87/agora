"""Minimaler Jev-Benchmark für den Use Case `local-search-relevance` (f005,
Slice `jev-benchmark`).

Scope-Entscheidung (Alex, 2026-09-21, im laufenden Task): kein
mehrtägiger, statistisch abgesicherter Benchmark mit Power-Analyse,
Kalibrations-/Test-Split-Trennung oder Latenz-unter-Last-Messung
(``docs/research/f005/benchmark-design.md`` beschreibt diesen größeren
Umfang für eine spätere, eigene Iteration). Dieses Skript ist das
absolute Minimum, um den echten Vergleich einmal laufen zu lassen:
kleine Fallmenge, ein Lauf, rohe Zahlen.

**Ground Truth ist NICHT maintainer-geprüft.** Die Spezifikation
verlangt das für einen belastbaren Benchmark ausdrücklich
(„mindestens eine Stichprobe pro Use Case wird manuell durch den
Maintainer gegengeprüft"); die Fälle unten sind vom Implementierer
konstruiert, nicht aus einem echten AGORA-Lauf gezogen (kein
Produktionsgraph vorhanden — nur Testdaten, siehe Projekt-Memory). Der
Bericht dieses Skripts ist deshalb ein Anhaltspunkt, keine Freigabe für
`authoritative`.

Aufruf:
    cd backend && uv run python scripts/jev_benchmark_local_search.py

Ohne gebundenen Jev-Key läuft nur die Rule-Baseline; der Jev-Arm wird
sichtbar als "übersprungen" markiert, nicht stillschweigend weggelassen.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from app.contracts.decision_contract import (
    DecisionQuestion,
    DecisionResult,
    DecisionState,
    NoulQuestion,
)
from app.services.decisions.jev_provider import build_jev_client, resolve_jev_api_key
from app.services.decisions.jev_provider import JevDecisionProvider
from app.services.decisions.local_search_shadow import _relevance_rule
from app.services.decisions.rule_provider import RuleOutcome, RuleProvider

_USE_CASE_ID = "local-search-relevance"


def _rule_fn(state: DecisionState, question: DecisionQuestion) -> RuleOutcome:
    """Ruft die produktive Regel auf — dieselbe wie in
    ``local_search_shadow.py``, nur mit der breiteren ``RuleFn``-Signatur,
    die ``RuleProvider`` erwartet (``_relevance_rule`` ist auf
    ``NoulQuestion`` verengt, weil sie nur dort gebraucht wird)."""
    assert isinstance(question, NoulQuestion)
    return _relevance_rule(state, question)


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    query: str
    fact: str
    expected_relevant: bool


# Konstruierte Fälle (siehe Moduldocstring: nicht maintainer-geprüft).
# top_score wird wie in graph_reader.py::local_search berechnet: 100 bei
# exaktem Query-Treffer, sonst 10 je getroffenem Keyword (>1 Zeichen).
_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        "exact-match",
        "Bundeskanzleramt",
        "Das Bundeskanzleramt koordiniert die Ressortabstimmung.",
        True,
    ),
    BenchmarkCase(
        "keyword-overlap",
        "Bundesministerium Finanzen",
        "Das Bundesministerium der Finanzen legt den Haushaltsentwurf vor.",
        True,
    ),
    BenchmarkCase(
        "no-overlap",
        "Bundeskanzleramt",
        "Der Stadtrat von München beschließt eine neue Verkehrsordnung.",
        False,
    ),
    BenchmarkCase(
        "coincidental-substring",
        "Rat",
        "Der Vorrat an Ersatzteilen im Lager reicht bis zum Quartalsende.",
        False,
    ),
    BenchmarkCase(
        "partial-relevant",
        "Bundestag Ausschuss",
        "Der Ausschuss für Digitales tagte am Dienstag im Bundestag.",
        True,
    ),
    BenchmarkCase(
        "different-institution",
        "Bundeskanzleramt",
        "Der Bayerische Landtag debattierte über die Schulreform.",
        False,
    ),
    BenchmarkCase(
        "single-keyword-weak-match",
        "Bundeskanzleramt Pressekonferenz",
        "Die Pressekonferenz des Vereins fand im Rathaus statt.",
        False,
    ),
    BenchmarkCase(
        "long-fact-relevant",
        "Bundesministerium Digitales",
        "Nach monatelangen Verhandlungen hat das Bundesministerium für "
        "Digitales und Verkehr ein neues Foerderprogramm fuer laendliche "
        "Breitbandanbindung vorgestellt, das ab dem naechsten Quartal gilt.",
        True,
    ),
    BenchmarkCase(
        "abbreviation-mismatch",
        "BMF",
        "Das Bundesministerium der Finanzen veroeffentlichte den Bericht.",
        True,  # BMF bezeichnet das Bundesministerium der Finanzen; die Keyword-Regel erkennt das nicht.
    ),
    BenchmarkCase(
        "negation-in-fact",
        "Bundeskanzleramt Stellungnahme",
        "Das Bundeskanzleramt hat bislang KEINE Stellungnahme abgegeben.",
        True,  # Thematisch relevant, obwohl der Inhalt eine Nicht-Aussage ist.
    ),
    BenchmarkCase(
        "different-topic-shared-word",
        "Bundeskanzleramt Sicherheit",
        "Die IT-Sicherheit des Unternehmens wurde nach einem Vorfall extern geprueft.",
        False,
    ),
    BenchmarkCase(
        "multi-entity-relevant",
        "Bundeskanzleramt Bundestag",
        "Vertreter des Bundeskanzleramts trafen sich mit Abgeordneten im Bundestag.",
        True,
    ),
]


def _match_score(query: str, fact: str) -> int:
    """Dieselbe Regel wie ``graph_reader.py::local_search.match_score``."""
    query_lower = query.lower()
    fact_lower = fact.lower()
    if query_lower in fact_lower:
        return 100
    keywords = [w.strip() for w in query_lower.replace(",", " ").split() if len(w.strip()) > 1]
    return sum(10 for kw in keywords if kw in fact_lower)


@dataclass
class CaseOutcome:
    case: BenchmarkCase
    top_score: int
    rule_probability_yes: float
    rule_correct: bool
    jev_result: DecisionResult | None
    jev_correct: bool | None
    jev_latency_ms: int | None
    jev_cost_micros: int | None
    jev_error: str | None


def run() -> list[CaseOutcome]:
    rule_provider = RuleProvider(use_case_id=_USE_CASE_ID, rule_fn=_rule_fn)

    jev_provider: JevDecisionProvider | None = None
    if resolve_jev_api_key():
        jev_provider = JevDecisionProvider(build_jev_client())

    outcomes: list[CaseOutcome] = []
    for case in _CASES:
        top_score = _match_score(case.query, case.fact)
        state = DecisionState(
            use_case_id=_USE_CASE_ID,
            state={"top_score": top_score},
            context_hash=f"bench-{case.case_id}",
        )
        rule_result = rule_provider.decide(state, NoulQuestion())
        rule_predicted = rule_result.probability_yes is not None and rule_result.probability_yes >= 0.5
        rule_correct = rule_predicted == case.expected_relevant

        jev_result: DecisionResult | None = None
        jev_correct: bool | None = None
        jev_latency_ms: int | None = None
        jev_cost_micros: int | None = None
        jev_error: str | None = None
        if jev_provider is not None:
            # Der reale Jev-Aufruf bekommt Query+Fakt im Klartext (nicht nur
            # top_score) — sonst hat er keinen Inhalt, über den er urteilen
            # kann. Das ist eine andere State-Form als im produktiven
            # Shadow-Pfad (local_search_shadow.py), der bewusst nur
            # top_score sendet; dieses Skript testet Jevs Eignung isoliert,
            # nicht den produktiven Aufrufpfad.
            jev_state = DecisionState(
                use_case_id=_USE_CASE_ID,
                state={"query": case.query, "fact": case.fact},
                context_hash=f"bench-{case.case_id}",
            )
            try:
                jev_result = jev_provider.decide(jev_state, NoulQuestion())
                jev_predicted = jev_result.probability_yes is not None and jev_result.probability_yes >= 0.5
                jev_correct = jev_predicted == case.expected_relevant
                jev_latency_ms = jev_result.latency_ms
                jev_cost_micros = jev_result.cost_micros
            except Exception as exc:  # noqa: BLE001 - Benchmark-Skript, Fehler sollen sichtbar im Bericht landen
                jev_error = f"{type(exc).__name__}: {exc}"

        outcomes.append(
            CaseOutcome(
                case=case,
                top_score=top_score,
                rule_probability_yes=rule_result.probability_yes or 0.0,
                rule_correct=rule_correct,
                jev_result=jev_result,
                jev_correct=jev_correct,
                jev_latency_ms=jev_latency_ms,
                jev_cost_micros=jev_cost_micros,
                jev_error=jev_error,
            )
        )
    return outcomes


def _print_report(outcomes: list[CaseOutcome]) -> bool:
    """Gibt den Bericht aus und meldet zurück, ob er verwertbar ist.

    ``False`` heißt: der Jev-Arm wurde versucht, ist aber (teilweise oder
    ganz) fehlgeschlagen — das Ergebnis taugt dann nicht als Vergleich,
    und der Aufrufer beendet den Prozess mit einem Fehlercode. Ein
    übersprungener Jev-Arm (kein Key gebunden) ist dagegen kein Fehler,
    sondern der dokumentierte Normalfall ohne Zugang.
    """
    jev_ran = any(o.jev_result is not None or o.jev_error is not None for o in outcomes)

    print(f"# Jev-Benchmark: local-search-relevance ({len(outcomes)} Fälle)\n")
    print(
        "| Fall | Query | top_score | erwartet | Rule | Jev-P(ja) | Jev korrekt | Kosten (µ$) | Latenz (ms) |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for o in outcomes:
        jev_p = f"{o.jev_result.probability_yes:.2f}" if o.jev_result else (o.jev_error or "—")
        jev_ok = "n/a" if o.jev_correct is None else ("✓" if o.jev_correct else "✗")
        cost = "—" if o.jev_cost_micros is None else str(o.jev_cost_micros)
        latency = "—" if o.jev_latency_ms is None else str(o.jev_latency_ms)
        print(
            f"| {o.case.case_id} | {o.case.query!r} | {o.top_score} | "
            f"{'ja' if o.case.expected_relevant else 'nein'} | "
            f"{'✓' if o.rule_correct else '✗'} | {jev_p} | {jev_ok} | {cost} | {latency} |"
        )

    rule_accuracy = sum(o.rule_correct for o in outcomes) / len(outcomes)
    print(f"\nRule-Baseline-Accuracy: {rule_accuracy:.0%} ({sum(o.rule_correct for o in outcomes)}/{len(outcomes)})")

    if not jev_ran:
        print(
            "\nJev übersprungen: kein API-Key im Provider-Secret-Store unter 'jev' gebunden."
        )
        return True

    jev_evaluated = [o for o in outcomes if o.jev_correct is not None]
    jev_errors = [o for o in outcomes if o.jev_error is not None]

    if jev_errors:
        # Kein Vergleich auf Teilmengen: die Rule-Accuracy steht über allen
        # Fällen, eine Jev-Accuracy über nur den geglückten Aufrufen wäre
        # eine andere Grundgesamtheit. Nebeneinander gedruckt sähen beide
        # Zahlen vergleichbar aus, ohne es zu sein — genau die stille
        # Falschaussage, die dieser Lauf nicht produzieren darf.
        print(
            f"\nFEHLGESCHLAGEN: {len(jev_errors)} von {len(outcomes)} Jev-Aufrufen "
            "sind fehlgeschlagen. Es wird bewusst KEINE Jev-Accuracy ausgewiesen — "
            "eine Quote über nur die geglückten Aufrufe wäre nicht mit der "
            "Rule-Baseline über alle Fälle vergleichbar."
        )
        print(f"\nJev-Fehler ({len(jev_errors)}):")
        for o in jev_errors:
            print(f"  - {o.case.case_id}: {o.jev_error}")
        return False

    if jev_evaluated:
        jev_correct_count = sum(1 for o in jev_evaluated if o.jev_correct)
        jev_accuracy = jev_correct_count / len(jev_evaluated)
        print(f"Jev-Accuracy: {jev_accuracy:.0%} ({jev_correct_count}/{len(jev_evaluated)})")
        latencies = [o.jev_latency_ms for o in jev_evaluated if o.jev_latency_ms is not None]
        costs = [o.jev_cost_micros for o in jev_evaluated if o.jev_cost_micros is not None]
        if latencies:
            print(
                f"Jev-Latenz: median={statistics.median(latencies):.0f}ms, "
                f"max={max(latencies)}ms (kein p95/p99 — Fallmenge zu klein für Perzentile)"
            )
        if costs:
            print(f"Jev-Gesamtkosten: {sum(costs)} Mikro-USD über {len(costs)} Aufrufe")
    return True


if __name__ == "__main__":
    t0 = time.monotonic()
    results = run()
    usable = _print_report(results)
    print(f"\nGesamtlaufzeit: {time.monotonic() - t0:.1f}s")
    # Exit-Code statt nur Text: ein fehlgeschlagener Jev-Arm darf nicht als
    # erfolgreicher Lauf durchgehen, wenn dieses Skript aus einem Wrapper
    # oder einer Pipeline heraus aufgerufen wird.
    raise SystemExit(0 if usable else 1)
