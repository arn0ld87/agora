"""Issue #1247 — Nicht-Stakeholder werden Personas, weil die Prüfung am Typ hängt.

Die Blockliste in ``persona_eligibility`` funktioniert nachweislich — sie
schließt ``Technology``, ``City`` und ``Date`` korrekt aus. Sie schützt
trotzdem nicht: Gemessen über zwei Referenzläufe tragen **28 von 29
Nicht-Stakeholdern den Typ ``Organization``** — ``Moodle``, ``ChatGPT``,
``granite-4.0-h-tiny``, ``GPU-Server``, ``Magdeburg``, ``AZAV-Zulassung``,
``Kursstart Februar 2027``, ``Abschnitt 7 (U1–U5)``.

``organization`` kann nicht auf die Blockliste: Bildungsträger, Betriebe und
Behörden sind legitime Stakeholder-Organisationen. Die Blockliste ist
strukturell nicht in der Lage, diesen Fall zu fangen.

Ein enger gefasstes Typvokabular hilft ebenfalls nicht. Ein Lauf lieferte
ausschließlich kanonische Typen (``Organization``, ``Person``, ``Student``,
``Professor``, ``Company``, ``GovernmentAgency``) — und trotzdem landeten 16
von 16 Nicht-Stakeholdern in ``Organization``. Der Typ ist gleichzeitig
legitimes Label und Auffangtopf für alles Unklare.

Wirkung, bis in die Evidence belegt: In den Reports der Referenzläufe treten
``Technische Mitarbeiterin im Rechenzentrum Magdeburg`` und ``Teamleiterin
AZAV-Zulassung bei der Agentur für Arbeit`` (6 Zitate) als zitierte Quellen
auf. Ein Slot, der leer bleibt, wäre hinnehmbar. Ein Slot, der mitredet und
zitiert wird, verfälscht das Ergebnis.

Zweiter Teil: Die typunabhängige Prüfung fällt erst im Generierungsaufruf,
also **nach** dem ``max_agents``-Cap. Ohne Nachbesetzung unterschreitet jede
Ablehnung den konfigurierten Wert — bei einem Cap von 30 (nach eigener
Empfehlung der Floor ohne Puffer) und einer beobachteten Ablehnungsquote von
bis zu 32 % wäre das der Unterschied zwischen 30 und 20 Stimmen.
"""

from __future__ import annotations

import pytest

from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import (
    OasisProfileGenerator,
    PersonaIneligible,
)


def _entity(name: str, entity_type: str, summary: str = "") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=[entity_type, "Entity"],
        summary=summary or f"{name} im Kontext der Umschulung.",
        attributes={},
    )


@pytest.fixture()
def generator():
    return OasisProfileGenerator(
        api_key="test", base_url="http://localhost", language="de"
    )


# ------------------------------------------------------ Teil 1: Ablehnung


