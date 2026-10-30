"""Extraktion numerischer Fakten aus Fließtext."""

from __future__ import annotations

import re
from typing import List, Tuple

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
    _ARTICLE_DISCONNECTORS,
    _BETWEEN_RE,
    _FROM_TO_RE,
    _NUMBER_VALUE,
    _PERCENT_RE,
    _RANGE_RE,
    _VERB_DISCONNECTORS,
    _is_calendar_year_or_date,
    normalize_unit,
)
from .types import BoundKind, FactModality, NumericFact


def _range_matches(sentence: str) -> List[Tuple[re.Match[str], float, float]]:
    """Findet alle Spannen-Matches mit lower and upper float values."""
    matches: List[Tuple[re.Match[str], float, float]] = []
    for pattern in (_RANGE_RE, _BETWEEN_RE, _FROM_TO_RE):
        for m in pattern.finditer(sentence):
            lo = _parse_number(m.group("lower"))
            hi = _parse_number(m.group("upper"))
            if lo is not None and hi is not None:
                matches.append((m, lo, hi))
    matches.sort(key=lambda x: x[0].start())

    filtered: List[Tuple[re.Match[str], float, float]] = []
    occupied: List[Tuple[int, int]] = []
    for m, lo, hi in matches:
        if any(o_start <= m.start() < o_end or o_start < m.end() <= o_end for o_start, o_end in occupied):
            continue
        occupied.append((m.start(), m.end()))
        filtered.append((m, lo, hi))
    return filtered


def _range_spans(sentence: str) -> List[tuple[int, int]]:
    """Zeichenbereiche, in denen Zahlen zu einer Spanne gehoeren."""
    return [(m.start(), m.end()) for m, _, _ in _range_matches(sentence)]


def _extract_range_facts(sentence: str) -> List[NumericFact]:
    """Extrahiert Spannen als jeweils zwei Fakten (AT_LEAST und AT_MOST)."""
    facts: List[NumericFact] = []
    ranges = _range_matches(sentence)
    for m, lo, hi in ranges:
        prefix = sentence[: m.start()]
        tail_full = sentence[m.end() :]
        is_percent = False
        unit = "count"
        m_pct = re.match(
            r"^\s*(?:%|Prozent|percent)\s*(?:der|des|von\s+den|von|aller|of)?\s*",
            tail_full,
            re.IGNORECASE,
        )
        if m_pct or "%" in m.group() or "prozent" in m.group().lower():
            is_percent = True
            unit = "percent"
            tail_rest = tail_full[m_pct.end() :] if m_pct else tail_full
        else:
            tail_rest = tail_full

        subject, tail = _split_subject_predicate(tail_rest)
        if not subject:
            subject = _subject_from_prefix(prefix)
        if not subject:
            subject = "Zahl"

        if not is_percent:
            first_word = (
                tail_full.strip().split()[0].strip(",.;:()").lower()
                if tail_full.strip()
                else ""
            )
            nu = normalize_unit(first_word)
            if nu != first_word:
                unit = nu
            else:
                nu_subj = normalize_unit(subject.lower())
                if nu_subj != subject.lower():
                    unit = nu_subj
                else:
                    unit = "count"

        predicate = _full_predicate(prefix, tail, head="")
        modality = _modality_of(predicate, sentence)
        scope = _scope_terms(prefix, subject)

        facts.append(
            NumericFact(
                value=lo,
                unit=unit,
                subject=subject,
                predicate=predicate,
                modality=modality,
                raw=sentence.strip(),
                bound=BoundKind.AT_LEAST,
                scope=scope,
            )
        )
        facts.append(
            NumericFact(
                value=hi,
                unit=unit,
                subject=subject,
                predicate=predicate,
                modality=modality,
                raw=sentence.strip(),
                bound=BoundKind.AT_MOST,
                scope=scope,
            )
        )
    return facts


