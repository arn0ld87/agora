"""Vergleichs-Primitive und Ähnlichkeitsmaße für das Evidence-Entailment."""

from __future__ import annotations

from typing import Optional

from .linguistics import _content_tokens, _stems
from .patterns import _MAJORITY_MARKERS, _MINORITY_MARKERS


def _overlap_ratio(left: str, right: str) -> float:
    """Containment-Overlap: Anteil der kleineren Tokenmenge in der größeren."""
    a, b = _content_tokens(left), _content_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def coverage_ratio(claim_text: str, evidence_text: str) -> float:
    """Anteil der Claim-Aussage, der von der Evidence gedeckt ist."""
    claim_tokens = _content_tokens(claim_text)
    evidence_tokens = _content_tokens(evidence_text)
    if not claim_tokens:
        return 0.0
    if not evidence_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def subjects_match(left: str, right: str) -> bool:
    """Bezugsgruppen-Vergleich mit leichter Stamm-Normalisierung."""
    a, b = _stems(left), _stems(right)
    if not a or not b:
        return False
    return bool(a & b)


def _quantifier_direction(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if any(marker in lowered for marker in _MAJORITY_MARKERS):
        return "majority"
    if any(marker in lowered for marker in _MINORITY_MARKERS):
        return "minority"
    return None


__all__ = [
    "_overlap_ratio",
    "_quantifier_direction",
    "coverage_ratio",
    "subjects_match",
]
