"""
Tests für voice_register-Integration in OasisProfileGenerator.

Prüft:
- LLM liefert valides voice_register → landet im Profil
- LLM liefert ungültiges voice_register → fallback neutral-de, Validation-Eintrag in missing_fields
- LLM ohne voice_register-Key → fallback neutral-de
- rule-based-Fallback liefert gültiges Register
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.oasis_profile_generator import (
    VOICE_REGISTERS,
    OasisProfileGenerator,
)


# ---------------------------------------------------------------------------
# Hilfsfunktion: minimaler Generator ohne echte LLM-Verbindung
# ---------------------------------------------------------------------------

def _make_generator() -> OasisProfileGenerator:
    with patch("app.services.oasis_profile_generator.OpenAI"):
        gen = OasisProfileGenerator(api_key="fake-key")
    return gen


# ---------------------------------------------------------------------------
# _validate_profile_metadata
# ---------------------------------------------------------------------------

def test_validate_accepts_valid_voice_register():
    gen = _make_generator()
    result = {
        "age": 35,
        "gender": "female",
        "mbti": "INTJ",
        "country": "DE",
        "voice_register": "technical-de",
    }
    errors = gen._validate_profile_metadata(result)
    # voice_register sollte KEINEN Fehler produzieren
    vr_errors = [e for e in errors if "voice_register" in e]
    assert not vr_errors, f"Unerwarteter voice_register-Fehler: {vr_errors}"


def test_validate_rejects_invalid_voice_register():
    gen = _make_generator()
    result = {
        "age": 35,
        "gender": "male",
        "mbti": "ENFP",
        "country": "DE",
        "voice_register": "english-uk",
    }
    errors = gen._validate_profile_metadata(result)
    vr_errors = [e for e in errors if "voice_register" in e]
    assert vr_errors, "Erwartet Fehler für ungültiges voice_register"


# ---------------------------------------------------------------------------
# _generate_profile_with_llm — LLM liefert valides voice_register
# ---------------------------------------------------------------------------

def _build_llm_response(voice_register_value) -> MagicMock:
    """Baue einen Mock-OpenAI-Response mit dem gewünschten voice_register."""
    payload = {
        "bio": "Erfahrene Entwicklerin.",
        "persona": "x" * 400,
        "display_name": "Lena Tester",
        "handle": "lena_tester",
        "age": 34,
        "gender": "female",
        "mbti": "INTJ",
        "country": "DE",
        "profession": "Software-Entwicklerin",
        "interested_topics": ["Technologie"],
    }
    if voice_register_value is not None:
        payload["voice_register"] = voice_register_value

    mock_message = MagicMock()
    mock_message.content = json.dumps(payload)
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


def test_llm_valid_voice_register_lands_in_profile():
    gen = _make_generator()
    gen.client.chat.completions.create.return_value = _build_llm_response("technical-de")

    result = gen._generate_profile_with_llm(
        entity_name="Test GmbH",
        entity_type="company",
        entity_summary="Eine Softwarefirma.",
        entity_attributes={},
        context="",
    )
    assert result.get("voice_register") == "technical-de"


def test_llm_invalid_voice_register_fallback_neutral_de():
    """LLM liefert ungültiges voice_register → fallback neutral-de + Warning."""
    import logging
    gen = _make_generator()
    gen.client.chat.completions.create.return_value = _build_llm_response("english-uk")

    # Agora-Logger propagiert nicht zum Root-Logger; Handler direkt mitschneiden.
    oasis_logger = logging.getLogger("agora.oasis_profile")
    oasis_logger.propagate = True
    try:
        with patch("app.services.oasis_profile_generator.logger") as mock_logger:
            result = gen._generate_profile_with_llm(
                entity_name="Test",
                entity_type="person",
                entity_summary="Jemand.",
                entity_attributes={},
                context="",
            )
            # Prüfe: warning wurde mit 'neutral-de' gerufen
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
            assert any("neutral-de" in c for c in warning_calls), (
                f"Erwartet Warning mit 'neutral-de', got: {warning_calls}"
            )
    finally:
        oasis_logger.propagate = False

    assert result.get("voice_register") == "neutral-de"


def test_llm_missing_voice_register_fallback_neutral_de():
    """LLM ohne voice_register-Key → fallback neutral-de + Warning."""
    gen = _make_generator()
    # Kein voice_register-Key in Payload
    gen.client.chat.completions.create.return_value = _build_llm_response(None)

    with patch("app.services.oasis_profile_generator.logger") as mock_logger:
        result = gen._generate_profile_with_llm(
            entity_name="Test",
            entity_type="person",
            entity_summary="Jemand.",
            entity_attributes={},
            context="",
        )
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("neutral-de" in c for c in warning_calls), (
            f"Erwartet Warning mit 'neutral-de', got: {warning_calls}"
        )

    assert result.get("voice_register") == "neutral-de"


# ---------------------------------------------------------------------------
# _generate_profile_rule_based — liefert gültiges Register
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entity_type", [
    "student", "alumni", "publicfigure", "expert", "faculty",
    "mediaoutlet", "university", "governmentagency", "ngo", "organization",
    "unknown_type",
])
def test_rule_based_voice_register_is_valid(entity_type: str):
    gen = _make_generator()
    result = gen._generate_profile_rule_based(
        entity_name="Beispiel",
        entity_type=entity_type,
        entity_summary="Kurze Zusammenfassung.",
        entity_attributes={},
    )
    vr = result.get("voice_register")
    assert vr in VOICE_REGISTERS, f"Ungültiges voice_register '{vr}' für entity_type='{entity_type}'"


# ---------------------------------------------------------------------------
# _rule_based_voice_register — direkte Einzel-Heuristik-Tests
# ---------------------------------------------------------------------------

def test_rule_based_heuristic_formal_for_government():
    result = OasisProfileGenerator._rule_based_voice_register("governmentagency", "Beamtin")
    assert result == "formal-de"


def test_rule_based_heuristic_technical_for_developer():
    result = OasisProfileGenerator._rule_based_voice_register("expert", "software developer")
    assert result == "technical-de"


def test_rule_based_heuristic_skeptisch_for_journalist():
    result = OasisProfileGenerator._rule_based_voice_register("mediaoutlet", "journalist")
    assert result == "skeptisch-de"


def test_rule_based_heuristic_neutral_default():
    result = OasisProfileGenerator._rule_based_voice_register("student", "Student")
    assert result == "neutral-de"
