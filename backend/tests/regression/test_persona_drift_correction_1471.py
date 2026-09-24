"""Persona-Domänendrift, Nachtrag #1471: Branchenquote und Bio-Korrektur.

Der Hauptfix von #1471 (Hauptdomänen-Vergleich statt Any-Overlap) ist mit
#1540 gemergt. Offen blieben zwei Punkte aus der ursprünglichen
Spezifikation:

1. Die Branchenquote (``build_industry_quota_prompt_block``) durfte eine
   quellengebundene Entität — deren Fach die Quelle bereits festlegt — in
   eine fremde Branche umdeuten. Abnahme: eine BFW-Sicherheitsverantwortliche
   behält ihren BFW-Kontext.
2. Erkannte Drift leerte bisher nur ``profession`` und liess Bio und
   Freitext mit ihrem fachfremden Vokabular stehen. Jetzt lässt der
   bestehende Persona-Generierungspfad (``LLMClient.chat_json`` mit
   Pydantic-Schema) sie korrigieren; scheitert die Korrektur, bleibt die
   Degradation sichtbar (``generation_error``), und ein
   ``BudgetExceededError`` wird nie abgefangen.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.services.oasis_profile_generator import (
    PERSONA_DETAIL_LEVELS,
    OasisProfileGenerator,
)
from app.services.oasis_profile_models import (
    PersonaCoherenceResolution,
    PersonaDriftCorrectionSchema,
)
from app.services.run_budget import BudgetExceededError


def _make_generator() -> OasisProfileGenerator:
    return OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")


# --- 1. Branchenquote nur für bewusst synthetische Vertreter ---------------

BFW_SOURCE_SUMMARY = (
    "Berufsförderungswerk (BFW): Träger der beruflichen Rehabilitation. Der "
    "Unterricht findet in mehreren Seminaren für Umschüler statt."
)


def test_a_source_bound_entity_does_not_get_the_industry_quota_block():
    """BFW-Sicherheitsverantwortliche behalten ihren BFW-Kontext (Abnahme #1471).

    Die Zusammenfassung trägt erkennbares Fachvokabular (Unterricht, Seminar)
    — die Entität ist quellengebunden. Die Branchenquote darf sie nicht in
    eine der Destatis-Branchen aus ``default_dach_industry_quota`` umdeuten.
    """
    gen = _make_generator()
    prompt = gen._build_individual_persona_prompt(
        entity_name="BFW-Sicherheitsverantwortliche",
        entity_type="Person",
        entity_summary=BFW_SOURCE_SUMMARY,
        entity_attributes={},
        context="",
        detail_level=PERSONA_DETAIL_LEVELS["standard"],
    )
    assert "Branchenverteilung" not in prompt
    assert "Destatis" not in prompt


def test_a_synthetic_entity_without_source_domain_still_gets_the_quota_block():
    """Ohne erkennbares Quellfach bleibt die Quote aktiv — sie verhindert den IT-Bias (#215)."""
    gen = _make_generator()
    prompt = gen._build_individual_persona_prompt(
        entity_name="Teilnehmerin",
        entity_type="Person",
        entity_summary="",
        entity_attributes={},
        context="Ein Projekt startet.",
        detail_level=PERSONA_DETAIL_LEVELS["standard"],
    )
    assert "Branchenverteilung" in prompt
    assert "Destatis" in prompt


# --- 2. Erkannte Drift korrigiert die Biografie statt nur profession zu leeren --

DRIFT_SOURCE_TEXT = (
    "Städtischer Klinikverbund Falkenbrück: Rollout von Nexora Triage Assist "
    "in Notaufnahme und Pflege."
)


def test_a_successful_correction_replaces_profession_bio_and_persona_text():
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(return_value={
        "bio": "Pflegedienstleitung im Klinikverbund.",
        "persona": "Leitet die Pflege in der Notaufnahme.",
        "profession": "Pflegedienstleitung",
        "voice_register": "neutral-de",
    })

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Schichtleiter Maschinenbau",
        persona_kind="individual",
        profession="Schichtleiter Maschinenbau",
        bio="Leitet die Produktionsplanung.",
        persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    assert resolution == PersonaCoherenceResolution(
        "Pflegedienstleitung",
        "Leitet die Pflege in der Notaufnahme.",
        "Pflegedienstleitung im Klinikverbund.",
        None,
    )
    gen._regenerate_persona_after_drift.assert_called_once()
    assert gen._regenerate_persona_after_drift.call_args.kwargs["drifted_domains"] == ["manufacturing"]


def test_a_failed_correction_clears_profession_and_sets_generation_error_visibly():
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(
        side_effect=RuntimeError("Drift-Korrektur nach 3 Versuchen fehlgeschlagen: boom")
    )

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Schichtleiter Maschinenbau",
        persona_kind="individual",
        profession="Schichtleiter Maschinenbau",
        bio="Leitet die Produktionsplanung.",
        persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    assert resolution.profession is None
    assert resolution.persona_text == "Verantwortet die Produktionsleitung in der Werkhalle."
    assert resolution.bio == "Leitet die Produktionsplanung."
    assert resolution.generation_error is not None
    assert "Korrektur fehlgeschlagen" in resolution.generation_error


def test_a_budget_exceeded_error_during_correction_is_never_swallowed():
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(
        side_effect=BudgetExceededError("calls", 10, 10)
    )

    with pytest.raises(BudgetExceededError):
        gen._persona_after_coherence_check(
            entity_type="Person",
            entity_name="Schichtleiter Maschinenbau",
            persona_kind="individual",
            profession="Schichtleiter Maschinenbau",
            bio="Leitet die Produktionsplanung.",
            persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
            entity_summary=DRIFT_SOURCE_TEXT,
            entity_context="",
            use_llm=True,
        )


def test_without_llm_the_conservative_line_applies_no_regeneration_attempted():
    """``use_llm=False``: kein LLM-Roundtrip, alte Linie — nur profession wird geleert."""
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock()

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Schichtleiter Maschinenbau",
        persona_kind="individual",
        profession="Schichtleiter Maschinenbau",
        bio="Leitet die Produktionsplanung.",
        persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=False,
    )

    assert resolution.profession is None
    assert resolution.persona_text == "Verantwortet die Produktionsleitung in der Werkhalle."
    assert resolution.generation_error is None
    gen._regenerate_persona_after_drift.assert_not_called()


def test_a_coherent_persona_is_untouched_no_regeneration_attempted():
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock()

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Dr. Marlene Krug",
        persona_kind="individual",
        profession="Oberärztin der Notaufnahme",
        bio="Arbeitet in der Notaufnahme.",
        persona_text="Arbeitet seit acht Jahren in der Notaufnahme.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    assert resolution == PersonaCoherenceResolution(
        "Oberärztin der Notaufnahme",
        "Arbeitet seit acht Jahren in der Notaufnahme.",
        "Arbeitet in der Notaufnahme.",
        None,
    )
    gen._regenerate_persona_after_drift.assert_not_called()


