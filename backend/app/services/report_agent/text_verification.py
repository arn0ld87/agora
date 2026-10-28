"""Faktenprüfung des sichtbaren Fließtexts.

Fassade für die Fließtext-Verifikation, aufgeteilt in kohäsive Submodule:
- `text_verification_types`: Datenstrukturen (Statements, Urteile, Marker)
- `text_verification_renumbering`: Erkennung von Listen-/Aufzählungsstrukturen & Renummerierung
- `text_verification_engine`: Faktenprüfung, Entscheidungsfindung, `verify_prose`

Alle öffentlichen und privaten Symbole werden hier für Abwärtskompatibilität re-exportiert.
"""

from __future__ import annotations

from ..sentence_splitter import split_sentences
from .text_verification_engine import (
    _DECISIVENESS,
    _SEVERITY,
    _best_verdict,
    _fact_probe,
    _reject_sentence,
    _worst_fact_verdict,
    prose_gate_decisions,
    verify_prose,
)
from .text_verification_renumbering import (
    _ENUMERATION_AT_SENTENCE_START,
    _ENUMERATION_ORDINALS,
    _ENUMERATION_SEQUENCE,
    _FENCE,
    _LIST_PREFIX,
    _MARKER_RE,
    _ORDERED_ITEM,
    _QUOTE_PREFIXES,
    _is_structural,
    _leading_ordinal,
    _mark_unverified,
    _paragraph_bounds,
    _renumber_block,
    _renumber_enumeration,
    _strip_marker,
    is_markup_or_quote_line,
)
from .text_verification_types import (
    UNVERIFIED_MARKER,
    FactOutcome,
    FlaggedStatement,
    RejectedStatement,
    UnverifiedStatement,
    VerifiedProse,
    _fact_label,
)

__all__ = [
    "UNVERIFIED_MARKER",
    "FlaggedStatement",
    "RejectedStatement",
    "UnverifiedStatement",
    "VerifiedProse",
    "is_markup_or_quote_line",
    "prose_gate_decisions",
    "split_sentences",
    "verify_prose",
    "FactOutcome",
    "_fact_label",
    "_QUOTE_PREFIXES",
    "_LIST_PREFIX",
    "_ORDERED_ITEM",
    "_ENUMERATION_SEQUENCE",
    "_ENUMERATION_ORDINALS",
    "_ENUMERATION_AT_SENTENCE_START",
    "_FENCE",
    "_is_structural",
    "_MARKER_RE",
    "_strip_marker",
    "_mark_unverified",
    "_renumber_block",
    "_leading_ordinal",
    "_paragraph_bounds",
    "_renumber_enumeration",
    "_fact_probe",
    "_DECISIVENESS",
    "_SEVERITY",
    "_best_verdict",
    "_worst_fact_verdict",
    "_reject_sentence",
]
