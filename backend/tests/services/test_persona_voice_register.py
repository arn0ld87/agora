"""Issue #1759, Befund A7 — „Alle Personas klingen gleich“.

Fünf Bausteine, ein Ziel: Betroffene klingen nicht wie Gutachter.

* Vertrag: drei neue Register (``betroffen-de``, ``emotional-de``,
  ``umgangssprachlich-de``) neben den vier sachlichen.
* Rollenbindung: das Register folgt der Rolle, ein widersprechendes
  Modell-Register wird überschrieben (LLM- und regelbasierter Pfad).
* Prompt: jedes Register wird mit Satzlänge, Perspektive und Ausrufen beschrieben.
* Länge: Beiträge sind je Plattform und Register begrenzt, als Vorgabe im
  Agenten-Prompt.
* Floskeln: Wörter, die der Batch schon in mehreren Bios verbraucht hat, gehen
  als „vermeiden“ in den nächsten Prompt.
"""

from __future__ import annotations

import csv
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.persona_contract import VOICE_REGISTER_VALUES, PersonaModel
from app.contracts.post_event_contract import VoiceRegister as PostEventVoiceRegister
from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.persona_bio_phrases import (
    BIO_WORD_MIN_BIOS,
    avoid_words_prompt_block,
    bio_words,
    overused_bio_words,
    register_bio_words,
)
from app.services.persona_post_length import (
    MAX_POST_CHARS,
    PLATFORM_REDDIT,
    PLATFORM_TWITTER,
    build_length_section,
    max_post_chars,
)
from app.services.persona_voice_register import (
    AFFECTED_REGISTERS,
    VoiceRole,
    classify_voice_role,
    resolve_voice_register,
    rule_based_voice_register,
)

NEW_REGISTERS = ("betroffen-de", "emotional-de", "umgangssprachlich-de")
FORMAL_OR_NEUTRAL = {"formal-de", "neutral-de"}


# ---------------------------------------------------------------- Vertrag


class TestVertrag:
    @pytest.mark.parametrize("value", NEW_REGISTERS)
    def test_neue_register_sind_im_personenvertrag_gueltig(self, value: str) -> None:
        persona = PersonaModel(
            user_id=1,
            user_name="test_user",
            name="Test",
            bio="Eine Testpersona für das Register.",
            persona="x" * 300,
            voice_register=value,  # type: ignore[arg-type]
        )
        assert persona.voice_register == value

    def test_default_bleibt_neutral_de(self) -> None:
        persona = PersonaModel(
            user_id=1,
            user_name="test_user",
            name="Test",
            bio="Eine Testpersona für das Register.",
            persona="x" * 300,
        )
        assert persona.voice_register == "neutral-de"

    def test_unbekanntes_register_bleibt_ungueltig(self) -> None:
        with pytest.raises(ValidationError):
            PersonaModel(
                user_id=1,
                user_name="test_user",
                name="Test",
                bio="Eine Testpersona für das Register.",
                persona="x" * 300,
                voice_register="casual-de",  # type: ignore[arg-type]
            )

    def test_laufzeitliste_und_ereignisvertrag_fuehren_dieselben_sieben_werte(self) -> None:
        assert set(VOICE_REGISTER_VALUES) == {
            "formal-de",
            "neutral-de",
            "technical-de",
            "skeptisch-de",
            *NEW_REGISTERS,
        }
        assert {member.value for member in PostEventVoiceRegister} == set(VOICE_REGISTER_VALUES)


# ---------------------------------------------------------------- Rollenbindung


