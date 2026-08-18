"""Deterministischer Vorabruf numerischer Evidence.

Das Evidence-Retrieval ist embedding-basiert und verwirft alles unter einer
Cosine-Schwelle. Für Fließtext ist das richtig — für Zahlen ist es das nicht.
Im Referenzlauf ``report_cc2ef45da5e9`` standen "mindestens 80 Prozent
Schulungsquote", "38 abweichende Dringlichkeitsfälle" und "maximal 15 Minuten
manueller Fallback" im kanonischen Evidence-Index, und der Bericht meldete
trotzdem "numerischer Claim ohne passenden Zahlenbeleg". Die Quellen sagten
dasselbe in anderen Worten; ihr Cosine-Wert blieb unter der Schwelle, und sie
erreichten die inhaltliche Prüfung nie.

Eine Zahl braucht dafür kein Embedding. ``54`` ist ``54``. Dieses Modul
beantwortet deshalb die reine Retrieval-Frage — *welche Quellen nennen
überhaupt dieselbe Zahl?* — deterministisch und nachvollziehbar, bevor ein
semantisches Urteil überhaupt gefragt ist.

Was es ausdrücklich **nicht** tut: entscheiden, ob eine Quelle den Claim
belegt. Dieselbe Zahl für eine andere Bezugsgruppe ist kein Beleg, und das
bleibt Sache von :mod:`app.services.evidence_entailment`. Der Vorabruf
erweitert nur die Menge der Quellen, die dort überhaupt geprüft werden.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .evidence_entailment import NumericFact, extract_numeric_facts

#: Toleranz beim Wertvergleich. Zahlen stammen aus derselben Extraktion und
#: sind nicht gerundet — die Schwelle fängt nur Fließkomma-Rauschen ab.
_VALUE_EPSILON = 0.001


def _facts_of(text: str) -> List[NumericFact]:
    return extract_numeric_facts(text or "")


def _same_value(left: NumericFact, right: NumericFact) -> bool:
    return left.unit == right.unit and abs(left.value - right.value) < _VALUE_EPSILON


def shares_numeric_fact(claim_text: str, evidence_text: str) -> bool:
    """Nennen beide Texte dieselbe Zahl in derselben Einheit?

    Bewusst nur der Wert, nicht die Bezugsgruppe: Die Frage lautet "lohnt es
    sich, diese Quelle inhaltlich zu prüfen?", nicht "belegt sie den Claim?".
    Ein Filter, der hier schon die Bezugsgruppe verlangt, hätte im
    Referenzlauf dieselben Belege verworfen wie das Embedding — Bezugsgruppen
    sind genau das, was zwischen Bericht und Quelle unterschiedlich
    formuliert ist.
    """
    claim_facts = _facts_of(claim_text)
    if not claim_facts:
        return False
    evidence_facts = _facts_of(evidence_text)
    return any(
        _same_value(claim_fact, evidence_fact)
        for claim_fact in claim_facts
        for evidence_fact in evidence_facts
    )


def numeric_candidates(
    claim_text: str,
    candidates: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Die Kandidaten, die eine Zahl des Claims wörtlich nennen.

    Reihenfolge der Eingabe bleibt erhalten. Ein Claim ohne Zahlen liefert
    eine leere Liste — dann ist dieser Pfad schlicht nicht zuständig.
    """
    if not _facts_of(claim_text):
        return []

    from .evidence_binder import candidate_text  # noqa: PLC0415 — zirkulärer Import

    return [
        item
        for item in candidates
        if shares_numeric_fact(claim_text, candidate_text(item))
    ]


def source_mentions_claim_numbers(
    claim_text: str,
    evidence_pool: Sequence[Dict[str, Any]],
) -> bool:
    """Kommt irgendeine Zahl des Claims in irgendeiner Quelle vor?

    Grundlage der Data-Gap-Semantik: eine Zahl, die in den Quellen steht, ist
    keine fehlende Information. Scheitert die Bindung trotzdem, ist das ein
    Bindungsfehler und keine Lücke in der Datenlage.
    """
    return bool(numeric_candidates(claim_text, evidence_pool))


__all__ = [
    "numeric_candidates",
    "shares_numeric_fact",
    "source_mentions_claim_numbers",
]
