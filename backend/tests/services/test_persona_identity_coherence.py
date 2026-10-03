"""Issue #1246 — Personas müssen kohärent sie selbst sein.

Drei Symptome, ein Ursachenbild: Der Generator ist gezwungen, eine Person zu
beschreiben, auch wo keine ist, und niemand prüft anschließend, ob die
beschriebene Person dieselbe ist wie die benannte.

**P1 — Identitätsbruch.** ``display_name`` und der Name im ``persona``-Freitext
beschreiben verschiedene Menschen, häufig mit abweichendem Geschlecht:

    username=katharina_schäfer_846   persona: "Sabine Krüger …"
    username=felix_krause_452        persona: "Klaus Weber …"

Der Interview-Systemprompt setzt beides zusammen — „Du bist <label>“ und
direkt darunter ein Profil, in dem jemand anders beschrieben wird. Die Persona
bekommt zwei Identitäten in derselben Nachricht. Das ist die plausibelste
Erklärung für die beobachtete Rollenübernahme (eine Technikerin antwortet „Als
Betriebsrat hätte ich…").

**P2 — Organisationen werden Einzelpersonen.** Aus `Nordharz Bildungswerk gGmbH`
(`source_entity_type: Organization`) wurde `juergen_hartmann_nhb_832` mit
`profession: "Dozent für IT-Umschulungen und Betriebsratsmitglied"`. Weder
„Dozent“ noch „Betriebsratsmitglied“ ist aus einem Bildungsträger ableitbar.
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
        """RED ohne den urspruenglichen Fix (#1246): `_save_reddit_json` schrieb
        age=30, gender=other, mbti=ISTJ.

        Die Realtime-Datei war korrekt, der finale Save überschrieb sie — und
        genau diese Datei lesen Persona-Galerie und Simulation.

        Die Schluessel selbst bleiben trotzdem immer vorhanden (Leerstring
        statt fehlendem Feld) — sonst reisst OASIS beim ungeschuetzten
        `agent_info[i]["mbti"]`-Zugriff mit KeyError ab. Nur der erfundene
        Wert bleibt aus.
        """
        entity = _entity("Nordharz Bildungswerk gGmbH", "Organization")
        profile = generator.generate_profile_from_entity(entity, user_id=1, use_llm=False)

        target = tmp_path / "reddit_profiles.json"
        generator._save_reddit_json([profile], str(target))
        written = json.loads(target.read_text(encoding="utf-8"))[0]

        assert written["age"] == ""
        assert written["gender"] == ""
        assert written["mbti"] == ""

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


# ---------------------------------------------------------------- #1759 (A1)


class TestNamensidentitaetImVertrag:
    """Der Anzeigename muss im Freitext wiedererkennbar sein (#1759 A1)."""

    def test_name_der_im_freitext_fehlt_liefert_einen_grund(self):
        from app.contracts.persona_contract import persona_name_identity_reason

        grund = persona_name_identity_reason(
            "Mia Weber",
            "Monika Hartmann, 52, ist Hebammenleiterin und mag klare Worte.",
        )

        assert grund is not None
        assert "Mia Weber" in grund

    def test_name_im_freitext_liefert_keinen_grund(self):
        from app.contracts.persona_contract import persona_name_identity_reason

        assert (
            persona_name_identity_reason(
                "Mia Weber", "Mia Weber, 52, ist Hebammenleiterin."
            )
            is None
        )

    def test_gross_kleinschreibung_ist_kein_grund(self):
        from app.contracts.persona_contract import persona_name_identity_reason

        assert (
            persona_name_identity_reason(
                "Mia Weber", "Am Steuer sitzt mia weber aus Hollerau."
            )
            is None
        )

    def test_namensbestandteil_im_freitext_liefert_keinen_grund(self):
        """Nur der Vorname im Text reicht — die Identität ist erkennbar."""
        from app.contracts.persona_contract import persona_name_identity_reason

        assert (
            persona_name_identity_reason("Mia Weber", "Mia hält den Verband zusammen.")
            is None
        )

    def test_leerer_anzeigename_liefert_keinen_grund(self):
        from app.contracts.persona_contract import persona_name_identity_reason

        assert persona_name_identity_reason("", "Ein Text ohne Namen.") is None


class TestUmbenennungZiehtDenFreitextNach:
    """Die Dedup-Umbenennung darf den Freitext nicht alt aussehen lassen."""

    def test_sync_stelle_ersetzt_alten_namen_in_freitext_und_bio(self):
        from app.services.oasis_profile_batch import _apply_identity_rename
        from app.services.oasis_profile_models import OasisAgentProfile

        profile = OasisAgentProfile(
            user_id=1,
            user_name="mia_weber_302",
            name="Mia Weber",
            bio="Hebammenleiterin Mia Weber aus Hollerau",
            persona=(
                "Monika Hartmann, 52, leitet die Hebammenschule. "
                "Monika schätzt klare Absprachen. Frau Hartmann meldet sich gern."
            ),
        )

        _apply_identity_rename(profile, "Monika Hartmann", "Mia Weber")

        assert profile.name == "Mia Weber"
        assert "Monika" not in profile.persona
        assert "Hartmann" not in profile.persona
        assert profile.persona.startswith("Mia Weber, 52,")
        assert "Mia schätzt klare Absprachen" in profile.persona
        assert "Frau Weber meldet sich gern" in profile.persona
        assert "Monika" not in profile.bio
        assert "Mia Weber" in profile.bio

    def test_umbenennung_bei_kollision_zieht_freitext_mit(self, generator, monkeypatch):
        """Zwei Profile mit demselben Namen: das zweite wird umgenannt und
        sein Freitext muss den neuen Namen tragen (Exaktbefund aus dem Lauf:
        Profil `valentina_ferrari_302`, Text `Maren Hoffmann`)."""
        from app.services.oasis_profile_models import OasisAgentProfile

        vorbereitet = [
            OasisAgentProfile(
                user_id=0,
                user_name="mia_weber_1",
                name="Mia Weber",
                bio="Klinikleitung",
                persona="Mia Weber, 44, leitet die Klinik. Mia mag Struktur.",
            ),
            OasisAgentProfile(
                user_id=1,
                user_name="mia_weber_2",
                name="Mia Weber",
                bio="Klinikleitung",
                persona="Mia Weber, 52, leitet die Hebammenschule. Mia mag Worte.",
            ),
        ]
        reihenfolge = iter(vorbereitet)

        def fake(entity, user_id, use_llm=True, demographic_slot=None):
            return next(reihenfolge)

        monkeypatch.setattr(generator, "generate_profile_from_entity", fake)
        profiles = generator.generate_profiles_from_entities(
            entities=[_entity("A", "Person"), _entity("B", "Person")],
            use_llm=True,
            parallel_count=1,
        )

        assert len(profiles) == 2
        zweites = profiles[1]
        assert zweites.name != "Mia Weber"
        assert "Mia Weber" not in zweites.persona
        assert zweites.name.split()[0] in zweites.persona


class TestAblehnungBeiFehlendemNamen:
    """Ein Profil, dessen Anzeigename im Freitext fehlt, wird abgelehnt."""

    def test_profil_ohne_namen_im_freitext_wird_abgelehnt(
        self, generator, monkeypatch
    ):
        from app.contracts.pipeline_degradation_contract import DegradationKind
        from app.services.degradation_collector import DegradationCollector
        from app.services.oasis_profile_models import OasisAgentProfile

        vorbereitet = [
            OasisAgentProfile(
                user_id=0,
                user_name="mia_weber_1",
                name="Mia Weber",
                bio="Klinikleitung",
                persona=(
                    "Monika Hartmann, 52, leitet die Hebammenschule. "
                    "Monika schätzt klare Absprachen."
                ),
            ),
        ]
        reihenfolge = iter(vorbereitet)

        def fake(entity, user_id, use_llm=True, demographic_slot=None):
            return next(reihenfolge)

        monkeypatch.setattr(generator, "generate_profile_from_entity", fake)
        degradations = DegradationCollector()
        profiles = generator.generate_profiles_from_entities(
            entities=[_entity("A", "Person")],
            use_llm=True,
            parallel_count=1,
            degradations=degradations,
        )

        assert profiles == [], "Profil mit fremdem Namen darf nicht durchwinken"
        events = degradations.report().events
        passende = [
            event
            for event in events
            if event.kind == DegradationKind.PERSONA_NAME_IDENTITY_REJECTED
        ]
        assert passende, "Die Ablehnung muss als sichtbare Degradation erscheinen"
        assert "Mia Weber" in passende[0].detail


class TestVergebeneNamenImPrompt:
    """Der Generierungs-Prompt kennt die bereits vergebenen Namen."""

    def test_prompt_benannt_bereits_vergebene_namen(self, generator):
        prompt = generator._build_individual_persona_prompt(
            "Dozent",
            "Person",
            "Dozent im Kontext der Umschulung.",
            {},
            "Kein zusätzlicher Kontext",
            taken_names=["Mia Weber", "Monika Hartmann"],
        )

        assert "Mia Weber" in prompt
        assert "Monika Hartmann" in prompt

    def test_ohne_vergebene_namen_bleibt_block_weg(self, generator):
        prompt = generator._build_individual_persona_prompt(
            "Dozent",
            "Person",
            "Dozent im Kontext der Umschulung.",
            {},
            "Kein zusätzlicher Kontext",
        )

        assert "bereits vergebene" not in prompt.lower()


# ------------------------------------------------- Issue #1759 · A2 / A3 / A1-Rest


def _entity_with(name: str, entity_type: str, attributes: dict | None = None) -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=[entity_type, "Entity"],
        summary=f"{name} im Kontext der Klinikschliessung.",
        attributes=attributes or {},
    )


def _stub_llm(generator, display_name: str, profession: str, calls: list | None = None):
    """Ersetzt den LLM-Aufruf: liefert ein festes Profil, protokolliert die Aufrufe."""

    def fake(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return {
            "display_name": display_name,
            "handle": display_name.lower().replace(" ", "_"),
            "persona": (
                f"{display_name} arbeitet als {profession} und äußert sich "
                "regelmäßig zur Klinikschließung."
            ),
            "bio": f"{profession}, Hollerau",
            "profession": profession,
            "interested_topics": [],
        }

    generator._generate_profile_with_llm = fake  # type: ignore[method-assign]


class TestRollenPlausibilitaet:
    """A2: Alter und Gender passen zur Rolle; Dokument-Belege haben Vorrang."""

    @pytest.mark.parametrize(
        ("age", "profession"),
        [
            (28, "Chefärztin der Geburtshilfe"),
            (25, "Chefarzt der Gynäkologie"),
            (65, "Betriebsratsvorsitzender"),
            (25, "Geschäftsführer der Klinikgesellschaft"),
        ],
    )
    def test_unplausibles_alter_hat_einen_ablehnungsgrund(self, age, profession):
        from app.contracts.persona_contract import persona_role_plausibility_reason

        reason = persona_role_plausibility_reason(age, profession, None)

        assert reason is not None
        assert str(age) in reason
        assert "#1759 A2" in reason

    @pytest.mark.parametrize(
        ("age", "profession"),
        [
            (45, "Chefärztin der Geburtshilfe"),
            (35, "Geschäftsführer der Klinikgesellschaft"),
            (58, "Betriebsratsvorsitzender"),
            (68, "Pensionierte Hebamme"),
            (70, "Betriebsratsvorsitzender im Ruhestand"),
            (22, "Pflegekraft"),
        ],
    )
    def test_plausibles_alter_wird_nicht_abgelehnt(self, age, profession):
        from app.contracts.persona_contract import persona_role_plausibility_reason

        assert persona_role_plausibility_reason(age, profession, None) is None

    def test_ohne_alter_oder_rolle_gibt_es_nichts_zu_pruefen(self):
        from app.contracts.persona_contract import persona_role_plausibility_reason

        assert persona_role_plausibility_reason(None, "Chefarzt", None) is None
        assert persona_role_plausibility_reason(20, None, None) is None

    @pytest.mark.parametrize(
        ("profession", "expected"),
        [
            ("Chefärztin der Geburtshilfe", "female"),
            ("Chefarzt der Gynäkologie", "male"),
            ("Freiberuflicher Hebamme", "female"),
            ("Betriebsratsvorsitzender", "male"),
            ("Hebamme und Verbandssprecher", None),  # beide Formen: nicht eindeutig
            ("Dozent", None),
            (None, None),
        ],
    )
    def test_gender_aus_der_berufsbezeichnung_nur_wenn_eindeutig(self, profession, expected):
        from app.contracts.persona_contract import gender_from_role_title

        assert gender_from_role_title(profession) == expected

    def test_falsches_gender_wird_auf_die_berufsbezeichnung_korrigiert(self):
        from app.contracts.persona_contract import role_corrected_gender

        assert role_corrected_gender("other", "Chefarzt", None) == "male"
        assert role_corrected_gender("male", "Freiberuflicher Hebamme", None) == "female"
        assert role_corrected_gender("female", "Chefärztin", None) == "female"
        assert role_corrected_gender("male", "Hebamme und Verbandssprecher", None) == "male"
        assert role_corrected_gender(None, "Chefarzt", None) is None

    def test_profil_bekommt_korrigiertes_gender_aus_der_berufsbezeichnung(self, generator):
        _stub_llm(generator, "Birgit Sander", "Chefärztin der Geburtshilfe")
        slot = PersonaDemographicSlot(age=45, gender="male", mbti="INTJ")

        profile = generator.generate_profile_from_entity(
            _entity_with("Chefärztin Geburtshilfe", "Person"),
            user_id=1,
            use_llm=True,
            demographic_slot=slot,
        )

        assert profile.gender == "female"
        assert profile.age == 45

    def test_dokumentierte_werte_schlagen_den_gewuerfelten_slot(self, generator):
        _stub_llm(generator, "Birgit Sander", "Chefärztin der Geburtshilfe")
        slot = PersonaDemographicSlot(age=28, gender="male", mbti="INTJ")
        entity = _entity_with(
            "Chefärztin Geburtshilfe", "Person", {"age": 52, "gender": "weiblich"}
        )

        profile = generator.generate_profile_from_entity(
            entity, user_id=1, use_llm=True, demographic_slot=slot
        )

        assert profile.age == 52
        assert profile.gender == "female"

    def test_unplausibles_alter_wird_im_batch_sichtbar_abgelehnt(self, generator):
        from app.contracts.pipeline_degradation_contract import DegradationKind
        from app.services.degradation_collector import DegradationCollector

        _stub_llm(generator, "Birgit Sander", "Chefärztin der Geburtshilfe")
        slot = PersonaDemographicSlot(age=28, gender="female", mbti="INTJ")
        degradations = DegradationCollector()

        profiles = generator.generate_profiles_from_entities(
            entities=[_entity_with("Chefärztin Geburtshilfe", "Person")],
            use_llm=True,
            parallel_count=1,
            degradations=degradations,
            demographic_slots=[slot],
        )

        assert profiles == []
        passende = [
            e for e in degradations.report().events
            if e.kind == DegradationKind.PERSONA_ROLE_IMPLAUSIBLE
        ]
        assert passende, "Die Ablehnung muss als sichtbare Degradation erscheinen"
        assert "28" in passende[0].detail

    def test_dokumentiertes_unplausibles_alter_wird_nicht_abgelehnt(self, generator):
        """Dokument-Beleg schlägt die Rollenregel (Vorrang vor generierten Werten)."""
        _stub_llm(generator, "Birgit Sander", "Chefärztin der Geburtshilfe")
        slot = PersonaDemographicSlot(age=50, gender="female", mbti="INTJ")

        profiles = generator.generate_profiles_from_entities(
            entities=[_entity_with("Chefärztin Geburtshilfe", "Person", {"age": 31})],
            use_llm=True,
            parallel_count=1,
            demographic_slots=[slot],
        )

        assert [p.age for p in profiles] == [31]


class TestKollektivKonsistenz:
    """A3: Fraktionen, Gremien, Behörden, Kassen bleiben Kollektive."""

    @pytest.mark.parametrize(
        "entity_type",
        [
            "PoliticalFaction",
            "LocalGovernment",
            "GovernmentAgency",
            "HealthInsurer",
            "Krankenkasse",
            "Hospital",
            "PoliticalParty",
            "NGO",
        ],
    )
    def test_typ_ist_kollektiv_und_in_beiden_pruefungen_gleich(self, generator, entity_type):
        from app.services.persona_domain_coherence import is_collective_entity_type

        assert is_collective_entity_type(entity_type) is True
        assert generator._is_group_entity(entity_type) is True

    @pytest.mark.parametrize("entity_type", ["PoliticalFaction", "LocalGovernment", "HealthInsurer"])
    def test_organisation_wird_kollektiv_ohne_erfundene_einzelperson(self, generator, entity_type):
        entity = _entity_with("Nordkasse", entity_type)
        slot = PersonaDemographicSlot(age=34, gender="female", mbti="INFJ")

        profile = generator.generate_profile_from_entity(
            entity, user_id=1, use_llm=False, demographic_slot=slot
        )

        assert profile.persona_kind == "collective"
        assert profile.name == "Nordkasse"
        assert profile.age is None
        assert profile.gender is None

    def test_derselbe_typ_wird_im_lauf_immer_gleich_behandelt(self, generator):
        kinds = {
            generator.generate_profile_from_entity(
                _entity_with(name, "LocalGovernment"), user_id=i, use_llm=False
            ).persona_kind
            for i, name in enumerate(["Kreistag Hollerau", "Stadtrat Nord", "Gemeinderat Süd"])
        }

        assert kinds == {"collective"}

    def test_dokumentierte_position_wird_verbindlich_in_den_kontext_gehoben(self, generator):
        calls: list = []
        _stub_llm(generator, "Anna Kohl", "Pflegekraft", calls)
        entity = _entity_with("Fraktion X", "Person", {"stance": "opposing", "position_on_closure": "Schließung ablehnen"})

        generator.generate_profile_from_entity(entity, user_id=1, use_llm=True)

        context = calls[0]["context"]
        assert "Dokumentierte Position (verbindlich)" in context
        assert "stance: opposing" in context
        assert "position_on_closure: Schließung ablehnen" in context

    def test_ohne_dokumentierte_position_bleibt_der_block_weg(self, generator):
        calls: list = []
        _stub_llm(generator, "Anna Kohl", "Pflegekraft", calls)

        generator.generate_profile_from_entity(_entity_with("Anna", "Person"), user_id=1, use_llm=True)

        assert "Dokumentierte Position" not in calls[0]["context"]


class TestVergebeneNamenWerdenDurchgereicht:
    """A1-Rest: ``taken_names`` wird aus dem laufenden Batch befüllt."""

    def test_spaetere_generierung_kennt_die_namen_vorheriger_profile(self, generator):
        calls: list = []
        names = iter(["Mia Weber", "Jonas Albers"])

        def fake(**kwargs):
            calls.append(kwargs)
            name = next(names)
            return {
                "display_name": name,
                "handle": name.lower().replace(" ", "_"),
                "persona": f"{name} lebt in Hollerau und engagiert sich vor Ort.",
                "bio": "Hollerau",
                "profession": "Pflegekraft",
                "interested_topics": [],
            }

        generator._generate_profile_with_llm = fake  # type: ignore[method-assign]

        generator.generate_profiles_from_entities(
            entities=[_entity_with("A", "Person"), _entity_with("B", "Person")],
            use_llm=True,
            parallel_count=1,
        )

        assert calls[0]["taken_names"] is None
        assert calls[1]["taken_names"] == ["Mia Weber"]

    def test_namensliste_wird_pro_batch_zurueckgesetzt(self, generator):
        generator._taken_display_names = ["Alter Name"]
        _stub_llm(generator, "Mia Weber", "Pflegekraft")

        generator.generate_profiles_from_entities(
            entities=[_entity_with("A", "Person")], use_llm=True, parallel_count=1
        )

        assert "Alter Name" not in generator._taken_display_names
        assert generator._taken_display_names == ["Mia Weber"]
