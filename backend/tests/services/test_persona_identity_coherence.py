"""Issue #1246 — Personas müssen kohärent sie selbst sein.

Drei Symptome, ein Ursachenbild: Der Generator ist gezwungen, eine Person zu
beschreiben, auch wo keine ist, und niemand prüft anschließend, ob die
beschriebene Person dieselbe ist wie die benannte.

**P1 — Identitätsbruch.** ``display_name`` und der Name im ``persona``-Freitext
beschreiben verschiedene Menschen, häufig mit abweichendem Geschlecht:

    username=katharina_schäfer_846   persona: "Sabine Krüger …"
    username=felix_krause_452        persona: "Klaus Weber …"

Der Interview-Systemprompt setzt beides zusammen — „Du bist <label>" und
direkt darunter ein Profil, in dem jemand anders beschrieben wird. Die Persona
bekommt zwei Identitäten in derselben Nachricht. Das ist die plausibelste
Erklärung für die beobachtete Rollenübernahme (eine Technikerin antwortet „Als
Betriebsrat hätte ich…").

**P2 — Organisationen werden Einzelpersonen.** Aus `Nordharz Bildungswerk gGmbH`
(`source_entity_type: Organization`) wurde `juergen_hartmann_nhb_832` mit
`profession: "Dozent für IT-Umschulungen und Betriebsratsmitglied"`. Weder
„Dozent" noch „Betriebsratsmitglied" ist aus einem Bildungsträger ableitbar.
Die Ursache ist strukturell: Eine gGmbH hat kein Alter, kein Geschlecht, keinen
MBTI-Typ und keine Berufsbezeichnung — der Generator musste all das erfinden.

**P3 — Degradierter Pfad.** Wo nichts abzuleiten war, reichte der Generator den
Entitätstyp wörtlich als Beruf durch: ``profession: "AIProvider"``,
``"WorkingGroup"``, ``"TechnologyVendor"``.
"""

from __future__ import annotations

import json


import pytest

from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import (
    OasisProfileGenerator,
    PersonaDemographicSlot,
)


@pytest.fixture()
def generator():
    return OasisProfileGenerator(
        api_key="test", base_url="http://localhost", language="de"
    )


def _entity(name: str, entity_type: str, summary: str = "") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=[entity_type, "Entity"],
        summary=summary or f"{name} im Kontext der Umschulung.",
        attributes={},
    )


# ---------------------------------------------------------------- P1


class TestIdentitaetsKohaerenz:
    """Der benannte und der beschriebene Mensch müssen derselbe sein."""

    def test_abweichender_name_im_freitext_wird_auf_den_anzeigenamen_gezogen(
        self, generator
    ):
        """RED ohne den Fix: der Freitext behält seinen eigenen Namen."""
        persona = (
            "Sabine Krüger, 47, arbeitet seit zwölf Jahren als Dozentin. "
            "Sabine schätzt klare Absprachen. Frau Krüger meldet sich selten zu Wort."
        )

        aligned = generator._align_persona_identity(persona, "Katharina Schäfer")

        assert "Sabine" not in aligned
        assert "Krüger" not in aligned
        assert aligned.startswith("Katharina Schäfer,")
        assert "Katharina schätzt klare Absprachen" in aligned
        assert "Frau Schäfer meldet sich selten zu Wort" in aligned

    def test_uebereinstimmender_name_bleibt_unveraendert(self, generator):
        """Gegenprobe: wo nichts bricht, wird nichts angefasst."""
        persona = "Katharina Schäfer, 47, ist Dozentin. Katharina mag Struktur."

        assert generator._align_persona_identity(persona, "Katharina Schäfer") == persona

    def test_freitext_ohne_eroeffnungsnamen_bleibt_unveraendert(self, generator):
        """Nicht jeder Text beginnt mit einem Namen — dann gibt es nichts zu ziehen."""
        persona = "Arbeitet seit zwölf Jahren als Dozentin und schätzt klare Absprachen."

        assert generator._align_persona_identity(persona, "Katharina Schäfer") == persona

    def test_leerer_anzeigename_laesst_den_freitext_in_ruhe(self, generator):
        persona = "Sabine Krüger, 47, ist Dozentin."

        assert generator._align_persona_identity(persona, "") == persona

    def test_generiertes_individuum_traegt_genau_eine_identitaet(self, generator):
        """Ende-zu-Ende über den regelbasierten Pfad."""
        entity = _entity("Dozent", "Person")
        slot = PersonaDemographicSlot(age=47, gender="female", mbti="INTJ")

        profile = generator.generate_profile_from_entity(
            entity, user_id=1, use_llm=False, demographic_slot=slot
        )

        assert profile.name, "Ohne Anzeigenamen ist die Frage nicht entscheidbar"
        first_name = profile.name.split()[0]
        assert first_name in profile.persona, (
            f"Der Freitext nennt nicht die benannte Person: name={profile.name!r} "
            f"persona={profile.persona[:120]!r}"
        )