class TestTypunabhaengigeEignungspruefung:
    def test_prompt_erlaubt_dem_modell_eine_ablehnung(self, generator):
        """Ohne diesen Block hat das Modell keine Alternative zur Erfindung."""
        block = generator._build_eligibility_prompt_block("Moodle", "Organization")

        assert "ineligible" in block
        assert "Moodle" in block
        # Der Typ darf ausdrücklich nicht als Antwort gelten — genau daran
        # scheitert die Blockliste.
        assert "Hinweis, keine Antwort" in block

    def test_legitimer_typ_mit_nicht_menschlichem_traeger_wird_abgelehnt(
        self, generator, monkeypatch
    ):
        """``Moodle`` als ``Organization`` — der beobachtete Hauptfall.

        RED ohne den Fix: die Entität durchläuft die Generierung und wird zu
        einer Persona mit erfundener Vita.
        """
        monkeypatch.setattr(
            generator,
            "_generate_profile_with_llm",
            lambda **kwargs: {
                "ineligible": True,
                "ineligible_reason": "Moodle ist eine Lernplattform, keine Personengruppe",
            },
        )

        with pytest.raises(PersonaIneligible) as excinfo:
            generator.generate_profile_from_entity(
                _entity("Moodle", "Organization"), user_id=1, use_llm=True
            )

        assert excinfo.value.entity_name == "Moodle"
        assert "Lernplattform" in excinfo.value.reason

    def test_ablehnung_ohne_begruendung_bekommt_einen_verstaendlichen_default(
        self, generator, monkeypatch
    ):
        monkeypatch.setattr(
            generator,
            "_generate_profile_with_llm",
            lambda **kwargs: {"ineligible": True},
        )

        with pytest.raises(PersonaIneligible) as excinfo:
            generator.generate_profile_from_entity(
                _entity("Magdeburg", "Organization"), user_id=1, use_llm=True
            )

        assert excinfo.value.reason

    def test_legitimer_stakeholder_wird_nicht_abgelehnt(self, generator, monkeypatch):
        """Gegenprobe: ein Bildungsträger ist ein Stakeholder und bleibt einer."""
        monkeypatch.setattr(
            generator,
            "_generate_profile_with_llm",
            lambda **kwargs: {
                "ineligible": False,
                "display_name": "Nordharz Bildungswerk gGmbH",
                "handle": "nordharz",
                "bio": "Bildungsträger",
                "persona": "Der Träger verantwortet die Umschulungen.",
                "country": "DE",
                "voice_register": "formal-de",
            },
        )

        profile = generator.generate_profile_from_entity(
            _entity("Nordharz Bildungswerk gGmbH", "Organization"),
            user_id=1,
            use_llm=True,
        )

        assert profile is not None
        assert profile.name == "Nordharz Bildungswerk gGmbH"

    def test_regelbasierter_pfad_lehnt_nie_ab(self, generator):
        """Ohne Modell gibt es niemanden, der die Frage beantworten könnte.

        Der regelbasierte Pfad ist der Notbehelf nach drei gescheiterten
        LLM-Versuchen — dort zusätzlich abzulehnen hieße, einen Ausfall in
        einen Ausschluss umzudeuten.
        """
        profile = generator.generate_profile_from_entity(
            _entity("Moodle", "Organization"), user_id=1, use_llm=False
        )

        assert profile is not None


# ------------------------------------------------- Teil 2: Nachbesetzung