class TestRollenZuordnung:
    @pytest.mark.parametrize(
        ("entity_type", "profession"),
        [
            ("Patient", None),
            ("Person", "Patientin"),
            ("Person", "Schwangere"),
            ("Person", "Anwohner"),
            ("Person", "Angehörige"),
            ("Person", "Beschäftigte der Geburtsstation"),
        ],
    )
    def test_direkt_betroffene_bekommen_ein_betroffenen_register(
        self, entity_type: str, profession: str | None
    ) -> None:
        assert classify_voice_role(entity_type, profession) is VoiceRole.AFFECTED
        register = rule_based_voice_register(entity_type, profession, seed="Mia Weber")
        assert register in AFFECTED_REGISTERS

    @pytest.mark.parametrize(
        "entity_type",
        ["Association", "GovernmentAgency", "Company", "HospitalNetwork", "PatientAdvisoryCouncil"],
    )
    def test_verbaende_behoerden_und_unternehmen_bleiben_formal_oder_neutral(
        self, entity_type: str
    ) -> None:
        assert classify_voice_role(entity_type, None) is VoiceRole.INSTITUTIONAL
        assert rule_based_voice_register(entity_type) in FORMAL_OR_NEUTRAL

    @pytest.mark.parametrize(
        "profession",
        [
            "Bürgermeisterin",
            "Bürgermeister der Gemeinde",
            "Landrat",
            "Landrätin",
            "Abgeordnete des Landtags",
            "Dezernent für Soziales",
            "Ministerin",
        ],
    )
    def test_amtstraeger_sind_institutionell_und_nicht_betroffen(self, profession: str) -> None:
        assert classify_voice_role("Person", profession) is VoiceRole.INSTITUTIONAL
        assert rule_based_voice_register("Person", profession, seed="Mia Weber") == "formal-de"

    @pytest.mark.parametrize(
        "profession", ["Bürgerin", "Mitglied einer Bürgerinitiative"]
    )
    def test_buerger_bleiben_betroffene(self, profession: str) -> None:
        assert classify_voice_role("Person", profession) is VoiceRole.AFFECTED
        assert rule_based_voice_register("Person", profession, seed="Mia Weber") in AFFECTED_REGISTERS

    def test_behoerde_ist_formal_unternehmen_neutral(self) -> None:
        assert rule_based_voice_register("GovernmentAgency") == "formal-de"
        assert rule_based_voice_register("Company") == "neutral-de"

    def test_fachrolle_ist_technical(self) -> None:
        assert rule_based_voice_register("Person", "Senior-Entwicklerin") == "technical-de"
        assert rule_based_voice_register("Developer", "DevOps") == "technical-de"

    def test_kritische_beobachter_bleiben_skeptisch(self) -> None:
        assert rule_based_voice_register("Journalist", "Redakteur") == "skeptisch-de"

    def test_unbekannter_einzelner_bleibt_neutral(self) -> None:
        assert classify_voice_role("Student", "Student") is VoiceRole.GENERAL
        assert rule_based_voice_register("Student", "Student") == "neutral-de"

    def test_kollektiv_entscheidung_des_aufrufers_gilt(self) -> None:
        assert classify_voice_role("Person", None, is_collective=True) is VoiceRole.INSTITUTIONAL
        assert classify_voice_role("Person", None, is_collective=False) is VoiceRole.GENERAL

    def test_betroffene_streuen_stabil_ueber_alle_drei_register(self) -> None:
        names = [f"Person Nummer {i}" for i in range(40)]
        first = [rule_based_voice_register("Patient", None, seed=n) for n in names]
        second = [rule_based_voice_register("Patient", None, seed=n) for n in names]

        assert first == second
        assert set(first) == set(AFFECTED_REGISTERS)


class TestWiderspruechlichesModellRegisterWirdUeberschrieben:
    def test_neutral_fuer_eine_patientin_wird_ersetzt(self) -> None:
        resolved = resolve_voice_register("neutral-de", "Patient", None, seed="Mia Weber")
        assert resolved in AFFECTED_REGISTERS

    def test_emotional_fuer_einen_verband_wird_ersetzt(self) -> None:
        resolved = resolve_voice_register("emotional-de", "Association", None)
        assert resolved in FORMAL_OR_NEUTRAL

    def test_formal_fuer_einen_entwickler_wird_technical(self) -> None:
        assert resolve_voice_register("formal-de", "Person", "Software-Entwickler") == "technical-de"

    def test_fehlendes_register_bekommt_das_der_rolle(self) -> None:
        assert resolve_voice_register(None, "GovernmentAgency", None) == "formal-de"

    def test_passendes_modell_register_bleibt(self) -> None:
        assert resolve_voice_register("emotional-de", "Patient", None, seed="x") == "emotional-de"
        assert resolve_voice_register("neutral-de", "Association", None) == "neutral-de"

    def test_unbekannte_rolle_laesst_jedes_gueltige_register_zu(self) -> None:
        for register in VOICE_REGISTER_VALUES:
            assert resolve_voice_register(register, "Person", "Dozentin") == register


@pytest.fixture()
def generator() -> OasisProfileGenerator:
    return OasisProfileGenerator(api_key="test", base_url="http://localhost", language="de")


def _entity(name: str, entity_type: str, summary: str = "Ein Beteiligter im Szenario.") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=[entity_type, "Entity"],
        summary=summary,
        attributes={},
    )


