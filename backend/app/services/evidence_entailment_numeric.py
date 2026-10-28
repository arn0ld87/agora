"""Numeric fact extraction, modality/bound parsing, and numeric claim comparison for evidence entailment."""

from __future__ import annotations

from .entailment.classifier import (
    _bound_is_violated,
    _classify_matching_number,
    _classify_numeric_claim,
    facts_are_comparable,
)
from .entailment.linguistics import (
    _bound_of,
    _modality_of,
    _parse_number,
)
from .entailment.numeric_facts import (
    _numeric_spans,
    _range_spans,
    extract_numeric_facts,
)
from .entailment.patterns import (
    PREDICATE_COVERAGE_THRESHOLD,
    PREDICATE_MATCH_THRESHOLD,
    _ABSOLUTE_RE,
    _AT_LEAST_MARKERS,
    _AT_MOST_MARKERS,
    _BETWEEN_RE,
    _BOUND_WINDOW,
    _DIVERGENCE_REASONS,
    _FROM_TO_RE,
    _NORMATIVE_MARKERS,
    _NORMATIVE_NOUN_MARKERS,
    _NUMBER_VALUE,
    _PERCENT_RE,
    _RANGE_RE,
    _WORD_NUMBER_ALTERNATION,
    _WORD_NUMBERS,
)
from .entailment.types import (
    BoundKind,
    EntailmentResult,
    EntailmentVerdict,
    FactModality,
    NumericFact,
)

__all__ = [
    "EntailmentVerdict",
    "FactModality",
    "BoundKind",
    "NumericFact",
    "EntailmentResult",
    "_WORD_NUMBERS",
    "_WORD_NUMBER_ALTERNATION",
    "_NUMBER_VALUE",
    "_PERCENT_RE",
    "_ABSOLUTE_RE",
    "_NORMATIVE_MARKERS",
    "_NORMATIVE_NOUN_MARKERS",
    "_AT_LEAST_MARKERS",
    "_AT_MOST_MARKERS",
    "_BOUND_WINDOW",
    "_parse_number",
    "_modality_of",
    "_bound_of",
    "_FROM_TO_RE",
    "_RANGE_RE",
    "_BETWEEN_RE",
    "_range_spans",
    "_numeric_spans",
    "extract_numeric_facts",
    "PREDICATE_MATCH_THRESHOLD",
    "PREDICATE_COVERAGE_THRESHOLD",
    "_DIVERGENCE_REASONS",
    "facts_are_comparable",
    "_bound_is_violated",
    "_classify_matching_number",
    "_classify_numeric_claim",
]
