"""Issue #1492: Die Faktenzerlegung darf einem Fakt nicht die Nachbarn anhängen.

Beobachtet in Bericht ``report_6daa7796257e`` (Projekt „LernPilot 2027"):
Sätze trugen ``[Beleg fehlt]``, deren Zahlen wörtlich im Seed stehen.

    > 120 Teilnehmende, 18 Lehrkräfte und sechs Qualifizierungsangebote … [Beleg fehlt]

Die Prüfung läuft seit #1356 pro numerischem Fakt, nicht pro Satz — der
Ausschnitt *je Fakt* endete aber weiterhin erst am Satzende. Für die 120
entstand damit das Prädikat „18 Lehrkräfte und sechs Qualifizierungsangebote":
keine einzelne Quelle konnte das decken, und der Satz wurde entwertet.

Im Prozentfall war die Folge schwerer als gemeldet. Die Evidenz
„18 % … 44 % …" trug in ihrem 18-%-Fakt das Prädikat der 44 % mit. Gegen den
44-%-Fakt des Berichts ergab das „gleiche Aussage über dieselbe Gruppe,
abweichender Zahlenwert" — ``CONTRADICTED``. Der Satz wurde nicht markiert,
sondern **gelöscht**, obwohl er mit der Quelle identisch war.

Zusätzlich lief die Absolutzahl-Extraktion nur, wenn der Satz *keine*
Prozentangabe enthielt. Ein gemischter Satz verlor seine Absolutzahlen
vollständig — sie tauchten in keinem Fakt auf und waren damit weder belegbar
noch widerlegbar.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services.evidence_entailment import (
    EntailmentVerdict,
    extract_numeric_facts,
)
from app.services.report_agent.text_verification import (
    UNVERIFIED_MARKER,
    verify_prose,
)

# Der Seed aus dem Issue, indikativ formuliert. Die Modalitätsprüfung
# (Zielvorgabe vs. Ist-Wert) ist ein eigener, gewollter Mechanismus und wird
# hier bewusst nicht mitgetestet — sie hat mit der Faktenzerlegung nichts zu tun.
SEED_PILOT = (
    "Der Pilot umfasst 120 Teilnehmende, 18 Lehrkräfte und sechs "
    "Qualifizierungsangebote."
)
SEED_SURVEY = (
    "18 % der Lehrkräfte lehnen KI ab, 44 % der Lehrkräfte nutzen KI bereits."
)


def _pool(*snippets: str) -> List[Dict[str, Any]]:
    return [
        {
            "snippet": snippet,
            "source_kind": "seed_corpus",
            "type": "seed_document",
        }
        for snippet in snippets
    ]


# --------------------------------------------------------------------------- #
# Zerlegung
# --------------------------------------------------------------------------- #

def test_every_number_of_a_bundled_sentence_becomes_a_fact():
    """Alle drei Angaben des Seed-Satzes, auch das Zahlwort."""
    facts = extract_numeric_facts(SEED_PILOT)
    assert sorted(f.value for f in facts) == [6.0, 18.0, 120.0]


def test_each_fact_keeps_only_its_own_predicate():
    """Kern des Fehlers: der Fakt der 120 trug die 18 in seinem Prädikat."""
    facts = {f.value: f for f in extract_numeric_facts(SEED_PILOT)}

    assert "18" not in facts[120.0].predicate, (
        f"Fakt 120 traegt eine fremde Zahl im Praedikat: {facts[120.0].predicate!r}"
    )
    assert "120" not in facts[18.0].predicate, (
        f"Fakt 18 traegt eine fremde Zahl im Praedikat: {facts[18.0].predicate!r}"
    )


def test_percent_facts_do_not_share_predicates():
    facts = {f.value: f for f in extract_numeric_facts(SEED_SURVEY)}

    assert facts[18.0].predicate.strip() == "lehnen KI ab"
    assert facts[44.0].predicate.strip() == "nutzen KI bereits"


def test_absolute_numbers_survive_next_to_a_percentage():
    """Gemischter Satz: vorher ging die Absolutzahl vollstaendig verloren."""
    facts = extract_numeric_facts(
        "Von 120 Teilnehmenden lehnen 18 % der Lehrkräfte die Nutzung ab."
    )
    values = sorted(f.value for f in facts)

    assert 120.0 in values, f"Absolutzahl verloren, gefunden: {values}"
    assert 18.0 in values


def test_percentage_does_not_also_become_an_absolute_fact():
    """„18 % der Lehrkräfte" darf nicht zusaetzlich „18 Lehrkräfte" erzeugen."""
    facts = extract_numeric_facts("18 % der Lehrkräfte lehnen KI ab.")

    assert len(facts) == 1
    assert facts[0].unit == "percent"


def test_raw_sentence_is_preserved_on_every_fact():
    """Die Zerlegung darf den Kontext einschraenken, nicht loeschen."""
    for fact in extract_numeric_facts(SEED_PILOT):
        assert fact.raw == SEED_PILOT


# --------------------------------------------------------------------------- #
# Wirkung auf den Fließtext
# --------------------------------------------------------------------------- #

def test_belegter_bundelsatz_bekommt_keinen_marker():
    result = verify_prose(SEED_PILOT, _pool(SEED_PILOT))

    assert UNVERIFIED_MARKER not in result.content
    assert not result.unverified
    assert not result.rejected


def test_identischer_prozentsatz_wird_nicht_als_widerspruch_geloescht():
    """Der schwerere Teilbefund: der Satz verschwand komplett aus dem Bericht."""
    result = verify_prose(SEED_SURVEY, _pool(SEED_SURVEY))

    assert not result.rejected, (
        "ein Satz, der mit seiner Quelle identisch ist, darf nicht als "
        f"Widerspruch entfernt werden: {[r.reason for r in result.rejected]}"
    )
    assert UNVERIFIED_MARKER not in result.content


def test_beide_seed_saetze_zusammen_bleiben_unveraendert():
    content = f"{SEED_PILOT}\n{SEED_SURVEY}"
    result = verify_prose(content, _pool(SEED_PILOT, SEED_SURVEY))

    assert result.content.strip() == content.strip()
    assert not result.changed


# --------------------------------------------------------------------------- #
# Gegenprobe — das Gate darf nicht stumpf werden
# --------------------------------------------------------------------------- #

def test_erfundene_zahl_wird_weiterhin_markiert():
    """Ohne diese Gegenprobe waere der Fix nur ein abgeschaltetes Gate."""
    content = "Zusätzlich nahmen 99 Schulleitungen an der Befragung teil."
    result = verify_prose(content, _pool(SEED_PILOT, SEED_SURVEY))

    assert UNVERIFIED_MARKER in result.content
    assert [u.verdict for u in result.unverified] == [EntailmentVerdict.INSUFFICIENT]


def test_abweichender_wert_derselben_kennzahl_bleibt_ein_widerspruch():
    """Echte Widersprueche muessen weiterhin greifen."""
    content = "71 % der Lehrkräfte nutzen KI bereits."
    result = verify_prose(content, _pool(SEED_SURVEY))

    assert result.rejected, "abweichender Wert derselben Kennzahl muss entfernt werden"
    assert result.rejected[0].verdict is EntailmentVerdict.CONTRADICTED


# --------------------------------------------------------------------------- #
# Ausgeschriebene Zahlwoerter (#1492, Restbefund)
# --------------------------------------------------------------------------- #

def test_ausgeschriebene_zahlwoerter_werden_erkannt():
    """Die deutsche Schreibkonvention setzt Zahlen bis zwoelf als Wort.

    "sechs Qualifizierungsangebote" ist derselbe pruefbare Fakt wie "6
    Qualifizierungsangebote", erzeugte aber keinen NumericFact, weil beide
    Muster eine Ziffer verlangten.
    """
    values = [f.value for f in extract_numeric_facts(SEED_PILOT)]
    assert 6.0 in values


def test_zahlwort_am_satzanfang():
    values = [f.value for f in extract_numeric_facts("Sechs Angebote entstanden.")]
    assert values == [6.0]


@pytest.mark.parametrize(
    "sentence",
    [
        "Eine Lehrkraft berichtet von Zeitgewinn.",
        "Ein Angebot wurde eingerichtet.",
        "Einer der Beteiligten widersprach.",
    ],
)
def test_unbestimmter_artikel_wird_nicht_zur_mengenangabe(sentence: str):
    """Gegenprobe — der wichtigste Fehlerfall dieser Erweiterung.

    "ein"/"eine" ist im Deutschen weit oefter Artikel als Zahlwort. Wuerde es
    mitgezaehlt, entstuende aus "eine Lehrkraft berichtet" der Fakt
    "1 Lehrkraft" — eine Mengenbehauptung, die der Satz nicht aufstellt, und
    damit eine vom Trust-Layer selbst erfundene Zahl.
    """
    assert extract_numeric_facts(sentence) == []


def test_zahlwort_im_wortinneren_ist_kein_treffer():
    """"Entzweiung" enthaelt "zwei", ist aber keine Mengenangabe."""
    assert extract_numeric_facts("Die Entzweiung der Gruppe schritt voran.") == []


def test_ausgeschriebene_prozentangabe():
    facts = extract_numeric_facts("Acht Prozent der Lehrkräfte lehnen ab.")
    assert [(f.value, f.unit) for f in facts] == [(8.0, "percent")]


def test_ausgeschriebene_zahl_ist_belegbar():
    """Die Angabe ist jetzt nicht nur sichtbar, sondern auch pruefbar."""
    result = verify_prose(SEED_PILOT, _pool(SEED_PILOT))
    assert UNVERIFIED_MARKER not in result.content


# --------------------------------------------------------------------------- #
# Präzision der Beanstandung (#1492, Lösungsrichtung 3)
# --------------------------------------------------------------------------- #

def test_beanstandung_benennt_die_konkrete_zahl():
    """Der Marker entwertete den ganzen Satz, ohne die Zahl zu nennen."""
    result = verify_prose(
        "Zusätzlich nahmen 99 Schulleitungen teil.", _pool(SEED_SURVEY)
    )

    assert len(result.unverified) == 1
    assert "99 Schulleitungen" in result.unverified[0].reason


def test_teilweise_belegter_satz_ist_von_gaenzlich_unbelegtem_unterscheidbar():
    """`partial_evidence` vs. echtes `missing_evidence`.

    Beide tragen denselben sichtbaren Marker — die strukturierte Begründung
    muss den Unterschied trotzdem hergeben, sonst kann ein Leser einen Satz
    mit zwei belegten und einer offenen Zahl nicht von einem ohne jeden Beleg
    unterscheiden.
    """
    partial = verify_prose(
        "18 % der Lehrkräfte lehnen KI ab, 71 Schulleitungen nahmen teil.",
        _pool(SEED_SURVEY),
    )
    missing = verify_prose(
        "Zusätzlich nahmen 99 Schulleitungen teil.", _pool(SEED_SURVEY)
    )

    assert "1 der 2 Zahlenangaben" in partial.unverified[0].reason
    assert "Zahlenangaben" not in missing.unverified[0].reason


def test_beanstandungsgrund_passt_in_den_contract_slot():
    """`ReportSectionUnverifiedStatementModel.reason` erlaubt 200 Zeichen."""
    result = verify_prose(
        "18 % der Lehrkräfte lehnen KI ab, 71 Schulleitungen nahmen teil.",
        _pool(SEED_SURVEY),
    )

    for statement in result.unverified:
        assert len(statement.reason) <= 200


def test_hypothese_traegt_die_konkrete_zahl_weiter():
    """Die Hypothese ist der Ort, an dem ein Auditor den Grund nachliest."""
    result = verify_prose(
        "Zusätzlich nahmen 99 Schulleitungen teil.", _pool(SEED_SURVEY)
    )

    hypothesis = result.unverified[0].as_hypothesis(1)
    assert "99 Schulleitungen" in hypothesis["rationale"]


# --------------------------------------------------------------------------- #
# Zahlenspannen sind keine Punktwerte
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "sentence",
    [
        "Dozenten berichten sechs bis neun Stunden Nacharbeit pro Woche.",
        "Es waren 6 bis 9 Stunden.",
        "Zwischen 40 und 60 Prozent der Lehrkräfte stimmen zu.",
        "Es nahmen zwischen sechs und neun Schulen teil.",
    ],
)
def test_spannen_erzeugen_keinen_punktfakt(sentence: str):
    """Eine Spanne behauptet keinen exakten Wert.

    Vorher wurde aus "sechs bis neun Stunden" der Fakt `6 Stunden` mit
    `BoundKind.EXACT` — eine Genauigkeit, die der Satz nicht aufstellt. Gegen
    eine Quelle mit derselben Spanne ergab das ein Fehlurteil. Die
    Vergleichslogik kennt nur Punktwerte und Schranken; eine Spanne laesst sich
    darin nicht ehrlich abbilden, also entsteht gar kein Fakt.
    """
    assert extract_numeric_facts(sentence) == []


def test_aufzaehlung_ist_keine_spanne():
    """Gegenprobe: ein blosses "und" zwischen zwei Zahlen zaehlt auf.

    Ohne diese Abgrenzung haette die Spannenerkennung den Kernfall dieses
    Issues selbst zerstoert — "120 Teilnehmende und 18 Lehrkraefte" sind zwei
    Fakten, keine Spanne.
    """
    values = [f.value for f in extract_numeric_facts(
        "Der Pilot umfasst 120 Teilnehmende und 18 Lehrkräfte."
    )]
    assert sorted(values) == [18.0, 120.0]


def test_bis_zu_bleibt_eine_obergrenze():
    """`bis zu` ist eine Schranke, kein Spannenende — der Fakt muss bleiben."""
    facts = extract_numeric_facts("Die Nacharbeit dauert bis zu neun Stunden.")
    assert [(f.value, f.bound.value) for f in facts] == [(9.0, "at_most")]


# --------------------------------------------------------------------------- #
# Aus dem Review: Teilaussagen und "von X bis zu Y"
# --------------------------------------------------------------------------- #

def test_praedikat_traegt_kein_fremdes_verb():
    """Satzzeichen trennen Teilaussagen.

    In "120 Teilnehmende kamen; 18 Lehrkraefte streikten" reichte der
    Ausschnitt der zweiten Zahl bis hinter das Verb der ersten — der Fakt
    "18 Lehrkraefte" bekam das Praedikat "kamen streikten" und damit eine
    Aussage, die der Satz ueber ihn gar nicht trifft.
    """
    facts = {f.value: f for f in extract_numeric_facts(
        "120 Teilnehmende kamen; 18 Lehrkräfte streikten."
    )}

    assert facts[120.0].predicate.strip() == "kamen"
    assert facts[18.0].predicate.strip() == "streikten"


def test_aufzaehlung_teilt_sich_weiterhin_den_satzkopf():
    """Gegenprobe: das Komma trennt keine Teilaussagen.

    In einer Aufzaehlung tragen die Glieder kein eigenes Praedikat — was sie
    behaupten, steht im Satzkopf und gilt fuer alle.
    """
    facts = extract_numeric_facts(SEED_PILOT)
    assert {f.predicate.strip() for f in facts} == {"Der Pilot umfasst"}


def test_von_x_bis_zu_y_ist_eine_spanne():
    """`von sechs bis zu neun Stunden` hat eine Unter- und eine Obergrenze.

    Ohne diese Form entstand daraus der Fakt "9 Stunden (AT_MOST)" — die
    Untergrenze fiel weg und die Aussage wurde enger, als der Satz sie macht.
    """
    assert extract_numeric_facts(
        "Die Nacharbeit dauert von sechs bis zu neun Stunden."
    ) == []


def test_bis_zu_ohne_startwert_bleibt_obergrenze():
    """Gegenprobe zur Abgrenzung: ohne `von` ist es eine echte Schranke."""
    facts = extract_numeric_facts("Die Nacharbeit dauert bis zu neun Stunden.")
    assert [(f.value, f.bound.value) for f in facts] == [(9.0, "at_most")]
