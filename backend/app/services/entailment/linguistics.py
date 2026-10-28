"""Linguistische Parsing-Funktionen für das Evidence-Entailment."""

from __future__ import annotations

import re
from typing import List, Optional

from ..sentence_splitter import split_sentences
from .patterns import (
    _AT_LEAST_MARKERS,
    _AT_MOST_MARKERS,
    _BOUND_WINDOW,
    _EN_SUBJECT_VERBS,
    _NEGATION_MARKERS,
    _NORMATIVE_MARKERS,
    _NORMATIVE_NOUN_MARKERS,
    _SCOPE_PREPOSITIONS,
    _SCOPE_PREPOSITION_WINDOW,
    _STOPWORDS,
    _SUBJECT_CONNECTORS,
    _TAIL_PREDICATE_MIN_TOKENS,
    _WORD_NUMBERS,
    ENUMERATION_WORDS,
)
from .types import BoundKind, FactModality


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"\W+", (text or "").lower()) if t and t not in _STOPWORDS]


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if len(t) > 3}


def _is_negated(text: str) -> bool:
    """Traegt der Text einen Verneinungsmarker?

    Bewusst grob: es geht nur darum, zwei sonst nicht messbare Praedikate
    auseinanderzuhalten, nicht um eine Skopusanalyse der Negation.
    """
    return any(
        token in _NEGATION_MARKERS
        for token in re.split(r"\W+", (text or "").lower())
        if token
    )


def _parse_number(raw: str) -> Optional[float]:
    cleaned = raw.strip()
    word_value = _WORD_NUMBERS.get(cleaned.lower())
    if word_value is not None:
        return word_value
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):  # 1.234.567
        cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _split_subject_predicate(tail: str) -> tuple[str, str]:
    """Trennt die Bezugsgruppe vom Prädikat.

    Deutsche Nomen sind großgeschrieben: die Nominalphrase läuft bis zum
    ersten kleingeschriebenen Wort, das kein Bindewort ist. Für englische
    Seeds (keine Großschreibung-Pflicht) fällt diese Heuristik leer aus —
    dann übernimmt ein Fallback, der die Bezugsgruppe bis zum ersten
    bekannten Report-Verb nimmt. Without that, ``extract_numeric_facts``
    liefert für englische Sätze keine Fakten und die Fließtext-Prüfung
    überspringt sie still (Handover P2.7).
    """
    words = tail.split()
    subject_parts: List[str] = []
    idx = 0
    for idx, word in enumerate(words):
        bare = word.strip(",.;:()").lower()
        # Issue #1356: Eine Bezugsgruppe enthält keine zweite Zahlenangabe.
        # In "83 Prozent, in der Verwaltung 91 Prozent und in der Pflege 54
        # Prozent" lief das Subjekt des ersten Fakts über die beiden anderen
        # Zahlen hinweg — jeder Fakt bekam dieselbe unbrauchbare Bezugsgruppe
        # und kollidierte anschließend mit fremden Quellen.
        if any(char.isdigit() for char in word):
            break
        if word[:1].isupper() or bare in _SUBJECT_CONNECTORS:
            # Ein Bindewort zählt nur mit, wenn danach wieder ein Nomen folgt.
            if bare in _SUBJECT_CONNECTORS and not subject_parts:
                continue
            subject_parts.append(word)
            continue
        break
    else:
        idx = len(words)

    # Trailing-Bindewörter gehören nicht zum Subjekt ("Eltern und" → "Eltern").
    while subject_parts and subject_parts[-1].strip(",.;:()").lower() in _SUBJECT_CONNECTORS:
        subject_parts.pop()
        idx -= 1

    subject = " ".join(subject_parts).strip(",.;:() ")
    predicate = " ".join(words[idx:]).strip(",.;:() ")

    # Englischer Fallback: keine Großschreibung → deutscher Pfad leer.
    if not subject and words:
        subject_parts = []
        end_idx = len(words)
        for en_idx, word in enumerate(words):
            bare = word.strip(",.;:()").lower()
            # Issue #1356: dieselbe Grenze wie im deutschen Pfad. Ohne sie
            # verschluckt der Fallback in einer Aufzählung ("83 Prozent, in
            # der Verwaltung 91 Prozent …") den gesamten Rest des Satzes als
            # Bezugsgruppe, sobald rechts der Zahl kein Nomen steht.
            if any(char.isdigit() for char in word):
                end_idx = en_idx
                break
            if bare in _EN_SUBJECT_VERBS:
                end_idx = en_idx
                break
            subject_parts.append(word)
        if subject_parts:
            subject = " ".join(subject_parts).strip(",.;:() ")
            predicate = " ".join(words[end_idx:]).strip(",.;:() ")

    return subject, predicate