def _numeric_spans(sentence: str) -> List[tuple[str, "re.Match[str]"]]:
    """Alle Zahlenvorkommen eines Satzes (Punktwerte), in Lesereihenfolge."""
    ranges = _range_spans(sentence)

    def _in_range(position: int) -> bool:
        """Liegt diese Zahl innerhalb einer erkannten Spanne?"""
        return any(lo <= position < hi for lo, hi in ranges)

    spans: List[tuple[str, "re.Match[str]"]] = []
    for m in _PERCENT_RE.finditer(sentence):
        if _in_range(m.start()):
            continue
        val = _parse_number(m.group("value"))
        if val is not None and _is_calendar_year_or_date(val, m.start(), m.end(), sentence):
            continue
        spans.append(("percent", m))

    percent_ranges = [(m.start(), m.end()) for _, m in spans]
    for match in _ABSOLUTE_RE.finditer(sentence):
        if _in_range(match.start()):
            continue
        if any(lo <= match.start() < hi for lo, hi in percent_ranges):
            continue
        val = _parse_number(match.group("value"))
        if val is None:
            continue
        if _is_calendar_year_or_date(val, match.start(), match.end(), sentence):
            continue
        val_end = match.start() + len(match.group("value"))
        noun_start = match.start("noun")
        gap_words = sentence[val_end:noun_start].strip().lower().split()
        if any(w in _VERB_DISCONNECTORS for w in gap_words):
            continue
        if any(w in _ARTICLE_DISCONNECTORS for w in gap_words) and "der" not in gap_words and "von" not in gap_words:
            continue
        noun = match.group("noun")
        norm_u = normalize_unit(noun)
        unit = norm_u if norm_u != noun.lower() else "count"
        spans.append((unit, match))

    spans.sort(key=lambda entry: entry[1].start())
    return spans


def _extract_table_numeric_facts(text: str) -> List[NumericFact]:
    """Extrahiert Zahlen strukturiert aus Markdown-Tabellen."""
    lines = text.splitlines()
    table_blocks: List[List[str]] = []
    current_block: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            current_block.append(stripped)
        else:
            if current_block:
                table_blocks.append(current_block)
                current_block = []
    if current_block:
        table_blocks.append(current_block)

    facts: List[NumericFact] = []
    for block in table_blocks:
        if len(block) < 3:
            continue
        delimiter_cells = [c.strip() for c in block[1].split("|")[1:-1]]
        if not all(re.match(r"^:?-+:?$", c) for c in delimiter_cells if c):
            continue
        headers = [c.strip() for c in block[0].split("|")[1:-1]]
        for row_str in block[2:]:
            cells = [c.strip() for c in row_str.split("|")[1:-1]]
            if not cells:
                continue
            row_label = cells[0]
            for col_idx, cell in enumerate(cells):
                if col_idx == 0 and len(cells) > 1 and not cell.replace(".", "").isdigit():
                    continue
                cell_bound = BoundKind.EXACT
                if re.search(r"(?:>=|mindestens|at least)", cell, re.I):
                    cell_bound = BoundKind.AT_LEAST
                elif re.search(r"(?:<=|<|bis zu|höchstens|max)", cell, re.I):
                    cell_bound = BoundKind.AT_MOST

                col_header = headers[col_idx] if col_idx < len(headers) else ""
                unit = "count"
                if "%" in cell or "%" in col_header or "prozent" in col_header.lower():
                    unit = "percent"
                else:
                    m_unit = re.search(r"\(([^)]+)\)", col_header)
                    raw_u = m_unit.group(1) if m_unit else cell
                    unit = normalize_unit(raw_u)
                    if unit == raw_u:
                        for token in col_header.lower().split():
                            nu = normalize_unit(token)
                            if nu != token:
                                unit = nu
                                break
                        else:
                            unit = "count"

                num_matches = list(re.finditer(_NUMBER_VALUE, cell))
                for nm in num_matches:
                    val = _parse_number(nm.group(0))
                    if val is None:
                        continue
                    if 1900 <= val <= 2099 and ("jahr" in col_header.lower() or "stand" in col_header.lower() or "jahr" in cell.lower()):
                        continue
                    if col_idx == 0:
                        subj = row_label if not row_label.isdigit() else col_header
                        pred = col_header
                    else:
                        subj = row_label if row_label else col_header
                        clean_header = re.sub(r"\s*\([^)]+\)", "", col_header).strip()
                        pred = clean_header or col_header

                    facts.append(
                        NumericFact(
                            value=val,
                            unit=unit,
                            subject=subj,
                            predicate=pred,
                            modality=FactModality.FACTUAL,
                            raw=row_str,
                            bound=cell_bound,
                            scope=frozenset(),
                        )
                    )
    return facts


def extract_numeric_facts(text: str) -> List[NumericFact]:
    """Extrahiert Zahlen samt Bezugsgruppe, Aussage und Modalität."""
    facts: List[NumericFact] = []
    # 1. Tabellen-Fakten extrahieren
    facts.extend(_extract_table_numeric_facts(text))

    # 2. Textzeilen ohne Tabellenzeilen für Fließtext
    prose_lines = [
        line for line in text.splitlines()
        if not (line.strip().startswith("|") and line.strip().endswith("|") and line.count("|") >= 2)
    ]
    prose_text = "\n".join(prose_lines)

    for sentence in _sentences(prose_text):
        # Punktwerte extrahieren (Spannen sind über _range_spans ausgeschlossen)
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