def test_a_collective_correction_never_keeps_a_profession():
    """Eine Kollektiv-Persona hat keinen Beruf (#1246) — auch nicht nach einer Korrektur."""
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(return_value={
        "bio": "Der Klinikverbund koordiniert die Pflege.",
        "persona": "Spricht als Träger für die Pflegekräfte.",
        "profession": "Pflegedienstleitung",
        "voice_register": "formal-de",
    })

    resolution = gen._persona_after_coherence_check(
        entity_type="EmployeeGroup",
        entity_name="Belegschaftsrat Fertigung",
        persona_kind="collective",
        profession=None,
        bio="Vertritt die Fertigungsplanung.",
        persona_text="Spricht für die Sachbearbeiterinnen der Fertigungsplanung.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    assert resolution.profession is None


# --- Regenerierung selbst: LLMClient.chat_json mit dediziertem Schema ------


class _CapturingDriftCorrectionClient:
    """Stub im Stil von test_oasis_profile_generator.py::_CapturingLLMClient."""

    last_instance = None

    def __init__(self, *args, **kwargs):
        _CapturingDriftCorrectionClient.last_instance = self
        self.captured_kwargs = None

    def chat_json(self, messages, temperature=0.7, max_tokens=8192,
                  schema=None, schema_name="structured_response",
                  context="chat_json", force_no_thinking=False, **kwargs):
        self.captured_kwargs = {
            "schema": schema,
            "schema_name": schema_name,
            "context": context,
            "force_no_thinking": force_no_thinking,
        }
        return {
            "bio": "Pflegedienstleitung im Klinikverbund.",
            "persona": "Leitet die Pflege in der Notaufnahme.",
            "profession": "Pflegedienstleitung",
            "voice_register": "neutral-de",
        }


def test_regenerate_persona_after_drift_uses_the_dedicated_schema(monkeypatch):
    import app.llm.client as _client_mod

    monkeypatch.setattr(_client_mod, "LLMClient", _CapturingDriftCorrectionClient)

    gen = _make_generator()
    result = gen._regenerate_persona_after_drift(
        entity_name="Schichtleiter Maschinenbau",
        entity_type="Person",
        persona_kind="individual",
        profession="Schichtleiter Maschinenbau",
        bio="Leitet die Produktionsplanung.",
        persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
        drifted_domains=["manufacturing"],
        source_text=DRIFT_SOURCE_TEXT,
    )

    assert result["profession"] == "Pflegedienstleitung"
    captured = _CapturingDriftCorrectionClient.last_instance.captured_kwargs
    assert captured is not None, "chat_json was not called"
    assert captured["schema"] is PersonaDriftCorrectionSchema
    assert captured["schema_name"] == "persona_drift_correction"
    assert captured["force_no_thinking"] is True
    assert captured["context"] == "persona"


def test_regenerate_persona_after_drift_lets_budget_exceeded_error_through(monkeypatch):
    import app.llm.client as _client_mod

    class _BudgetBlockedClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat_json(self, *args, **kwargs):
            raise BudgetExceededError("calls", 10, 10)

    monkeypatch.setattr(_client_mod, "LLMClient", _BudgetBlockedClient)

    gen = _make_generator()
    with pytest.raises(BudgetExceededError):
        gen._regenerate_persona_after_drift(
            entity_name="Schichtleiter Maschinenbau",
            entity_type="Person",
            persona_kind="individual",
            profession="Schichtleiter Maschinenbau",
            bio="Leitet die Produktionsplanung.",
            persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
            drifted_domains=["manufacturing"],
            source_text=DRIFT_SOURCE_TEXT,
        )


# --- Codex-Review-Findings auf PR #1573 (F1–F5) -----------------------------


def test_f1_persona_drift_correction_schema_lives_in_contracts_and_is_strict():
    """F1: LLM-Antwortvertrag gehört nach app.contracts (Contracts-first), nicht
    in ein Service-Modul — und ist so streng wie seine Nachbarn dort."""
    from app.contracts.persona_drift_contract import (
        PersonaDriftCorrectionSchema as ContractSchema,
    )

    # Reexport aus oasis_profile_models.py bleibt dieselbe Klasse.
    assert ContractSchema is PersonaDriftCorrectionSchema
    assert ContractSchema.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError):
        ContractSchema(bio="x", persona="y", profession="z", unexpected_field="nope")