# ---------------------------------------------------------------- P2


class TestKollektivPersona:
    """Eine Organisation bekommt keine erfundene Vita."""

    def test_organisation_wird_kollektiv_ohne_demografie(self, generator):
        """RED ohne den Fix: die gGmbH bekommt Alter, Geschlecht und MBTI."""
        entity = _entity("Nordharz Bildungswerk gGmbH", "Organization")
        slot = PersonaDemographicSlot(age=57, gender="male", mbti="ESTJ")

        profile = generator.generate_profile_from_entity(
            entity, user_id=1, use_llm=False, demographic_slot=slot
        )

        assert profile.persona_kind == "collective"
        assert profile.age is None, "Eine gGmbH hat kein Alter"
        assert profile.gender is None, "Eine gGmbH hat kein Geschlecht"
        assert profile.mbti is None, "Eine gGmbH hat keinen Persönlichkeitstyp"

    def test_kollektiv_traegt_keine_erfundene_individualrolle(self, generator):
        """`Dozent und Betriebsratsmitglied` war aus einem Traeger nicht ableitbar."""
        entity = _entity("Nordharz Bildungswerk gGmbH", "Organization")

        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        assert profile.profession is None, (
            f"Kollektiv-Persona traegt eine erfundene Rolle: {profile.profession!r}"
        )

    def test_kollektiv_spricht_unter_dem_eigenen_namen(self, generator):
        """Nicht `Juergen Hartmann, 57`, sondern der Traeger selbst."""
        entity = _entity("Nordharz Bildungswerk gGmbH", "Organization")

        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        assert profile.name == "Nordharz Bildungswerk gGmbH"

    def test_individuum_bleibt_individuum(self, generator):
        """Gegenprobe: der Personenpfad ist unveraendert."""
        entity = _entity("Dozent", "Person")
        slot = PersonaDemographicSlot(age=47, gender="female", mbti="INTJ")

        profile = generator.generate_profile_from_entity(
            entity, user_id=1, use_llm=False, demographic_slot=slot
        )

        assert profile.persona_kind == "individual"
        assert profile.age == 47
        assert profile.gender == "female"
        assert profile.mbti == "INTJ"

    def test_kollektiv_wird_serialisiert(self, generator):
        """Die Persona-Galerie und OASIS muessen die Ausprägung lesen koennen."""
        entity = _entity("Agentur für Arbeit", "GovernmentAgency")

        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        assert profile.to_reddit_format()["persona_kind"] == "collective"
        assert profile.to_twitter_format()["persona_kind"] == "collective"
        assert profile.to_dict()["persona_kind"] == "collective"

    def test_individuum_bleibt_im_serialisierten_format_erkennbar(self, generator):
        entity = _entity("Dozent", "Person")

        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        assert profile.to_reddit_format()["persona_kind"] == "individual"


# ---------------------------------------------------------------- P3


class TestEntitaetstypIstKeinBeruf:
    @pytest.mark.parametrize(
        "entity_type", ["AIProvider", "WorkingGroup", "TechnologyVendor", "Executive"]
    )
    def test_entitaetstyp_erscheint_nie_als_profession(self, generator, entity_type):
        """RED ohne den Fix: `profession` traegt woertlich den Typnamen."""
        entity = _entity("Irgendwas", entity_type)

        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        assert profile.profession != entity_type, (
            f"Der Entitaetstyp wird als Beruf durchgereicht: {profile.profession!r}"
        )

    def test_nicht_ableitbarer_beruf_bleibt_leer_statt_erfunden(self, generator):
        """Lieber keine Angabe als eine falsche."""
        entity = _entity("Irgendwas", "AIProvider")

        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        assert profile.profession in (None, "")


# ------------------------------------- Review-Findings (CodeRabbit PR #1257)