def _llm_payload(register: str | None, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "display_name": "Mia Weber",
        "handle": "mia_weber",
        "bio": "Mutter von zwei Kindern aus Hollerau.",
        "persona": "Mia Weber lebt in Hollerau.",
        "age": 38,
        "gender": "female",
        "mbti": "ISFJ",
        "country": "DE",
        "profession": "Patientin",
        "interested_topics": ["Gesundheit"],
        "voice_register": register,
    }
    payload.update(overrides)
    return payload


class TestRegisterImErzeugtenProfil:
    def test_llm_neutral_fuer_betroffene_wird_im_profil_ueberschrieben(
        self, generator: OasisProfileGenerator
    ) -> None:
        generator._generate_profile_with_llm = lambda **kw: _llm_payload("neutral-de")  # type: ignore[method-assign]

        profile = generator.generate_profile_from_entity(
            _entity("Mia Weber", "Patient"), user_id=1, use_llm=True
        )

        assert profile.voice_register in AFFECTED_REGISTERS

    def test_llm_emotional_fuer_verband_wird_im_profil_ueberschrieben(
        self, generator: OasisProfileGenerator
    ) -> None:
        generator._generate_profile_with_llm = lambda **kw: {  # type: ignore[method-assign]
            "bio": "Der Verband vertritt die Kliniken.",
            "persona": "Der Verband vertritt die Kliniken der Region.",
            "country": "DE",
            "interested_topics": [],
            "voice_register": "emotional-de",
        }

        profile = generator.generate_profile_from_entity(
            _entity("Klinikverband Nord", "HospitalAssociation"), user_id=1, use_llm=True
        )

        assert profile.persona_kind == "collective"
        assert profile.voice_register in FORMAL_OR_NEUTRAL

    @pytest.mark.parametrize(
        ("entity_type", "expected"),
        [("Patient", set(AFFECTED_REGISTERS)), ("GovernmentAgency", {"formal-de"})],
    )
    def test_regelbasierter_pfad_folgt_derselben_zuordnung(
        self, generator: OasisProfileGenerator, entity_type: str, expected: set[str]
    ) -> None:
        profile = generator.generate_profile_from_entity(
            _entity("Beispiel Name", entity_type), user_id=1, use_llm=False
        )

        assert profile.voice_register in expected


class TestPrompt:
    def test_individuen_prompt_beschreibt_alle_sieben_register(
        self, generator: OasisProfileGenerator
    ) -> None:
        prompt = generator._build_individual_persona_prompt(
            "Mia Weber", "Person", "Zusammenfassung", {}, "Kontext"
        )

        for register in VOICE_REGISTER_VALUES:
            assert f'"{register}":' in prompt
        assert "Ausrufe" in prompt
        assert "Ich-Perspektive" in prompt
        assert "Alltagssprache" in prompt

    def test_individuen_prompt_nennt_den_rollenhinweis_nur_wo_der_typ_ihn_hergibt(
        self, generator: OasisProfileGenerator
    ) -> None:
        affected = generator._build_individual_persona_prompt("Mia", "Patient", "", {}, "")
        neutral = generator._build_individual_persona_prompt("Mia", "Student", "", {}, "")

        assert "Für diesen Entitätstyp passend" in affected
        assert "Für diesen Entitätstyp passend" not in neutral

    def test_kollektiv_prompt_bietet_nur_formal_und_neutral(
        self, generator: OasisProfileGenerator
    ) -> None:
        prompt = generator._build_group_persona_prompt(
            "Klinikverband Nord", "HospitalAssociation", "Zusammenfassung", {}, "Kontext"
        )

        assert '"formal-de":' in prompt
        assert '"neutral-de":' in prompt
        for register in ("emotional-de", "betroffen-de", "umgangssprachlich-de"):
            assert f'"{register}"' not in prompt

    def test_englischer_prompt_traegt_dieselben_register(self) -> None:
        generator = OasisProfileGenerator(api_key="test", base_url="http://localhost", language="en")

        prompt = generator._build_individual_persona_prompt("Mia", "Person", "", {}, "")

        for register in VOICE_REGISTER_VALUES:
            assert f'"{register}":' in prompt


# ---------------------------------------------------------------- Länge


