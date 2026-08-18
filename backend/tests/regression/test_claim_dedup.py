"""Derselbe Befund aus mehreren Abschnitten ist ein Befund.

Über die sieben Abschnitte des Referenzlaufs ``report_cc2ef45da5e9``
verteilten sich mehrfach praktisch identische Aussagen. Für den Leser sieht
das aus wie mehrfache Bestätigung; tatsächlich ist es dieselbe Quelle,
mehrfach zitiert.

Die Gegenrichtung wiegt schwerer: ein falsch verschmolzener Claim löscht eine
Aussage, ein doppelt genannter ermüdet nur. Deshalb gelten Zahlen und
Belegmenge als harte Vorbedingung, und die Wortüberlappung darüber hinaus ist
hoch angesetzt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.services.report_agent.claim_dedup import (
    canonical_claim_key,
    claims_are_duplicates,
    dedup_claims,
    duplicate_report,
)


@dataclass
class _Claim:
    id: str
    statement: str
    evidence_refs: List[str] = field(default_factory=list)


# --- Dublettenerkennung -----------------------------------------------------


def test_the_same_statement_reworded_counts_as_a_duplicate():
    assert claims_are_duplicates(
        _Claim("C1", "Die Schulungsquote der Pflege liegt bei 54 Prozent.", ["ev_a"]),
        _Claim("C2", "Bei 54 Prozent liegt die Schulungsquote der Pflege.", ["ev_a"]),
    )


def test_a_filler_word_in_a_long_claim_does_not_break_the_match():
    """Ein zusätzliches, bedeutungsneutrales Wort kippt die Ähnlichkeit nicht."""
    assert claims_are_duplicates(
        _Claim(
            "C1",
            "Die verpflichtende Basisschulung der Pflegekräfte ist im "
            "Projektplan verankert und vor Produktivstart abzuschließen.",
            ["ev_a"],
        ),
        _Claim(
            "C2",
            "Die verpflichtende Basisschulung der Pflegekräfte ist im "
            "Projektplan verankert und zwingend vor Produktivstart "
            "abzuschließen.",
            ["ev_a"],
        ),
    )


def test_a_filler_word_in_a_short_claim_does_break_the_match():
    """Die dokumentierte Kehrseite der hohen Schwelle.

    Bei vier Inhaltswörtern senkt ein fünftes die Überlappung auf 0.80 — unter
    die Schwelle. Die Dublette bleibt dann stehen. Das ist der bewusste
    Tausch: eine hohe Schwelle lässt eher eine Dublette durch, eine niedrige
    verschmilzt eher zwei verschiedene Aussagen und löscht eine davon.
    """
    assert not claims_are_duplicates(
        _Claim("C1", "Die Schulungsquote der Pflege liegt bei 54 Prozent.", ["ev_a"]),
        _Claim(
            "C2",
            "Die Schulungsquote der Pflege liegt aktuell bei 54 Prozent.",
            ["ev_a"],
        ),
    )


def test_a_different_population_is_no_duplicate():
    """31 % in der Nachtschicht und 31 % in der Verwaltung sind zwei Aussagen."""
    assert not claims_are_duplicates(
        _Claim(
            "C1",
            "In der Pflege-Nachtschicht sind 31 Prozent der Beschäftigten geschult.",
            ["ev_a"],
        ),
        _Claim(
            "C2",
            "In der Verwaltung sind 31 Prozent der Beschäftigten geschult.",
            ["ev_a"],
        ),
    )


def test_a_paraphrase_with_a_different_verb_is_not_caught():
    """Die dokumentierte Grenze des Verfahrens.

    "erreichte" und "liegt bei" meinen dasselbe; ein Wortvergleich sieht das
    nicht. Sie zu fangen bräuchte ein semantisches Urteil, dessen Fehler
    unvorhersagbar wären — an dieser Stelle wiegt das schwerer als die
    verbleibende Dublette.
    """
    assert not claims_are_duplicates(
        _Claim("C1", "Die Pflege erreichte 54 Prozent.", ["ev_a"]),
        _Claim("C2", "Bei 54 Prozent liegt die Pflege.", ["ev_a"]),
    )


def test_a_different_value_keeps_its_own_key():
    assert canonical_claim_key("Die Pflege erreichte 54 Prozent.", ["ev_a"]) != (
        canonical_claim_key("Die Pflege erreichte 31 Prozent.", ["ev_a"])
    )


def test_a_different_evidence_set_keeps_its_own_key():
    """Zwei Quellen für dieselbe Aussage sind zweifach belegt, nicht doppelt."""
    assert canonical_claim_key("Die Pflege erreichte 54 Prozent.", ["ev_a"]) != (
        canonical_claim_key("Die Pflege erreichte 54 Prozent.", ["ev_b"])
    )


def test_identical_wording_with_a_different_source_is_no_duplicate():
    assert not claims_are_duplicates(
        _Claim("C1", "Die Pflege erreichte 54 Prozent.", ["ev_a"]),
        _Claim("C2", "Die Pflege erreichte 54 Prozent.", ["ev_b"]),
    )


def test_the_order_of_evidence_refs_does_not_matter():
    assert canonical_claim_key("Die Pflege erreichte 54 Prozent.", ["ev_a", "ev_b"]) == (
        canonical_claim_key("Die Pflege erreichte 54 Prozent.", ["ev_b", "ev_a"])
    )


# --- Deduplizierung ----------------------------------------------------------


def test_the_first_occurrence_survives():
    """Der frühere Abschnitt gewinnt — dort findet der Leser den Zusammenhang."""
    kept = dedup_claims([
        _Claim("C1_01", "Die Schulungsquote der Pflege liegt bei 54 Prozent.", ["ev_a"]),
        _Claim("C4_02", "Bei 54 Prozent liegt die Schulungsquote der Pflege.", ["ev_a"]),
    ])

    assert [claim.id for claim in kept] == ["C1_01"]


def test_two_genuinely_different_claims_both_survive():
    kept = dedup_claims([
        _Claim("C1_01", "Die Pflege erreichte 54 Prozent.", ["ev_a"]),
        _Claim("C2_01", "Die Nachtschicht erreichte 31 Prozent.", ["ev_a"]),
    ])

    assert len(kept) == 2


def test_the_order_of_the_remaining_claims_is_preserved():
    kept = dedup_claims([
        _Claim("C1_01", "Erste Aussage über die Pflege.", ["ev_a"]),
        _Claim("C2_01", "Zweite Aussage über die Verwaltung.", ["ev_b"]),
        _Claim("C3_01", "Über die Pflege die erste Aussage.", ["ev_a"]),
    ])

    assert [claim.id for claim in kept] == ["C1_01", "C2_01"]


def test_an_empty_list_stays_empty():
    assert dedup_claims([]) == []


# --- Protokoll ---------------------------------------------------------------


def test_removed_duplicates_are_reported_with_their_original():
    """Information darf verschwinden — aber nicht ohne Spur."""
    report = duplicate_report([
        _Claim("C1_01", "Die Schulungsquote der Pflege liegt bei 54 Prozent.", ["ev_a"]),
        _Claim("C4_02", "Bei 54 Prozent liegt die Schulungsquote der Pflege.", ["ev_a"]),
    ])

    assert report == [{"claim_id": "C4_02", "duplicate_of": "C1_01"}]


def test_a_clean_list_reports_nothing():
    assert (
        duplicate_report([
            _Claim("C1_01", "Die Pflege erreichte 54 Prozent.", ["ev_a"]),
            _Claim("C2_01", "Die Verwaltung erreichte 91 Prozent.", ["ev_b"]),
        ])
        == []
    )