class TestKollektivUeberlebtDiePersistenz:
    """Die Kollektiv-Semantik darf nicht am finalen Speichern scheitern."""

    def test_reddit_json_fuellt_kollektiv_demografie_nicht_auf(
        self, generator, tmp_path
    ):
        """RED ohne den Fix: `_save_reddit_json` schrieb age=30, gender=other, mbti=ISTJ.

        Die Realtime-Datei war korrekt, der finale Save überschrieb sie — und
        genau diese Datei lesen Persona-Galerie und Simulation.
        """
        entity = _entity("Nordharz Bildungswerk gGmbH", "Organization")
        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        target = tmp_path / "reddit_profiles.json"
        generator._save_reddit_json([profile], str(target))
        written = json.loads(target.read_text(encoding="utf-8"))[0]

        assert "age" not in written or written["age"] is None
        assert "gender" not in written or written["gender"] is None
        assert "mbti" not in written or written["mbti"] is None

    def test_reddit_json_behaelt_die_oasis_defaults_fuer_individuen(
        self, generator, tmp_path
    ):
        """Gegenprobe: OASIS braucht für echte Personas weiterhin Werte."""
        entity = _entity("Dozent", "Person")
        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)
        profile.age = None
        profile.mbti = None

        target = tmp_path / "reddit_profiles.json"
        generator._save_reddit_json([profile], str(target))
        written = json.loads(target.read_text(encoding="utf-8"))[0]

        assert written["age"] == 30
        assert written["mbti"] == "ISTJ"
        assert written["gender"]


class TestKollektivNameUeberlebtDieDedup:
    def test_zwei_organisationen_mit_gleichem_schlusstoken_behalten_ihre_namen(
        self, generator
    ):
        """RED ohne den Fix: `GmbH` gilt als doppelter Nachname.

        Die zweite Organisation bekam einen zufälligen DACH-Personennamen,
        während ihr Personatext weiter die Organisation beschreibt — exakt der
        Identitätsbruch, den dieser Slice schließt.
        """
        entities = [
            _entity("Nordharz Bildungswerk gGmbH", "Organization"),
            _entity("Regionale Bildungswerke gGmbH", "Organization"),
        ]
        profiles = generator.generate_profiles_from_entities(
            entities=entities, use_llm=False, parallel_count=1
        )

        names = sorted(p.name for p in profiles if p is not None)
        assert names == [
            "Nordharz Bildungswerk gGmbH",
            "Regionale Bildungswerke gGmbH",
        ]


class TestSchemaTrenntIndividuumUndKollektiv:
    def test_kollektiv_schema_verlangt_keine_personenfelder(self):
        """Ein Kollektiv-Schema mit Pflicht-`age` liesse jeden LLM-Call scheitern."""
        from app.services.oasis_profile_generator import CollectivePersonaSchema

        fields = CollectivePersonaSchema.model_fields
        for person_field in ("age", "gender", "mbti", "display_name", "handle", "profession"):
            assert person_field not in fields, (
                f"{person_field} gehört nicht in den Kollektiv-Vertrag"
            )
        assert "persona" in fields and "voice_register" in fields

    def test_metadaten_pruefung_meldet_fuer_kollektive_keine_personenfelder(
        self, generator
    ):
        """RED ohne den Fix: `age`/`gender`/`mbti` fehlten → drei Retries → regelbasiert."""
        missing = generator._validate_profile_metadata(
            {"country": "DE", "voice_register": "formal-de"}, is_collective=True
        )

        assert missing == []

    def test_metadaten_pruefung_bleibt_fuer_individuen_streng(self, generator):
        missing = generator._validate_profile_metadata(
            {"country": "DE", "voice_register": "formal-de"}, is_collective=False
        )

        assert "age" in missing and "gender" in missing


class TestEroeffnungsnameBrauchtEineGrenze:
    def test_rollenformulierung_am_satzanfang_ist_kein_name(self, generator):
        """RED ohne den Fix: `Als IT-Leiter` wurde als Name ersetzt."""
        persona = "Als IT-Leiter verantwortet er den Rollout und schult die Teams."

        assert generator._align_persona_identity(persona, "Katharina Schäfer") == persona

    def test_name_mit_komma_wird_weiterhin_gezogen(self, generator):
        persona = "Sabine Krüger, 47, ist Dozentin."

        aligned = generator._align_persona_identity(persona, "Katharina Schäfer")
        assert aligned.startswith("Katharina Schäfer,")


class TestPersonaKindImVertrag:
    def test_persona_model_kennt_persona_kind(self):
        """`extra="forbid"` würde serialisierte Profile sonst ablehnen."""
        from app.contracts.persona_contract import PersonaModel

        assert "persona_kind" in PersonaModel.model_fields
