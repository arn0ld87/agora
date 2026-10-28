"""Lexical, tokenization, stemming, scope, and subject-matching helpers for evidence entailment."""

from __future__ import annotations

from .entailment.linguistics import (
    _content_tokens,
    _full_predicate,
    _is_negated,
    _noun_phrases,
    _preceded_by_scope_preposition,
    _scope_stems,
    _scope_terms,
    _scopes_diverge,
    _sentences,
    _split_subject_predicate,
    _stems,
    _subject_from_prefix,
    _tokens,
)
from .entailment.patterns import (
    ENUMERATION_WORDS,
    _EN_SUBJECT_VERBS,
    _MAJORITY_MARKERS,
    _MINORITY_MARKERS,
    _NEGATION_MARKERS,
    _SCOPE_PREPOSITION_WINDOW,
    _SCOPE_PREPOSITIONS,
    _STOPWORDS,
    _SUBJECT_CONNECTORS,
    _TAIL_PREDICATE_MIN_TOKENS,
)
from .entailment.scoring import (
    _overlap_ratio,
    _quantifier_direction,
    coverage_ratio,
    subjects_match,
)

__all__ = [
    "ENUMERATION_WORDS",
    "_MAJORITY_MARKERS",
    "_MINORITY_MARKERS",
    "_STOPWORDS",
    "_tokens",
    "_content_tokens",
    "_NEGATION_MARKERS",
    "_is_negated",
    "_SUBJECT_CONNECTORS",
    "_EN_SUBJECT_VERBS",
    "_split_subject_predicate",
    "_noun_phrases",
    "_subject_from_prefix",
    "_stems",
    "_SCOPE_PREPOSITIONS",
    "_SCOPE_PREPOSITION_WINDOW",
    "_preceded_by_scope_preposition",
    "_scope_terms",
    "_scope_stems",
    "_scopes_diverge",
    "_sentences",
    "_TAIL_PREDICATE_MIN_TOKENS",
    "_full_predicate",
    "_overlap_ratio",
    "coverage_ratio",
    "subjects_match",
    "_quantifier_direction",
]
