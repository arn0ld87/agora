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