def test_f2_collective_drift_prompt_has_no_profession_or_demographics_wording():
    """F2: Der Kollektiv-Korrekturprompt fordert keinen Beruf und keine Demografie an."""
    gen = _make_generator()
    prompt = gen._build_drift_correction_prompt(
        entity_name="Belegschaftsrat Fertigung",
        entity_type="EmployeeGroup",
        persona_kind="collective",
        profession="",
        bio="Vertritt die Fertigungsplanung.",
        persona_text="Spricht für die Sachbearbeiterinnen der Fertigungsplanung.",
        drifted_domains=["manufacturing"],
        source_text=DRIFT_SOURCE_TEXT,
    )
    assert "Bisheriger Beruf" not in prompt
    assert "kein Alter, kein Geschlecht, kein MBTI-Typ, keine Berufsbezeichnung" in prompt


def test_f2_individual_drift_prompt_asks_for_a_profession():
    """F2: Der Individuen-Korrekturprompt fordert weiterhin einen Beruf an."""
    gen = _make_generator()
    prompt = gen._build_drift_correction_prompt(
        entity_name="Schichtleiter Maschinenbau",
        entity_type="Person",
        persona_kind="individual",
        profession="Schichtleiter Maschinenbau",
        bio="Leitet die Produktionsplanung.",
        persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
        drifted_domains=["manufacturing"],
        source_text=DRIFT_SOURCE_TEXT,
    )
    assert "Bisheriger Beruf" in prompt


def test_f3_english_language_generator_gets_an_english_drift_prompt():
    """F3: ``language="en"`` erzeugt einen englischen statt eines immer-deutschen Prompts."""
    gen = OasisProfileGenerator(
        api_key="test-key", base_url="https://example.test/v1", language="en",
    )
    prompt = gen._build_drift_correction_prompt(
        entity_name="Schichtleiter Maschinenbau",
        entity_type="Person",
        persona_kind="individual",
        profession="Shift lead manufacturing",
        bio="Leads production planning.",
        persona_text="Runs production in the factory hall.",
        drifted_domains=["manufacturing"],
        source_text=DRIFT_SOURCE_TEXT,
    )
    assert "Rewrite profession, bio and free text" in prompt
    assert "Schreibe" not in prompt


