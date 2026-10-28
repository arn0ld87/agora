"""Extraktion numerischer Fakten aus Fließtext."""

from __future__ import annotations

import re
from typing import List

from .linguistics import (
    _bound_of,
    _full_predicate,
    _modality_of,
    _parse_number,
    _scope_terms,
    _sentences,
    _split_subject_predicate,
    _subject_from_prefix,
)
from .patterns import (
    _ABSOLUTE_RE,
    _BETWEEN_RE,
    _FROM_TO_RE,
    _PERCENT_RE,
    _RANGE_RE,
)
from .types import NumericFact


def _range_spans(sentence: str) -> List[tuple[int, int]]:
    """Zeichenbereiche, in denen Zahlen zu einer Spanne gehoeren."""
    spans = [(m.start(), m.end()) for m in _RANGE_RE.finditer(sentence)]
    spans.extend((m.start(), m.end()) for m in _BETWEEN_RE.finditer(sentence))
    spans.extend((m.start(), m.end()) for m in _FROM_TO_RE.finditer(sentence))
    return spans


def _numeric_spans(sentence: str) -> List[tuple[str, "re.Match[str]"]]:
    """Alle Zahlenvorkommen eines Satzes, in Lesereihenfolge."""
    ranges = _range_spans(sentence)

    def _in_range(position: int) -> bool:
        """Liegt diese Zahl innerhalb einer erkannten Spanne?"""
        return any(lo <= position < hi for lo, hi in ranges)

    spans: List[tuple[str, "re.Match[str]"]] = [
        match_pair
        for match_pair in (("percent", m) for m in _PERCENT_RE.finditer(sentence))
        if not _in_range(match_pair[1].start())
    ]
    percent_ranges = [(m.start(), m.end()) for _, m in spans]
    for match in _ABSOLUTE_RE.finditer(sentence):
        if _in_range(match.start()):
            continue
        if any(lo <= match.start() < hi for lo, hi in percent_ranges):
            continue
        spans.append(("absolute", match))
    spans.sort(key=lambda entry: entry[1].start())
    return spans


def extract_numeric_facts(text: str) -> List[NumericFact]:
    """Extrahiert Zahlen samt Bezugsgruppe, Aussage und Modalität."""
    facts: List[NumericFact] = []
    for sentence in _sentences(text):
        spans = _numeric_spans(sentence)
        head = sentence[: spans[0][1].start()] if spans else ""
        for index, (unit, match) in enumerate(spans):
            value = _parse_number(match.group("value"))
            if value is None:
                continue
            prefix_start = spans[index - 1][1].end() if index else 0
            tail_end = (
                spans[index + 1][1].start()
                if index + 1 < len(spans)
                else len(sentence)
            )
            prefix = sentence[prefix_start : match.start()]
            starts_new_clause = False
            for separator in (";", ":", "—", " – "):
                if separator in prefix:
                    starts_new_clause = index > 0
                    prefix = prefix.rsplit(separator, 1)[1]
            tail_start = (
                match.end() if unit == "percent" else match.start("noun")
            )
            subject, tail = _split_subject_predicate(sentence[tail_start:tail_end])
            if not subject:
                subject = _subject_from_prefix(prefix)
            if not subject:
                continue
            predicate = _full_predicate(
                prefix, tail, head="" if starts_new_clause else head
            )
            facts.append(
                NumericFact(
                    value=value,
                    unit=unit,
                    subject=subject,
                    predicate=predicate,
                    modality=_modality_of(predicate, sentence),
                    raw=sentence.strip(),
                    bound=_bound_of(prefix),
                    scope=_scope_terms(prefix, subject),
                )
            )
    return facts


__all__ = [
    "_numeric_spans",
    "_range_spans",
    "extract_numeric_facts",
]
