"""M11.8b: Output-Contract-Snapshot-Tests.

Pinnt die DEFAULT_REPORT_SECTIONS aus report_prompts.py gegen einen
maschinenlesbaren Snapshot (output-contract-required-sections.txt).
Drift in der Section-Liste schlägt damit sofort als Test-Fail an,
nicht erst beim externen Bewertungs-Review.

Quelle: docu/2026-05-09-output-vertrag-bewertung-evidence-quality.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.report_agent import MIN_PERSONA_TABLE_ROWS
from app.services.report_prompts import DEFAULT_REPORT_SECTIONS

SNAPSHOT_PATH = (
    Path(__file__).parent / "snapshots" / "output-contract-required-sections.txt"
)


def test_default_report_sections_matches_snapshot():
    """DEFAULT_REPORT_SECTIONS-Titles müssen exakt mit Snapshot übereinstimmen.

    Drift erfordert bewussten Snapshot-Update, nicht stillschweigendes
    Wegrutschen der Pflichtabschnitt-Liste.
    """
    expected = SNAPSHOT_PATH.read_text(encoding="utf-8").strip().splitlines()
    actual = [title for title, _desc in DEFAULT_REPORT_SECTIONS]
    assert actual == expected, (
        "DEFAULT_REPORT_SECTIONS-Titles weichen vom Snapshot ab.\n"
        f"  Snapshot: {expected}\n"
        f"  Actual:   {actual}\n"
        "Wenn das Update beabsichtigt ist, passe "
        f"{SNAPSHOT_PATH} an."
    )


def test_default_report_sections_descriptions_non_empty():
    """Jede Default-Section muss eine non-empty description haben."""
    for title, desc in DEFAULT_REPORT_SECTIONS:
        assert desc and desc.strip(), (
            f"Section '{title}' hat leere description in DEFAULT_REPORT_SECTIONS"
        )


def test_min_persona_table_rows_pinned_to_fifty():
    """MIN_PERSONA_TABLE_ROWS pinnt das Mengengerüst aus der externen Bewertung.

    Quelle: docu/2026-05-09-output-vertrag-bewertung-evidence-quality.md §6.1.
    Eine Änderung verlangt expliziten Sub-Slice + Bewertungs-Begründung.
    """
    assert MIN_PERSONA_TABLE_ROWS == 50


def test_required_sections_count_is_eleven():
    """Pflichtabschnitt-Liste muss genau 11 Einträge haben."""
    assert len(DEFAULT_REPORT_SECTIONS) == 11
