"""Regression: geschlossene Persona-Wertemengen werden technisch erzwungen (Befund J).

``gender``, ``voice_register``, ``persona_kind`` und ``generation_source`` waren
im Schema bzw. in der Dataclass freie ``str``. Die zulaessigen Werte standen nur
in Prompttexten und Laufzeitpruefungen — ein abweichender Wert fiel erst dort
auf, wo er konsumiert wurde, und bei ``persona_kind``/``generation_source``
teilweise ueberhaupt nicht mehr: beide landen unveraendert in
``reddit_profiles.json`` und steuern Persona-Galerie und Report-Kennzeichnung.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.oasis_profile_models import (
    CollectivePersonaSchema,
    OasisAgentProfile,
    PersonaProfileSchema,
)

_BASE_INDIVIDUAL = {
    "display_name": "Maria Koch",
    "handle": "maria_koch",
    "bio": "Elternvertreterin",
    "persona": "Engagiert und skeptisch.",
    "age": 42,
    "gender": "female",
    "mbti": "INFJ",
    "country": "DE",
    "profession": "Lehrerin",
    "interested_topics": ["Bildung"],
    "voice_register": "neutral-de",
}

_BASE_COLLECTIVE = {
    "bio": "Bildungstraeger",
    "persona": "Eine Organisation.",
    "country": "DE",
    "interested_topics": ["Bildung"],
    "voice_register": "formal-de",
}


class TestPersonaGender:
    @pytest.mark.parametrize("gender", ["male", "female", "nonbinary"])
    def test_valid_genders_pass(self, gender: str) -> None:
        assert PersonaProfileSchema.model_validate({**_BASE_INDIVIDUAL, "gender": gender})

    @pytest.mark.parametrize("gender", ["other", "OTHER", "Male", "divers", "", 1, True])
    def test_invalid_genders_are_rejected(self, gender) -> None:
        """``other`` ist fuer Individualpersonas ausdruecklich verboten — der
        eigene Prompt sagt "das ist Institutionen vorbehalten", und die
        Gewichtstabelle erzeugt es nie."""
        with pytest.raises(ValidationError):
            PersonaProfileSchema.model_validate({**_BASE_INDIVIDUAL, "gender": gender})

    def test_null_stays_allowed_for_the_rejection_path(self) -> None:
        """Bei ``ineligible: true`` gibt es keine Demografie, die nicht erfunden
        waere; der strict-Mode macht jedes Feld zum Pflichtfeld."""
        payload = PersonaProfileSchema.model_validate(
            {**_BASE_INDIVIDUAL, "gender": None, "ineligible": True}
        )

        assert payload.gender is None


class TestVoiceRegister:
    @pytest.mark.parametrize(
        "register", ["formal-de", "neutral-de", "technical-de", "skeptisch-de"]
    )
    def test_valid_registers_pass(self, register: str) -> None:
        assert PersonaProfileSchema.model_validate(
            {**_BASE_INDIVIDUAL, "voice_register": register}
        )
        assert CollectivePersonaSchema.model_validate(
            {**_BASE_COLLECTIVE, "voice_register": register}
        )

    @pytest.mark.parametrize("register", ["informal-de", "neutral", "NEUTRAL-DE", "de", 3])
    def test_invalid_registers_are_rejected(self, register) -> None:
        with pytest.raises(ValidationError):
            PersonaProfileSchema.model_validate(
                {**_BASE_INDIVIDUAL, "voice_register": register}
            )
        with pytest.raises(ValidationError):
            CollectivePersonaSchema.model_validate(
                {**_BASE_COLLECTIVE, "voice_register": register}
            )

    def test_null_keeps_the_existing_neutral_de_fallback_reachable(self) -> None:
        assert (
            PersonaProfileSchema.model_validate(
                {**_BASE_INDIVIDUAL, "voice_register": None}
            ).voice_register
            is None
        )


class TestSchemaEnumsReachTheProvider:
    def test_json_schema_exposes_the_closed_sets_as_enums(self) -> None:
        """Der Wert des geschlossenen Sets liegt auch darin, dass der Provider
        im strict-json_schema-Mode gar nichts anderes liefern *kann*."""
        schema = PersonaProfileSchema.model_json_schema()

        gender_enum = _enum_values(schema, "gender")
        assert set(gender_enum) == {"male", "female", "nonbinary"}
        register_enum = _enum_values(schema, "voice_register")
        assert set(register_enum) == {
            "formal-de",
            "neutral-de",
            "technical-de",
            "skeptisch-de",
        }


def _enum_values(schema: dict, field: str) -> list:
    node = schema["properties"][field]
    for candidate in node.get("anyOf", [node]):
        if "enum" in candidate:
            return candidate["enum"]
    raise AssertionError(f"{field} has no enum in {node}")


class TestDataclassValueSets:
    """``OasisAgentProfile`` ist eine Dataclass — ``Literal`` allein prueft
    nichts zur Laufzeit, deshalb ein expliziter ``__post_init__``-Riegel."""

    @staticmethod
    def _profile(**overrides) -> OasisAgentProfile:
        payload = {
            "user_id": 1,
            "user_name": "maria_koch",
            "name": "Maria Koch",
            "bio": "Bio",
            "persona": "Persona",
        }
        payload.update(overrides)
        return OasisAgentProfile(**payload)

    @pytest.mark.parametrize("kind", ["individual", "collective"])
    def test_valid_persona_kind(self, kind: str) -> None:
        assert self._profile(persona_kind=kind).persona_kind == kind

    @pytest.mark.parametrize("kind", ["Individual", "group", "", None])
    def test_invalid_persona_kind_is_rejected(self, kind) -> None:
        with pytest.raises(ValueError, match="persona_kind"):
            self._profile(persona_kind=kind)

    @pytest.mark.parametrize("source", ["llm", "rule_based"])
    def test_valid_generation_source(self, source: str) -> None:
        assert self._profile(generation_source=source).generation_source == source

    @pytest.mark.parametrize("source", ["rule-based", "fallback", "LLM", "", None])
    def test_invalid_generation_source_is_rejected(self, source) -> None:
        with pytest.raises(ValueError, match="generation_source"):
            self._profile(generation_source=source)

    def test_defaults_are_valid(self) -> None:
        profile = self._profile()

        assert profile.persona_kind == "individual"
        assert profile.generation_source == "llm"
