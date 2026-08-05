"""
Tests für voice_register-Integration in OasisProfileGenerator.

Prüft:
- LLM liefert valides voice_register → landet im Profil
- LLM liefert ungültiges voice_register → fallback neutral-de, Validation-Eintrag in missing_fields
- LLM ohne voice_register-Key → fallback neutral-de
- rule-based-Fallback liefert gültiges Register
"""
from __future__ import annotations

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

def _build_llm_payload(voice_register_value) -> dict:
    """Persona-Payload, wie ``LLMClient.chat_json`` ihn zurückgibt.

    ``_generate_profile_with_llm`` spricht seit der ``chat_json``-Migration
    nicht mehr über ``self.client`` (rohes OpenAI-SDK), sondern konstruiert
    intern einen ``LLMClient`` und bekommt von ``chat_json`` bereits ein
    geparstes und gegen ``PersonaProfileSchema`` validiertes Dict. Ein
    Mock-Response-Objekt am alten Seam wurde deshalb schlicht ignoriert und
    die Tests liefen gegen den echten Endpunkt (beobachtet: HTTP 401 gegen
    ``https://api.minimax.io/v1``, danach stiller Fallback auf
    ``rule-based generation``).
    """
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
    return payload


def _patch_chat_json(payload: dict):
    """Ersetzt die LLM-Schicht durch einen Stub, der ``payload`` liefert.

    ``app.llm.client.LLMClient`` ist der richtige Patch-Punkt: die Methode
    importiert die Klasse spät (``from ..llm.client import LLMClient``),
    greift also zur Aufrufzeit auf das Modul-Attribut zu. Dasselbe Muster
    nutzt bereits ``tests/test_oasis_profile_generator.py``.
    """
    stub = MagicMock(name="LLMClient")
    stub.return_value.chat_json.return_value = payload
    return patch("app.llm.client.LLMClient", stub)


def test_llm_valid_voice_register_lands_in_profile():
    gen = _make_generator()

    with _patch_chat_json(_build_llm_payload("technical-de")):
        result = gen._generate_profile_with_llm(
            entity_name="Test GmbH",
            entity_type="company",
            entity_summary="Eine Softwarefirma.",
            entity_attributes={},
            context="",
        )
    assert result.get("voice_register") == "technical-de"


def test_llm_invalid_voice_register_fallback_neutral_de():
    """LLM liefert ungültiges voice_register → fallback neutral-de + Warning.

    ``PersonaProfileSchema`` typisiert ``voice_register`` nur als ``str``, der
    strict-Mode fängt ein ``english-uk`` also nicht ab. Die
    Enum-Zugehörigkeit prüft erst der Generator — genau diese defensive
    Schicht steht hier unter Test.
    """
    gen = _make_generator()

    with _patch_chat_json(_build_llm_payload("english-uk")), \
            patch("app.services.oasis_profile_generator.logger") as mock_logger:
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


def test_llm_missing_voice_register_fallback_neutral_de():
    """LLM ohne voice_register-Key → fallback neutral-de + Warning."""
    gen = _make_generator()

    with _patch_chat_json(_build_llm_payload(None)), \
            patch("app.services.oasis_profile_generator.logger") as mock_logger:
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