class TestLaengengrenzen:
    def test_jedes_register_hat_eine_grenze_auf_jeder_plattform(self) -> None:
        for platform in (PLATFORM_TWITTER, PLATFORM_REDDIT):
            assert set(MAX_POST_CHARS[platform]) == set(VOICE_REGISTER_VALUES)

    @pytest.mark.parametrize("register", VOICE_REGISTER_VALUES)
    def test_twitter_ist_deutlich_kuerzer_als_reddit(self, register: str) -> None:
        twitter = max_post_chars(PLATFORM_TWITTER, register)
        reddit = max_post_chars(PLATFORM_REDDIT, register)

        assert twitter <= 280
        assert twitter * 2 <= reddit

    @pytest.mark.parametrize("platform", [PLATFORM_TWITTER, PLATFORM_REDDIT])
    @pytest.mark.parametrize("register", NEW_REGISTERS)
    def test_neue_register_sind_kuerzer_als_formal(self, platform: str, register: str) -> None:
        assert max_post_chars(platform, register) < max_post_chars(platform, "formal-de")

    def test_unbekanntes_register_und_unbekannte_plattform_haben_einen_default(self) -> None:
        assert max_post_chars(PLATFORM_TWITTER, None) == 240
        assert max_post_chars(PLATFORM_REDDIT, "gibt-es-nicht") == 700
        assert max_post_chars("mastodon", None) == 700

    def test_abschnitt_nennt_die_grenze_im_klartext(self) -> None:
        section = build_length_section(PLATFORM_TWITTER, "umgangssprachlich-de")

        assert "höchstens 140 Zeichen" in section
        assert section.startswith("## Beitragslänge")


_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
agent_tools = importlib.import_module("agent_tools")