def test_f4_a_correction_that_is_still_drifting_is_rejected_and_keeps_old_values():
    """F4: eine schema-gültige, aber weiterhin driftende Korrektur wird verworfen —
    kein zweiter LLM-Versuch, der alte Freitext und die alte Bio bleiben stehen."""
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(return_value={
        "bio": "Weiterhin zuständig für die Fertigungsplanung.",
        "persona": "Leitet weiterhin die Produktionsplanung in der Werkhalle.",
        "profession": "Schichtleiter Maschinenbau",
        "voice_register": "neutral-de",
    })

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Schichtleiter Maschinenbau",
        persona_kind="individual",
        profession="Schichtleiter Maschinenbau",
        bio="Leitet die Produktionsplanung.",
        persona_text="Verantwortet die Produktionsleitung in der Werkhalle.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    assert resolution.profession is None
    assert resolution.persona_text == "Verantwortet die Produktionsleitung in der Werkhalle."
    assert resolution.bio == "Leitet die Produktionsplanung."
    assert resolution.generation_error is not None
    assert "weiterhin driftend" in resolution.generation_error
    gen._regenerate_persona_after_drift.assert_called_once()


def test_f5_bio_only_domain_drift_reaches_the_correction_path():
    """F5: Drift ausschließlich in der Bio (Beruf und Freitext sauber) erreicht
    jetzt ebenfalls den Korrekturpfad."""
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(return_value={
        "bio": "Arbeitet in der Notaufnahme.",
        "persona": "Arbeitet seit Jahren im Team.",
        "profession": "",
        "voice_register": "neutral-de",
    })

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Teammitglied",
        persona_kind="individual",
        profession="",
        bio="Zuständig für die Fertigungsplanung.",
        persona_text="Arbeitet seit Jahren im Team.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    gen._regenerate_persona_after_drift.assert_called_once()
    assert gen._regenerate_persona_after_drift.call_args.kwargs["drifted_domains"] == ["manufacturing"]
    assert resolution.generation_error is None
    assert resolution.bio == "Arbeitet in der Notaufnahme."


def test_p2_source_true_bio_does_not_mask_drifting_persona_text():
    """Codex P2 auf PR #1575: Felder werden einzeln geprueft. Eine markerreiche,
    quellentreue Bio darf einen fachfremden Freitext nicht ueberdecken — als
    zusammengeklebter Text waere Healthcare die dominante Domaene gewesen und
    die Fertigungs-Drift des Freitexts unsichtbar."""
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(return_value={
        "bio": "Arbeitet in der Notaufnahme.",
        "persona": "Koordiniert die Pflege auf der Station.",
        "profession": "",
        "voice_register": "neutral-de",
    })

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Teammitglied",
        persona_kind="individual",
        profession="",
        bio=(
            "Seit Jahren in der Klinik, in der Pflege und in der Notaufnahme "
            "tätig; kennt Station, Ärzte und Patienten."
        ),
        persona_text="Leitet die Fertigungsplanung und die Produktionslinie.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    gen._regenerate_persona_after_drift.assert_called_once()
    assert gen._regenerate_persona_after_drift.call_args.kwargs["drifted_domains"] == ["manufacturing"]
    assert resolution.generation_error is None
    assert resolution.persona_text == "Koordiniert die Pflege auf der Station."


def test_p2_correction_with_drifting_bio_behind_clean_persona_is_rejected():
    """Codex P2 auf PR #1575, Gegenrichtung: Die Rest-Drift-Pruefung der
    Korrektur prueft die Bio einzeln — ein langer, sauberer Freitext darf eine
    fachfremde korrigierte Bio nicht verstecken."""
    gen = _make_generator()
    gen._regenerate_persona_after_drift = MagicMock(return_value={
        "bio": "Zuständig für die Fertigungsplanung.",
        "persona": (
            "Koordiniert die Pflege auf der Station, spricht täglich mit "
            "Ärzten und Patienten in der Klinik und der Notaufnahme."
        ),
        "profession": "",
        "voice_register": "neutral-de",
    })

    resolution = gen._persona_after_coherence_check(
        entity_type="Person",
        entity_name="Teammitglied",
        persona_kind="individual",
        profession="",
        bio="Zuständig für die Fertigungsplanung.",
        persona_text="Arbeitet seit Jahren im Team.",
        entity_summary=DRIFT_SOURCE_TEXT,
        entity_context="",
        use_llm=True,
    )

    assert resolution.generation_error is not None
    assert "weiterhin driftend (manufacturing)" in resolution.generation_error
    assert resolution.bio == "Zuständig für die Fertigungsplanung."
    assert resolution.persona_text == "Arbeitet seit Jahren im Team."

