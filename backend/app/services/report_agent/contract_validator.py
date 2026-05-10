"""Output-Contract-Validator fuer den Report-Agent (Sub-Slice P1.1).

Quelle: PLAN.md §2.1 — Pflichtabschnitt-Validator.
"""
from __future__ import annotations


def validate_required_sections(
    outline_titles: list[str],
    required: list[str],
) -> list[str]:
    """Liefert fehlende Section-Titel, case-insensitive und whitespace-tolerant."""
    have = {t.strip().casefold() for t in outline_titles if t and t.strip()}
    return [t for t in required if t.strip().casefold() not in have]


__all__ = ["validate_required_sections"]
