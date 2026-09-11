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
