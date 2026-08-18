"""Golden Cases aus dem Referenzlauf zu Issue #1356.

Alle Fälle stammen aus einem vollständigen 7-Sektionen-Lauf, in dem der
Fließtext-Faktencheck 28 Aussagen entfernte und dabei Markdown-Struktur wie
Satzsyntax beschädigte. Jeder Test hält genau einen dieser Schäden fest.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services.evidence_entailment import extract_numeric_facts
from app.services.report_agent.text_verification import (
    UNVERIFIED_MARKER,
    split_sentences,
    verify_prose,
)


def _seed_item(text: str, evidence_id: str = "ev_test") -> Dict[str, Any]:
    return {"evidence_id": evidence_id, "type": "seed_document", "snippet": text}


#: Ein Pool, der nichts von dem belegt, was die Tests hineingeben. Er ist
#: nicht leer, weil ``verify_prose`` ohne Evidence bewusst gar nicht prüft.
UNRELATED_POOL: List[Dict[str, Any]] = [
    _seed_item("Die Kantine bleibt an Feiertagen geschlossen.", "ev_unrelated")
]


# ---------------------------------------------------------------------------
# Satzsegmentierung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line, expected",
    [
        # Der Fall aus section_06.md: die Ordinalzahlen im Datumsbereich
        # galten als Satzende, das Fragment mit den Zahlen fiel weg und der
        # gelesene Satz brach mitten in der Klammer ab.
        (
            "Bei den Tests (3. bis 14. Juni mit 14 Ärzten) wichen 38 Empfehlungen ab. "
            "Die Validität wurde nicht geprüft.",
            [
                "Bei den Tests (3. bis 14. Juni mit 14 Ärzten) wichen 38 Empfehlungen ab.",
                "Die Validität wurde nicht geprüft.",
            ],
        ),
        # Der Fall aus section_01.md: die Listennummer wurde ein eigener Satz
        # und überlebte ihren eigenen Inhalt.
        (
            "1. Erfolgreicher Wiederholungstest in unter 15 Minuten",
            ["1. Erfolgreicher Wiederholungstest in unter 15 Minuten"],
        ),
        # Abkürzungen aus einem Buchstaben und aus der Liste.
        (
            "Das gilt z. B. für Nr. 3 und den 15. Mai. Danach folgt der Rest.",
            ["Das gilt z. B. für Nr. 3 und den 15. Mai.", "Danach folgt der Rest."],
        ),
        # Gewöhnliche Zweibuchstabenwörter dürfen kein Satzende verhindern.
        ("Das lehnten sie ab. Der Rest folgte.", ["Das lehnten sie ab.", "Der Rest folgte."]),
        # Codex-Review PR #1360: eine Kardinalzahl am Satzende ist keine
        # Ordinalzahl. Verschmölzen beide Sätze zu einer Prüfeinheit, risse ein
        # widerlegter Fakt im zweiten den ersten mit heraus.
        (
            "Die Stichprobe umfasste 14. Danach waren 61 Prozent betroffen.",
            ["Die Stichprobe umfasste 14.", "Danach waren 61 Prozent betroffen."],
        ),
        # Dieselbe Zahl vor einem Monatsnamen bleibt eine Ordinalzahl.
        (
            "Der Test lief bis zum 14. Juni und blieb ohne Befund.",
            ["Der Test lief bis zum 14. Juni und blieb ohne Befund."],
        ),
    ],
)
def test_sentence_split_keeps_ordinals_and_abbreviations_together(line, expected):
    assert split_sentences(line) == expected


# ---------------------------------------------------------------------------
# Struktur bleibt heil
# ---------------------------------------------------------------------------

def test_list_marker_never_survives_its_own_content():
    """section_01.md zeigte '1.' und '2.' als leere Zeilen.

    Die beiden Punkte trugen Zahlen, ihre Inhalte fielen der Prüfung zum
    Opfer, die Marker blieben stehen. Kein Ausgang der Prüfung darf einen
    nackten Aufzählungsmarker hinterlassen.
    """
    prose = (
        "Vor einem Rollout sind folgende Bedingungen zu erfüllen:\n"
        "\n"
        "1. Wiederherstellung in unter 15 Minuten\n"
        "2. Schulungsziel von 80 Prozent in allen Schichten\n"
        "3. Abschluss einer Betriebsvereinbarung\n"
    )
    result = verify_prose(prose, UNRELATED_POOL)

    for line in result.content.splitlines():
        assert line.strip() not in {"1.", "2.", "3."}, (
            f"Nackter Listenmarker im Ergebnis:\n{result.content}"
        )


def test_date_range_survives_an_unverifiable_sentence():
    """Der zerstörte Satz aus section_06.md."""
    prose = (
        "Bei den Tests am Standort Falkenbrück-Mitte (3. bis 14. Juni mit 14 Ärzten "
        "und 9 Pflegekräften) wichen 38 Systemempfehlungen ab. "
        "Die klinische Validität wurde nicht geprüft."
    )
    result = verify_prose(prose, UNRELATED_POOL)

    assert "(3. bis 14. Juni" in result.content
    assert "Die klinische Validität wurde nicht geprüft." in result.content
    assert not result.rejected


def test_numbering_is_repaired_when_a_line_is_removed():
    """Entfällt ein Listenpunkt, zählt die Liste lückenlos weiter."""
    contradicting_pool = [
        _seed_item("Der Krankenstand lag bei 12 Prozent der Belegschaft.", "ev_c")
    ]
    prose = (
        "1. Der Krankenstand lag bei 40 Prozent der Belegschaft.\n"
        "2. Abschluss einer Betriebsvereinbarung\n"
        "3. Behebung kritischer Sicherheitsbefunde\n"
    )
    result = verify_prose(prose, contradicting_pool)

    if result.rejected:
        numbers = [
            line.split(".", 1)[0].strip()
            for line in result.content.splitlines()
            if line.strip() and line.strip()[0].isdigit()
        ]
        assert numbers == [str(i) for i in range(1, len(numbers) + 1)], (
            f"Lücke in der Nummerierung:\n{result.content}"
        )


def test_fenced_code_is_never_touched():
    prose = (
        "Vorbemerkung.\n"
        "```\n"
        "1. 83 Prozent der Ärzteschaft\n"
        "2. 54 Prozent der Pflege\n"
        "```\n"
        "Nachbemerkung.\n"
    )
    result = verify_prose(prose, UNRELATED_POOL)
    assert "1. 83 Prozent der Ärzteschaft" in result.content
    assert "2. 54 Prozent der Pflege" in result.content


# ---------------------------------------------------------------------------
# Nur ein Widerspruch entfernt
# ---------------------------------------------------------------------------

def test_unsupported_statement_stays_and_is_marked():
    """"Nicht belegbar" heißt nicht "falsch" — der Satz bleibt lesbar."""
    prose = "Zudem stehen 61 Prozent der Beschäftigten der Einführung kritisch gegenüber."
    result = verify_prose(prose, UNRELATED_POOL)

    assert "61 Prozent" in result.content
    assert UNVERIFIED_MARKER in result.content
    assert result.unverified
    assert not result.rejected


def test_contradicted_statement_is_removed():
    """Widerspricht eine Quelle aktiv, verschwindet die Aussage."""
    pool = [
        _seed_item(
            "40 Prozent der Beschäftigten stehen der Einführung kritisch gegenüber.",
            "ev_conflict",
        )
    ]
    prose = "Zudem stehen 61 Prozent der Beschäftigten der Einführung kritisch gegenüber."
    result = verify_prose(prose, pool)

    assert result.rejected
    assert "61 Prozent" not in result.content


def test_a_single_colliding_item_does_not_sink_the_whole_sentence():
    """Der 83/91-Prozent-Satz aus section_01.md.

    Ein Pool-Item schreibt einen dieser Werte einer fremden Bezugsgruppe zu
    und liefert deshalb ``CONTRADICTED``. Früher entschied dieses eine Item
    über den ganzen Satz, weil ``CONTRADICTED`` gegenüber ``INSUFFICIENT``
    bevorzugt wurde. Jetzt zählt pro Fakt das günstigste Urteil des gesamten
    Pools — ein zufälliger Zahlentreffer kippt keinen Satz mehr, dessen
    übrige Aussagen tragfähig sind.
    """
    pool = [
        _seed_item("83 Prozent der Auszubildenden nahmen teil.", "ev_other_group"),
        _seed_item("Die Schulungsquote lag bei 91 Prozent der Verwaltung.", "ev_admin"),
    ]
    prose = (
        "Die Schulungsquote lag bei 83 Prozent der Ärzteschaft "
        "und 91 Prozent der Verwaltung."
    )
    result = verify_prose(prose, pool)

    assert not result.rejected, (
        "Ein einzelnes kollidierendes Evidence-Item hat den ganzen Satz entfernt"
    )
    assert "83 Prozent" in result.content


def test_a_value_the_claim_itself_names_is_not_a_contradiction():
    """Der 83/91-Satz aus section_01.md in seiner echten Wortstellung.

    Steht die Bezugsgruppe vor der Zahl, läuft das Subjekt der ersten Zahl
    bis zur zweiten Gruppe durch (#1357) — die Regel verglich dann 83 mit den
    belegten 91 Prozent derselben Verwaltung und las einen Widerspruch, wo
    die Quelle den Satz stützt. Ein Claim, der den belegten Wert selbst
    nennt, widerspricht nicht; er ordnet nur unscharf zu.
    """
    pool = [
        _seed_item(
            "Die verpflichtende Basisschulung wurde zu 91 Prozent von der "
            "Verwaltung abgeschlossen.",
            "ev_admin",
        ),
    ]
    prose = (
        "Während die Basisschulung im Ärztlichen Dienst zu 83 Prozent und in der "
        "Verwaltung zu 91 Prozent abgeschlossen wurde, liegt die Quote im "
        "Pflegebereich bei lediglich 54 Prozent."
    )
    result = verify_prose(prose, pool)

    assert not result.rejected
    assert "83 Prozent" in result.content


def test_a_genuinely_different_value_still_removes_the_sentence():
    """Die Gegenprobe: nennt der Claim den belegten Wert nirgends, bleibt es
    ein Widerspruch und der Satz verschwindet (Codex-Review PR #1360, P1)."""
    pool = [
        _seed_item(
            "Die verpflichtende Basisschulung wurde zu 91 Prozent von der "
            "Verwaltung abgeschlossen.",
            "ev_admin",
        ),
    ]
    prose = "Die Basisschulung wurde zu 42 Prozent von der Verwaltung abgeschlossen."
    result = verify_prose(prose, pool)

    assert result.rejected
    assert "42 Prozent" not in result.content


# ---------------------------------------------------------------------------
# Textuelle Aufzählungen
# ---------------------------------------------------------------------------


ENUMERATION_POOL: List[Dict[str, Any]] = [
    _seed_item("Die Verwaltung erreichte 91 Prozent.", "ev_admin_share"),
]

#: Der Absatz aus dem Referenzlauf: vier durchgezählte Punkte, von denen der
#: dritte eine widerlegte Zahl trägt.
ENUMERATION_PROSE = (
    "Erstens bleibt die Personaldecke der Nachtschicht dünn. "
    "Zweitens fehlt eine dokumentierte Rückfallebene. "
    "Drittens erreichte die Verwaltung 42 Prozent. "
    "Viertens fehlt ein belastbarer Zeitplan."
)


def test_textual_enumeration_remains_consistent_after_sanitizing():
    """Der sichtbare Schaden aus ``report_cc2ef45da5e9``.

    Der Trust-Layer entfernte den dritten Punkt und hinterließ "Erstens …
    Zweitens … Viertens". Der Leser sieht dort einen Fehler im Bericht, nicht
    eine vorsichtige Prüfung — und kann nicht wissen, dass etwas fehlt.
    Nummerierte Listen sind seit #1356 geschützt; ausgeschriebene Aufzählungen
    waren es nie.
    """
    result = verify_prose(ENUMERATION_PROSE, ENUMERATION_POOL)

    assert result.rejected, "Der widerlegte dritte Punkt muss entfernt werden"
    assert "42 Prozent" not in result.content
    assert "Viertens" not in result.content
    assert "Erstens" in result.content
    assert "Zweitens" in result.content
    assert "Drittens" in result.content


def test_an_intact_enumeration_is_left_alone():
    """Ohne Entfernung wird nicht umgezählt.

    Ein Absatz, der bewusst mit "Zweitens" einsetzt, weil der erste Punkt im
    vorigen Absatz steht, darf nicht stillschweigend zu "Erstens" werden.
    """
    prose = "Zweitens fehlt eine Rückfallebene. Drittens fehlt ein Zeitplan."
    result = verify_prose(prose, ENUMERATION_POOL)

    assert result.content == prose


def test_an_unverified_enumeration_item_keeps_its_position():
    """Nur Entferntes verschiebt die Zählung — Markiertes bleibt stehen."""
    prose = (
        "Erstens bleibt die Lage angespannt. "
        "Zweitens erreichte die Notaufnahme 37 Prozent. "
        "Drittens fehlt ein Zeitplan."
    )
    result = verify_prose(prose, ENUMERATION_POOL)

    assert not result.rejected
    assert "Zweitens" in result.content
    assert "Drittens" in result.content


def test_enumerations_are_renumbered_per_paragraph():
    """Zwei Absätze sind zwei Aufzählungen; die zweite bleibt unberührt."""
    prose = (
        "Erstens bleibt die Personaldecke dünn. "
        "Zweitens erreichte die Verwaltung 42 Prozent. "
        "Drittens fehlt ein Zeitplan.\n"
        "\n"
        "Zweitens gilt das auch für den Rollout."
    )
    result = verify_prose(prose, ENUMERATION_POOL)

    assert result.rejected
    assert result.content.splitlines()[-1] == "Zweitens gilt das auch für den Rollout."


def test_an_ordinal_adverb_is_not_mistaken_for_a_reference_group():
    """"Drittens" zählt einen Punkt, es benennt keine Personengruppe.

    Ohne diese Abgrenzung wurde das Aufzählungswort zur Bezugsgruppe der Zahl,
    die echte Gruppe rutschte in den Scope, und der Satz fand seinen Beleg
    (oder seinen Widerspruch) nie.
    """
    facts = extract_numeric_facts("Drittens erreichte die Verwaltung 42 Prozent.")

    assert facts
    assert "verwaltung" in facts[0].subject.lower()


def test_leading_subject_is_assigned_to_the_right_number():
    """Die als ``xfail`` geführte Restlücke aus #1357, jetzt geschlossen.

    Steht die Bezugsgruppe vor der Zahl, fand ``_split_subject_predicate``
    rechts davon nichts — der Fakt entstand entweder gar nicht oder trug die
    nächstfolgende Gruppe. Beides machte die Zahl unprüfbar. Maßgeblich ist
    jetzt die Nominalphrase unmittelbar links der Zahl.
    """
    facts = extract_numeric_facts("Die Basisschulung erreichte in der Ärzteschaft 83 Prozent.")
    assert facts
    assert "ärzteschaft" in facts[0].subject.lower()


def test_marker_is_not_duplicated_on_repeated_runs():
    prose = "Zudem stehen 61 Prozent der Beschäftigten der Einführung kritisch gegenüber."
    once = verify_prose(prose, UNRELATED_POOL)
    twice = verify_prose(once.content, UNRELATED_POOL)
    assert twice.content.count(UNVERIFIED_MARKER) == 1


def test_empty_pool_leaves_the_text_untouched():
    """Eine Prüfung ohne Vergleichsbasis ist keine bestandene Prüfung."""
    prose = "Zudem stehen 61 Prozent der Beschäftigten der Einführung kritisch gegenüber."
    result = verify_prose(prose, [])
    assert result.content == prose
    assert not result.changed
