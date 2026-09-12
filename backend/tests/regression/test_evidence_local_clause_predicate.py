"""Regression: eine eigenstaendige Nebenklausel erbt nicht das Kopf-Praedikat.

Root Cause: ``_full_predicate`` faellt auf den Satzkopf zurueck, sobald der Teil
rechts der Zahl weniger als ``_TAIL_PREDICATE_MIN_TOKENS`` Inhaltswoerter
traegt. Das ist fuer ein Aufzaehlungsglied richtig — "18 Lehrkraefte und" hat
gar keine eigene Aussage, sie steht im Kopf und gilt fuer alle Glieder. Fuer
eine durch Semikolon abgetrennte eigene Klausel ist es falsch: "18 Lehrkraefte
streikten" behauptet ``streikten``, nicht ``kamen``.

Der Fallback darf deshalb nicht ueber die Tokenzahl allein entschieden werden
(``_TAIL_PREDICATE_MIN_TOKENS = 1`` wuerde die Aufzaehlung beschaedigen),
sondern ueber die Satzstruktur: hinter einem Klauseltrenner beginnt eine neue
Aussage, hinter einem Aufzaehlungskomma nicht.
"""

from __future__ import annotations

import pytest

from app.services.evidence_entailment import extract_numeric_facts


def _by_value(text: str) -> dict[float, str]:
    return {fact.value: fact.predicate for fact in extract_numeric_facts(text)}


class TestLocalClauseKeepsItsOwnPredicate:
    def test_semicolon_clause_does_not_inherit_the_head(self) -> None:
        predicates = _by_value("Im Pilotprojekt kamen 120 Teilnehmende; 18 Lehrkräfte streikten.")

        assert "kamen" in predicates[120.0]
        assert "streikten" in predicates[18.0]
        assert "kamen" not in predicates[18.0]

    @pytest.mark.parametrize("separator", [";", ":", "—", " – "])
    def test_every_clause_separator_starts_a_new_statement(self, separator: str) -> None:
        text = f"Im Pilotprojekt kamen 120 Teilnehmende{separator} 18 Lehrkräfte streikten."

        predicates = _by_value(text)

        assert "streikten" in predicates[18.0]
        assert "kamen" not in predicates[18.0]


class TestEnumerationStillSharesTheHead:
    def test_comma_enumeration_keeps_the_shared_head_predicate(self) -> None:
        """Das Gegenstueck: hier haben die hinteren Glieder keine eigene
        Aussage. Was sie behaupten, steht im Kopf und gilt fuer alle drei."""
        predicates = _by_value(
            "Der Pilot umfasst 120 Teilnehmende, 18 Lehrkräfte und sechs Angebote."
        )

        assert predicates[120.0] == "Der Pilot umfasst"
        assert predicates[18.0] == "Der Pilot umfasst"
        assert predicates[6.0] == "Der Pilot umfasst"

    def test_two_member_enumeration_keeps_the_head(self) -> None:
        predicates = _by_value("Die Stelle betreut 40 Familien und 12 Einrichtungen.")

        # Beide Glieder tragen dasselbe Kopf-Praedikat; das angehaengte "und"
        # beim ersten stammt aus dessen Tail und ist bestehendes Verhalten.
        assert "betreut" in predicates[40.0]
        assert "betreut" in predicates[12.0]


class TestUnchangedBehaviour:
    def test_single_number_sentence_with_leading_vorfeld(self) -> None:
        predicates = _by_value("Auf der Personalliste des Trägers stehen 31 Honorarkräfte.")

        assert "stehen" in predicates[31.0]

    def test_percent_sentence_keeps_its_vorfeld_predicate(self) -> None:
        """Beim Prozentmuster wird das Bezugsnomen zum Subjekt; die Aussage
        steht im Vorfeld. Bestehendes Verhalten, hier festgehalten."""
        predicates = _by_value("Die Verwaltung erreichte 91 Prozent der gesetzten Ziele.")

        assert "erreichte" in predicates[91.0]


class TestSeparatorBeforeTheFirstNumber:
    """Codex-Befund P1 auf PR #1498 — Regression aus dem Klauseltrenner-Fix.

    Steht der Trenner *vor* der ersten Zahl, gibt es keine vorangehende
    numerische Klausel, von der sich etwas abgrenzen liesse: der Satzkopf IST
    dann die Aussage. Die Unterdrueckung des Kopfes hat den Prefix auf
    Leerzeichen reduziert und ein leeres Praedikat erzeugt — Claim und Evidence
    wurden anschliessend ueber ``predicate_not_measurable`` als ``INSUFFICIENT``
    gewertet statt als belegt.
    """

    @pytest.mark.parametrize(
        "text, expected_token",
        [
            pytest.param("Die Studie ergab: 120 Teilnehmende.", "ergab", id="colon"),
            pytest.param("Der Bericht nennt — 45 Prozent der Betriebe.", "nennt", id="emdash"),
            pytest.param("Der Träger beschäftigt — 31 Honorarkräfte.", "beschäftigt", id="emdash-absolute"),
            pytest.param("Zum Stichtag – 31 Honorarkräfte.", "Stichtag", id="endash"),
        ],
    )
    def test_head_survives_a_separator_before_the_first_number(
        self, text: str, expected_token: str
    ) -> None:
        predicates = list(_by_value(text).values())

        assert predicates, f"kein Fakt extrahiert aus {text!r}"
        assert any(p.strip() for p in predicates), f"leeres Praedikat fuer {text!r}"
        assert any(expected_token in p for p in predicates), predicates

    def test_separator_before_the_first_number_with_its_own_tail_is_unaffected(self) -> None:
        """Traegt der Teil rechts der Zahl selbst eine Aussage, wird der Kopf
        ohnehin nicht gebraucht — dieser Pfad bleibt unveraendert."""
        predicates = _by_value("Kurz gesagt; 31 Honorarkräfte arbeiten dort.")

        assert predicates[31.0] == "arbeiten dort"

    def test_later_span_after_a_separator_still_drops_the_head(self) -> None:
        """Die eigentliche Wirkung des Fixes bleibt erhalten."""
        predicates = _by_value("Im Pilotprojekt kamen 120 Teilnehmende; 18 Lehrkräfte streikten.")

        assert "streikten" in predicates[18.0]
        assert "kamen" not in predicates[18.0]