def _modality_of(predicate: str, context: str = "") -> FactModality:
    """Ist-Wert oder Zielvorgabe?

    ``context`` ist der ganze Satz. Modalität ist eine Satzeigenschaft, keine
    Prädikatseigenschaft: in "Das Schulungsziel von 80 Prozent wurde in allen
    Schichten verfehlt" steht der Marker im Vorfeld, während ``_full_predicate``
    nur "in allen Schichten verfehlt" liefert. Wer bloß das Prädikat liest,
    hält die Vorgabe für einen gemessenen Wert (Issue #1356).
    """
    lowered = f" {predicate.lower()} {context.lower()} "
    if any(f" {marker} " in lowered for marker in _NORMATIVE_MARKERS):
        return FactModality.NORMATIVE
    if any(marker in lowered for marker in _NORMATIVE_NOUN_MARKERS):
        return FactModality.NORMATIVE
    return FactModality.FACTUAL


def _bound_of(prefix: str) -> BoundKind:
    """Punktwert oder Schranke? Entschieden wird am Fenster links der Zahl."""
    window = (prefix or "")[-_BOUND_WINDOW:].lower()
    at_least = max(
        (window.rfind(marker) for marker in _AT_LEAST_MARKERS), default=-1
    )
    at_most = max((window.rfind(marker) for marker in _AT_MOST_MARKERS), default=-1)
    if at_least < 0 and at_most < 0:
        return BoundKind.EXACT
    return BoundKind.AT_LEAST if at_least > at_most else BoundKind.AT_MOST


def _noun_phrases(text: str) -> List[List[str]]:
    """Zusammenhängende großgeschriebene Nominalphrasen eines Textstücks."""
    groups: List[List[str]] = []
    current: List[str] = []
    for word in (text or "").split():
        bare = word.strip(",.;:()\"'").lower()
        if any(char.isdigit() for char in word):
            if current:
                groups.append(current)
                current = []
            continue
        if (
            word[:1].isupper()
            and bare not in _STOPWORDS
            and bare not in ENUMERATION_WORDS
            and len(bare) > 3
        ):
            current.append(word.strip(",.;:()\"'"))
            continue
        if current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _subject_from_prefix(prefix: str) -> str:
    """Bezugsgruppe aus dem Vorfeld, wenn rechts der Zahl keine steht."""
    groups = _noun_phrases(prefix)
    if not groups:
        return ""
    return " ".join(groups[-1])


def _stems(value: str) -> set[str]:
    return {t[:6] for t in _tokens(value) if len(t) > 3}


def _preceded_by_scope_preposition(prefix: str, phrase: List[str]) -> bool:
    """Führt eine eingrenzende Präposition diese Nominalphrase ein?"""
    if not phrase:
        return False
    words = prefix.split()
    head = phrase[0].strip(",.;:()\"'")
    for index in range(len(words) - 1, -1, -1):
        if words[index].strip(",.;:()\"'") != head:
            continue
        window = words[max(0, index - _SCOPE_PREPOSITION_WINDOW) : index]
        return any(
            word.strip(",.;:()\"'").lower() in _SCOPE_PREPOSITIONS for word in window
        )
    return False


def _scope_terms(prefix: str, subject: str) -> frozenset[str]:
    """Einschränkende Zusätze links der Zahl, ohne die Bezugsgruppe selbst."""
    subject_stems = _stems(subject)
    groups = _noun_phrases(prefix)
    if not groups:
        return frozenset()
    if not _preceded_by_scope_preposition(prefix, groups[-1]):
        return frozenset()
    return frozenset(
        word for word in groups[-1] if not (_stems(word) & subject_stems)
    )


def _scope_stems(scope: frozenset[str]) -> set[str]:
    """Normalisiert Scope-Wörter für den Vergleich; Komposita zählen einzeln."""
    out: set[str] = set()
    for word in scope:
        for token in re.split(r"[-/]", word.lower()):
            if len(token) > 3 and token not in _STOPWORDS:
                out.add(token[:6])
    return out


def _scopes_diverge(left: frozenset[str], right: frozenset[str]) -> bool:
    """Widersprechen sich die Teilpopulationen — oder schweigt eine Seite?"""
    a, b = _scope_stems(left), _scope_stems(right)
    if not a or not b:
        return False
    return a != b


def _sentences(text: str) -> List[str]:
    return split_sentences(text or "")


def _full_predicate(prefix: str, tail_predicate: str, head: str = "") -> str:
    """Wählt die Satzhälfte, die die Aussage trägt."""
    if len(_content_tokens(tail_predicate)) >= _TAIL_PREDICATE_MIN_TOKENS:
        return tail_predicate
    combined = " ".join(
        part for part in (prefix.strip(",.;:() "), tail_predicate) if part
    ).strip()
    if len(_content_tokens(combined)) >= _TAIL_PREDICATE_MIN_TOKENS or not head:
        return combined
    return head.strip(",.;:() ")


__all__ = [
    "_bound_of",
    "_content_tokens",
    "_full_predicate",
    "_is_negated",
    "_modality_of",
    "_noun_phrases",
    "_parse_number",
    "_preceded_by_scope_preposition",
    "_scope_stems",
    "_scope_terms",
    "_scopes_diverge",
    "_sentences",
    "_split_subject_predicate",
    "_stems",
    "_subject_from_prefix",
    "_tokens",
]