class TestNachbesetzungNachAblehnung:
    def test_abgelehnter_platz_wird_aus_der_reserve_nachbesetzt(
        self, generator, monkeypatch
    ):
        """RED ohne den Fix: der Platz bleibt leer, max_agents wird unterschritten."""
        rejects = {"Moodle"}

        def fake_llm(**kwargs):
            name = kwargs["entity_name"]
            if name in rejects:
                return {"ineligible": True, "ineligible_reason": "kein Träger"}
            return {
                "ineligible": False,
                "display_name": name,
                "handle": name.lower(),
                "bio": "",
                "persona": f"{name} nimmt teil.",
                "age": 40,
                "gender": "female",
                "mbti": "INTJ",
                "country": "DE",
                "profession": "",
                "voice_register": "neutral-de",
            }

        monkeypatch.setattr(generator, "_generate_profile_with_llm", fake_llm)

        profiles = generator.generate_profiles_from_entities(
            entities=[_entity("Betriebsrat", "WorksCouncil"), _entity("Moodle", "Organization")],
            use_llm=True,
            parallel_count=1,
            reserve_entities=[_entity("Honorarkraft", "Lecturer")],
        )

        names = sorted(p.name for p in profiles if p is not None)
        assert "Moodle" not in names
        assert names == ["Betriebsrat", "Honorarkraft"], (
            f"Der abgelehnte Platz wurde nicht nachbesetzt: {names}"
        )

    def test_leere_reserve_laesst_den_platz_leer_statt_zu_erfinden(
        self, generator, monkeypatch
    ):
        """Ohne Nachrücker ist ein leerer Platz das ehrliche Ergebnis."""
        monkeypatch.setattr(
            generator,
            "_generate_profile_with_llm",
            lambda **kwargs: {"ineligible": True, "ineligible_reason": "kein Träger"},
        )

        profiles = generator.generate_profiles_from_entities(
            entities=[_entity("Moodle", "Organization")],
            use_llm=True,
            parallel_count=1,
            reserve_entities=[],
        )

        assert [p for p in profiles if p is not None] == []

    def test_auch_der_nachruecker_darf_abgelehnt_werden(self, generator, monkeypatch):
        """Die Reserve wird weitergezogen, bis ein Kandidat trägt."""
        rejects = {"Moodle", "ChatGPT"}

        def fake_llm(**kwargs):
            name = kwargs["entity_name"]
            if name in rejects:
                return {"ineligible": True, "ineligible_reason": "kein Träger"}
            return {
                "ineligible": False,
                "display_name": name,
                "handle": name.lower(),
                "bio": "",
                "persona": f"{name} nimmt teil.",
                "age": 40,
                "gender": "female",
                "mbti": "INTJ",
                "country": "DE",
                "profession": "",
                "voice_register": "neutral-de",
            }

        monkeypatch.setattr(generator, "_generate_profile_with_llm", fake_llm)

        profiles = generator.generate_profiles_from_entities(
            entities=[_entity("Moodle", "Organization")],
            use_llm=True,
            parallel_count=1,
            reserve_entities=[
                _entity("ChatGPT", "Organization"),
                _entity("Kostenträger", "FundingAgency"),
            ],
        )

        names = [p.name for p in profiles if p is not None]
        assert names == ["Kostenträger"]

    def test_ohne_ablehnung_bleibt_die_reserve_unangetastet(
        self, generator, monkeypatch
    ):
        """Gegenprobe: der Normalfall darf sich nicht ändern."""
        monkeypatch.setattr(
            generator,
            "_generate_profile_with_llm",
            lambda **kwargs: {
                "ineligible": False,
                "display_name": kwargs["entity_name"],
                "handle": kwargs["entity_name"].lower(),
                "bio": "",
                "persona": f"{kwargs['entity_name']} nimmt teil.",
                "age": 40,
                "gender": "female",
                "mbti": "INTJ",
                "country": "DE",
                "profession": "",
                "voice_register": "neutral-de",
            },
        )

        profiles = generator.generate_profiles_from_entities(
            entities=[_entity("Betriebsrat", "WorksCouncil")],
            use_llm=True,
            parallel_count=1,
            reserve_entities=[_entity("Honorarkraft", "Lecturer")],
        )

        names = [p.name for p in profiles if p is not None]
        assert names == ["Betriebsrat"]


# ----------------------------------------------- Teil 3: Reserve im Prepare


class TestReservePoolAusDemCap:
    def test_der_cap_legt_die_weggeschnittenen_kandidaten_in_die_reserve(self):
        """Was der Cap wegschneidet, muss als Nachrücker verfügbar bleiben."""
        from app.services.entity_reader import FilteredEntities
        from app.services.prepare_service import _cap_entities_across_types

        entities = [
            _entity("A", "Alpha"),
            _entity("B", "Beta"),
            _entity("C", "Gamma"),
            _entity("D", "Delta"),
        ]
        capped = _cap_entities_across_types(entities, 2)
        selected_uuids = {e.uuid for e in capped}
        reserve = [e for e in entities if e.uuid not in selected_uuids]

        assert len(capped) == 2
        assert len(reserve) == 2
        assert selected_uuids.isdisjoint({e.uuid for e in reserve})

        filtered = FilteredEntities(
            entities=capped,
            entity_types={"Alpha", "Beta"},
            total_count=4,
            filtered_count=2,
            reserve_entities=reserve,
        )
        assert len(filtered.reserve_entities) == 2
        # Die Reserve ist ein internes Auswahldetail, kein Prepare-Ergebnis.
        assert "reserve_entities" not in filtered.to_dict()

    def test_ohne_cap_gibt_es_keine_reserve(self):
        """Reicht der Pool nicht über den Cap hinaus, gibt es nichts nachzurücken."""
        from app.services.entity_reader import FilteredEntities

        filtered = FilteredEntities(
            entities=[_entity("A", "Alpha")],
            entity_types={"Alpha"},
            total_count=1,
            filtered_count=1,
        )

        assert filtered.reserve_entities == []
