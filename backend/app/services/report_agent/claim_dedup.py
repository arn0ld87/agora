"""Derselbe Befund, siebenmal gesagt, bleibt ein Befund.

Über die sieben Abschnitte des Referenzlaufs ``report_cc2ef45da5e9`` verteilten
sich mehrfach praktisch identische Aussagen: dieselbe Schulungsquote, dieselbe
Fallback-Dauer, jeweils neu formuliert. Für den Leser sieht das aus wie
mehrfache Bestätigung — tatsächlich ist es dieselbe Quelle, siebenmal zitiert.

Zusammengeführt wird nur, was wirklich dasselbe ist. Die Spezifikation ist an
dieser Stelle ausdrücklich: unterschiedliche Populationen, Zeiträume,
Bedingungen oder Evidenzquellen dürfen nicht zusammenfallen. "31 % in der
Nachtschicht" und "54 % in der Pflege" sind zwei Aussagen, auch wenn sie
einander ähneln, und ein Claim aus zwei verschiedenen Quellen ist zweifach
belegt und nicht doppelt genannt.

Der Vergleich läuft in zwei Stufen. Hart und vorab: gleiche Zahlen in gleicher
Einheit, gleiche Belegmenge. Nur innerhalb dieser Gruppen entscheidet dann die
Wortüberlappung — hoch angesetzt, weil ein falsch verschmolzener Claim eine
Aussage löscht, ein doppelt genannter nur ermüdet.

Was der Ansatz nicht leistet, sagt er offen: eine Paraphrase mit anderem Verb
("erreichte" gegen "liegt bei") fällt durch. Sie zu fangen bräuchte ein
semantisches Urteil, und dessen Fehler wären unvorhersagbar — an dieser Stelle
wiegt das schwerer als die verbleibende Dublette.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from ..evidence_entailment import extract_numeric_facts

_STOPWORDS_MIN_LENGTH = 4

#: Wortüberlappung (Jaccard), ab der zwei gleich belegte Aussagen mit
#: denselben Zahlen als dieselbe gelten. Hoch angesetzt: unterhalb davon
#: verliert man eher eine eigenständige Aussage als eine Dublette.
CLAIM_SIMILARITY_THRESHOLD = 0.85


def _content_tokens(text: str) -> frozenset[str]:
    import re  # noqa: PLC0415 — nur hier gebraucht

    return frozenset(
        token[:6]
        for token in re.split(r"[^\wäöüßÄÖÜ]+", (text or "").lower())
        if len(token) >= _STOPWORDS_MIN_LENGTH
    )


def _numeric_signature(text: str) -> frozenset[Tuple[float, str]]:
    """Die Zahlen des Claims, mit Einheit.

    Bewusst ohne Bezugsgruppe und Teilpopulation. Beide werden aus der
    Wortstellung abgeleitet und fallen bei einer Umformulierung verschieden
    aus — sie machten den Schlüssel gegen genau die Paraphrasen blind, für die
    er da ist. Die Population steckt ohnehin schon in den Inhaltswörtern: "in
    der Pflege-Nachtschicht" und "in der Verwaltung" trennen sich dort.
    """
    return frozenset(
        (round(fact.value, 6), fact.unit) for fact in extract_numeric_facts(text)
    )


def canonical_claim_key(
    statement: str, evidence_refs: Sequence[str]
) -> Tuple[Any, ...]:
    """Die harte Vorbedingung: gleiche Zahlen, gleiche Belege.

    Zwei Claims mit verschiedenen Schlüsseln sind nie Dubletten — und der
    Schlüssel ist billig genug, um vor jedem Textvergleich zu stehen.
    """
    return (
        _numeric_signature(statement),
        frozenset(str(ref) for ref in evidence_refs or ()),
    )


def _similarity(left: str, right: str) -> float:
    a, b = _content_tokens(left), _content_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def claims_are_duplicates(left: Any, right: Any) -> bool:
    """Behaupten beide denselben Sachverhalt?"""
    if canonical_claim_key(
        getattr(left, "statement", ""), getattr(left, "evidence_refs", ())
    ) != canonical_claim_key(
        getattr(right, "statement", ""), getattr(right, "evidence_refs", ())
    ):
        return False
    return (
        _similarity(
            getattr(left, "statement", ""), getattr(right, "statement", "")
        )
        >= CLAIM_SIMILARITY_THRESHOLD
    )


def _first_duplicate(claim: Any, kept: Sequence[Any]) -> Any | None:
    for candidate in kept:
        if claims_are_duplicates(candidate, claim):
            return candidate
    return None


def dedup_claims(claims: Sequence[Any]) -> List[Any]:
    """Behält je Sachverhalt den ersten Claim, in Reihenfolge des Auftretens.

    Erwartet Objekte mit ``statement`` und ``evidence_refs``. Der erste
    gewinnt, weil er im früheren Abschnitt steht und der Leser ihn dort im
    Zusammenhang findet.
    """
    kept: List[Any] = []
    for claim in claims:
        if _first_duplicate(claim, kept) is None:
            kept.append(claim)
    return kept


def duplicate_report(claims: Sequence[Any]) -> List[Dict[str, str]]:
    """Welche Claims als Dubletten entfallen — für das Audit-Protokoll.

    Eine stillschweigend entfernte Aussage wäre derselbe Fehler in klein, den
    dieser Slice sonst behebt: Information darf verschwinden, aber nicht ohne
    Spur.
    """
    kept: List[Any] = []
    dropped: List[Dict[str, str]] = []
    for claim in claims:
        original = _first_duplicate(claim, kept)
        if original is None:
            kept.append(claim)
            continue
        dropped.append({
            "claim_id": str(getattr(claim, "id", "")),
            "duplicate_of": str(getattr(original, "id", "")),
        })
    return dropped


__all__ = [
    "CLAIM_SIMILARITY_THRESHOLD",
    "canonical_claim_key",
    "claims_are_duplicates",
    "dedup_claims",
    "duplicate_report",
]