class TestVorgabeImAgentenPrompt:
    def test_twitter_profil_bekommt_die_grenze_des_registers(self, tmp_path: Path) -> None:
        path = tmp_path / "twitter_profiles.csv"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["user_id", "name", "username", "user_char", "description", "voice_register"])
            writer.writerow([0, "Mia", "mia_1", "Persona Mia", "Bio", "umgangssprachlich-de"])
            writer.writerow([1, "Amt", "amt_1", "Persona Amt", "Bio", "formal-de"])

        out = agent_tools.augment_profile_with_stance(
            str(path), [{"agent_id": 0}, {"agent_id": 1}], platform="twitter"
        )

        with open(out, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert "höchstens 140 Zeichen" in rows[0]["user_char"]
        assert "höchstens 280 Zeichen" in rows[1]["user_char"]
        assert rows[0]["user_char"].startswith("Persona Mia")

    def test_reddit_profil_bekommt_die_grenze_des_registers(self, tmp_path: Path) -> None:
        path = tmp_path / "reddit_profiles.json"
        path.write_text(
            json.dumps(
                [
                    {"user_id": 0, "persona": "Persona Mia", "voice_register": "emotional-de"},
                    {"user_id": 1, "persona": "Persona Amt", "voice_register": "formal-de"},
                ]
            ),
            encoding="utf-8",
        )

        out = agent_tools.augment_profile_with_stance(
            str(path), [{"agent_id": 0}, {"agent_id": 1}], platform="reddit"
        )

        data = json.loads(Path(out).read_text(encoding="utf-8"))
        assert "höchstens 450 Zeichen" in data[0]["persona"]
        assert "höchstens 900 Zeichen" in data[1]["persona"]

    def test_ohne_register_im_profil_entscheidet_die_rolle_des_entitaetstyps(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "twitter_profiles.csv"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["user_id", "name", "username", "user_char", "description"])
            writer.writerow([0, "Amt", "amt_1", "Persona Amt", "Bio"])

        out = agent_tools.augment_profile_with_stance(
            str(path), [{"agent_id": 0, "entity_type": "GovernmentAgency"}], platform="twitter"
        )

        with open(out, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert "höchstens 280 Zeichen" in rows[0]["user_char"]

    def test_twitter_csv_schreibt_das_register_mit(
        self, generator: OasisProfileGenerator, tmp_path: Path
    ) -> None:
        profile = generator.generate_profile_from_entity(
            _entity("Beispiel Name", "Patient"), user_id=1, use_llm=False
        )
        path = tmp_path / "twitter_profiles.csv"

        generator._save_twitter_csv([profile], str(path))

        with open(path, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[0]["voice_register"] == profile.voice_register
        assert rows[0]["voice_register"] in AFFECTED_REGISTERS


# ---------------------------------------------------------------- Floskeln


class _Profile:
    def __init__(self, bio: str, kind: str = "individual") -> None:
        self.bio = bio
        self.name = bio
        self.persona_kind = kind


class _Holder:
    pass


class TestBioFloskeln:
    def test_zaehlbare_woerter_sind_lang_genug_und_keine_funktionswoerter(self) -> None:
        words = bio_words("Verlässlich, dagegen kurz: Pflege und Hebamme.")

        assert "verlässlich" in words
        assert "hebamme" in words
        assert "dagegen" not in words
        assert "kurz" not in words

    def test_ein_wort_zaehlt_je_bio_nur_einmal(self) -> None:
        holder = _Holder()
        holder._bio_word_counts = {}  # type: ignore[attr-defined]

        register_bio_words(holder, _Profile("verlässlich verlässlich verlässlich"))

        assert holder._bio_word_counts == {"verlässlich": 1}  # type: ignore[attr-defined]

    def test_ohne_batchzaehlung_passiert_nichts(self) -> None:
        holder = _Holder()

        register_bio_words(holder, _Profile("verlässlich"))

        assert overused_bio_words(holder) is None
        assert not hasattr(holder, "_bio_word_counts")

    def test_wort_wird_erst_ab_der_schwelle_zur_floskel(self) -> None:
        holder = _Holder()
        holder._bio_word_counts = {}  # type: ignore[attr-defined]
        for _ in range(BIO_WORD_MIN_BIOS - 1):
            register_bio_words(holder, _Profile("verlässlich und engagiert"))
        assert overused_bio_words(holder) is None

        register_bio_words(holder, _Profile("verlässlich"))

        assert overused_bio_words(holder) == ["verlässlich"]

    def test_quellengebundene_woerter_der_entitaet_sind_keine_floskel(self) -> None:
        holder = _Holder()
        holder._bio_word_counts = {"verlässlich": 5, "hebamme": 4}  # type: ignore[attr-defined]

        assert overused_bio_words(holder, context="Die Hebamme Anna Kohl arbeitet dort.") == [
            "verlässlich"
        ]

    def test_promptabsatz_ist_leer_ohne_woerter_und_nennt_sie_sonst(self) -> None:
        assert avoid_words_prompt_block(None, "de") == ""
        assert "verlässlich" in avoid_words_prompt_block(["verlässlich"], "de")
        assert "vermeiden" in avoid_words_prompt_block(["verlässlich"], "de")
        assert "avoid" in avoid_words_prompt_block(["verlässlich"], "en")


class _RecordingClient:
    prompts: list[str] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def chat_json(self, messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
        _RecordingClient.prompts.append(messages[-1]["content"])
        index = len(_RecordingClient.prompts)
        return _llm_payload(
            "neutral-de",
            display_name=f"Person Nummer{'x' * index}",
            handle=f"person_{index}",
            bio="Verlässlich und engagiert in der Nachbarschaft.",
            profession="Dozentin",
        )


class TestFloskelnWerdenDurchDenBatchGereicht:
    def test_spaetere_prompts_nennen_die_verbrauchten_woerter(
        self, generator: OasisProfileGenerator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.llm.client as client_module

        _RecordingClient.prompts = []
        monkeypatch.setattr(client_module, "LLMClient", _RecordingClient)

        generator.generate_profiles_from_entities(
            entities=[_entity(f"Person {i}", "Person") for i in range(BIO_WORD_MIN_BIOS + 2)],
            use_llm=True,
            parallel_count=1,
        )

        prompts = _RecordingClient.prompts
        assert len(prompts) >= BIO_WORD_MIN_BIOS + 1
        # Die ersten Bios sind noch unauffaellig, ab der Schwelle steht das Wort im Prompt.
        assert "bereits verwendete Wörter" not in prompts[0]
        assert "bereits verwendete Wörter" in prompts[BIO_WORD_MIN_BIOS]
        assert "verlässlich" in prompts[BIO_WORD_MIN_BIOS].split("bereits verwendete Wörter")[-1]

    def test_zaehlung_wird_pro_batch_zurueckgesetzt(
        self, generator: OasisProfileGenerator, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.llm.client as client_module

        _RecordingClient.prompts = []
        monkeypatch.setattr(client_module, "LLMClient", _RecordingClient)
        generator._bio_word_counts = {"altlast": 9}

        generator.generate_profiles_from_entities(
            entities=[_entity("Person A", "Person")], use_llm=True, parallel_count=1
        )

        assert "altlast" not in generator._bio_word_counts
        assert "altlast" not in _RecordingClient.prompts[0]
