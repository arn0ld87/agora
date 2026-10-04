"""Ein Claim, der drei Dinge behauptet, braucht Belege für drei Dinge.

Im Referenzlauf ``report_cc2ef45da5e9`` trugen einzelne Claims gleichzeitig
einen Seed-Fakt, eine Stakeholder-Aussage und eine Ableitung. Eine Evidence-ID
kann davon höchstens einen Teil tragen — und trug ihn auch, weshalb der Claim
als belegt durchging.

``coverage_ratio`` fängt den groben Fall schon ab. Was ihm entgeht, ist der
lange Claim mit einem kurzen unbelegten Anhängsel: dessen Wörter gehen in der
Gesamtdeckung unter.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from app.services.claim_atomizer import is_compound, split_compound_claim
from app.services.evidence_entailment import EntailmentVerdict, classify_evidence


def _snippet(text: str) -> Dict[str, Any]:
    return {"snippet": text, "source_kind": "seed_corpus"}


# --- Zerlegung ---------------------------------------------------------------


def test_a_semicolon_separates_two_claims():
    parts = split_compound_claim(
        "Die Schulungsquote liegt bei 31 Prozent; der gestaffelte Rollout "
        "beginnt im kommenden Quartal."
    )

    assert len(parts) == 2


def test_sowie_separates_two_claims():
    parts = split_compound_claim(
        "Die Pflege meldet Zeitdruck sowie die Verwaltung berichtet von "
        "fehlenden Schulungsplätzen."
    )

    assert len(parts) == 2


def test_two_sentences_are_two_claims():
    parts = split_compound_claim(
        "Die Schulungsquote liegt bei 31 Prozent. Der Rollout bleibt riskant."
    )

    assert len(parts) == 2


@pytest.mark.parametrize(
    "statement",
    [
        "Die Verwaltung prüft die Folgen, bevor der Kreistag den Standort zum "
        "30. Juni 2027 aufgibt.",
        "Der Kreistag soll bis zum 11. Juni 2027 entscheiden, ob der Standort "
        "erhalten bleibt.",
        "Die Auswertung erfolgt im 2. Quartal durch die Verwaltung des Landkreises.",
    ],
)
def test_ordinal_date_is_not_a_sentence_boundary(statement):
    """#1766: "zum 30. Juni 2027" ist ein Datum, kein Satzende.

    Der naive Trenner machte daraus "… zum 30." und "Juni 2027 aufgibt." —
    zwei Fragmente, die als Hypothesen und Data Gaps durch den Bericht liefen.
    """
    assert split_compound_claim(statement) == [statement]


def test_a_year_followed_by_a_new_sentence_is_still_a_boundary():
    """Gegenprobe: Punkt nach vierstelliger Jahreszahl bleibt ein Satzende."""
    parts = split_compound_claim(
        "Der Standort schließt im Jahr 2027. Danach übernimmt die Nachbarklinik "
        "die Versorgung."
    )

    assert parts == [
        "Der Standort schließt im Jahr 2027.",
        "Danach übernimmt die Nachbarklinik die Versorgung.",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Die Verwaltung prüft die Folgen, bevor der Kreistag den Standort zum "
            "30. Juni 2027 aufgibt.",
            [
                "Die Verwaltung prüft die Folgen, bevor der Kreistag den Standort "
                "zum 30. Juni 2027 aufgibt."
            ],
        ),
        (
            "Der Kreistag soll bis zum 11. Juni 2027 entscheiden, ob der Standort "
            "erhalten bleibt.",
            [
                "Der Kreistag soll bis zum 11. Juni 2027 entscheiden, ob der "
                "Standort erhalten bleibt."
            ],
        ),
        (
            "Der Standort schließt im Jahr 2027. Danach übernimmt die Nachbarklinik "
            "die Versorgung.",
            [
                "Der Standort schließt im Jahr 2027.",
                "Danach übernimmt die Nachbarklinik die Versorgung.",
            ],
        ),
        ("Ist das belegt? Ja. Es steht im Bericht!", ["Ist das belegt?", "Ja.", "Es steht im Bericht!"]),
    ],
)
def test_shared_splitter_and_entailment_sentences_agree(text, expected):
    """Claim-Atomizer, Entailment und Fließtext-Prüfung teilen eine Satzgrenze."""
    from app.services.evidence_entailment import _sentences
    from app.services.sentence_splitter import split_sentences

    assert split_sentences(text) == expected
    assert _sentences(text) == expected


def test_a_simple_claim_stays_whole():
    statement = "Die Schulungsquote der Pflege liegt bei 31 Prozent."

    assert split_compound_claim(statement) == [statement]
    assert is_compound(statement) is False


def test_oder_does_not_split_a_claim():
    """Eine Alternative ist eine Aussage, keine zwei."""
    statement = "Der Rollout erfolgt gestaffelt oder er verschiebt sich."

    assert len(split_compound_claim(statement)) == 1


def test_a_fragment_is_not_an_atom():
    """"und dann" trägt nichts, was sich belegen ließe."""
    parts = split_compound_claim(
        "Die Schulungsquote liegt bei 31 Prozent; und dann."
    )

    assert len(parts) == 1


def test_an_empty_statement_yields_nothing():
    assert split_compound_claim("") == []


def test_a_colon_introduced_bullet_list_splits_into_one_claim_per_item():
    """#1346: Aufzaehlungsform aus dem Issue-Beispiel.

    ``Rollout nur wenn:`` gefolgt von Bindestrich-Bullets ist ein
    Sammelclaim mit so vielen Teilaussagen wie Bullets. Jeder Teil traegt
    die Einleitung vor dem Doppelpunkt weiter — sonst waere z.B.
    "S-17 behoben" ohne Bezug zu "Rollout" und faellt unter
    ``MIN_ATOM_TOKENS``.
    """
    parts = split_compound_claim(
        "Rollout nur wenn folgende Bedingungen erfuellt sind:\n"
        "- die Datenschutzfolgenabschaetzung abgeschlossen ist\n"
        "- die Betriebsvereinbarung unterschrieben ist\n"
        "- die Schulungsquote erreicht ist"
    )

    assert len(parts) == 3
    assert all(p.startswith("Rollout nur wenn folgende Bedingungen erfuellt sind") for p in parts)
    assert any("Datenschutzfolgenabschaetzung" in p for p in parts)
    assert any("Betriebsvereinbarung" in p for p in parts)
    assert any("Schulungsquote" in p for p in parts)


def test_a_bullet_list_without_colon_intro_is_not_split():
    """Konservative Grenze: nur Doppelpunkt+Liste loest die Zerlegung aus.

    Ohne Doppelpunkt am Zeilenende vor der Aufzaehlung ist nicht sicher,
    dass die folgenden Zeilen eigenstaendige Teilaussagen sind statt z.B.
    einer Fortsetzung eines Fliesstext-Absatzes mit Gedankenstrichen.
    """
    text = (
        "Rollout nur wenn folgende Bedingungen erfuellt sind\n"
        "- die Datenschutzfolgenabschaetzung abgeschlossen ist\n"
        "- die Betriebsvereinbarung unterschrieben ist"
    )

    assert split_compound_claim(text) == [text]


# --- Wirkung auf das Urteil --------------------------------------------------


def test_a_compound_claim_with_one_unbacked_part_is_not_supported():
    """Der Fall aus dem Referenzlauf: langer belegter Teil, kurzes Anhängsel.

    Die Gesamtdeckung liegt über der Schwelle — die Wörter des Anhängsels
    gehen darin unter. Erst die Zerlegung macht sichtbar, dass die Quelle zu
    einer der beiden Behauptungen nichts sagt.
    """
    result = classify_evidence(
        "Die verpflichtende Basisschulung ist im Projektplan verankert und vor "
        "Produktivstart abzuschließen; die Kantinenpreise steigen deutlich.",
        _snippet(
            "Die verpflichtende Basisschulung ist im Projektplan verankert und "
            "vor Produktivstart abzuschließen."
        ),
    )

    assert result.verdict is not EntailmentVerdict.SUPPORTED
    assert "compound_claim_partially_uncovered" in result.checks


def test_a_compound_claim_with_every_part_backed_is_supported():
    result = classify_evidence(
        "Die verpflichtende Basisschulung ist im Projektplan verankert; "
        "der Projektplan nennt den Produktivstart.",
        _snippet(
            "Die verpflichtende Basisschulung ist im Projektplan verankert, und "
            "der Projektplan nennt den Produktivstart."
        ),
    )

    assert result.verdict is EntailmentVerdict.SUPPORTED


def test_a_simple_backed_claim_is_unaffected():
    """Die Verschärfung greift nur bei zusammengesetzten Claims."""
    result = classify_evidence(
        "Die verpflichtende Basisschulung ist im Projektplan verankert.",
        _snippet(
            "Die verpflichtende Basisschulung ist im Projektplan verankert."
        ),
    )

    assert result.verdict is EntailmentVerdict.SUPPORTED
