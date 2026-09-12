"""Regression: Kollektiv-Ablehnung passt zum Kollektiv-Schema (Befund I).

Root Cause: ``_build_eligibility_prompt_block`` erzeugte einen einzigen Text
fuer beide Persona-Arten. Bei ``ineligible: true`` verlangte er woertlich
``display_name``, ``handle``, ``age 30``, ``gender other``, ``mbti ISTJ`` und
ein leeres ``profession`` — Felder, die ``CollectivePersonaSchema`` gar nicht
kennt. Der Kollektivzweig laeuft aber genau gegen dieses Schema, und der
Strict-JSON-Schema-Mode setzt ``additionalProperties: false``. Prompt und
Vertrag widersprachen sich also fuer jede Gruppen-Entitaet, die abgelehnt
werden sollte.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import pytest

from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import (
    CollectivePersonaSchema,
    OasisProfileGenerator,
    PersonaProfileSchema,
)
from app.services.oasis_profile_models import PersonaIneligible

_INDIVIDUAL_ONLY_FIELDS = ("display_name", "handle", "age", "gender", "mbti", "profession")


@pytest.fixture()
def generator() -> OasisProfileGenerator:
    return OasisProfileGenerator(api_key="test-key", base_url="http://localhost:11434")


def _entity(name: str, entity_type: str) -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=[entity_type],
        summary="Zusammenfassung",
        attributes={},
    )


class TestCollectiveEligibilityPrompt:
    def test_collective_block_names_no_schema_foreign_fields(self, generator) -> None:
        block = generator._build_eligibility_prompt_block(
            "Nordharz Bildungswerk gGmbH", "Organization", is_collective=True
        )

        allowed = set(CollectivePersonaSchema.model_fields)
        for field in _INDIVIDUAL_ONLY_FIELDS:
            assert field not in allowed  # Vorbedingung des Befunds
            # Wortgrenzen, damit deutsche Fliesstextwoerter wie
            # "Interessenlage" nicht als Feldnennung von "age" zaehlen.
            assert not re.search(rf"\b{field}\b", block), (
                f"collective prompt still demands {field!r}"
            )

    def test_collective_block_still_asks_for_the_rejection(self, generator) -> None:
        block = generator._build_eligibility_prompt_block(
            "Moodle", "Organization", is_collective=True
        )

        assert "ineligible" in block
        assert "ineligible_reason" in block

    def test_individual_block_keeps_its_placeholders(self, generator) -> None:
        block = generator._build_eligibility_prompt_block(
            "Moodle", "Organization", is_collective=False
        )

        assert "display_name" in block
        assert "ineligible" in block

    @pytest.mark.parametrize("is_collective", [True, False])
    @pytest.mark.parametrize("language", ["de", "en"])
    def test_placeholders_named_in_the_prompt_validate_against_the_used_schema(
        self, generator, is_collective: bool, language: str
    ) -> None:
        """Die im Prompt genannten Platzhalter muessen gegen genau das Schema
        validieren, das der jeweilige Zweig an ``chat_json`` uebergibt."""
        generator.language = language
        block = generator._build_eligibility_prompt_block(
            "Moodle", "Organization", is_collective=is_collective
        )

        schema = CollectivePersonaSchema if is_collective else PersonaProfileSchema
        payload = _placeholder_payload(block, schema)

        assert schema.model_validate(payload).ineligible is True


def _placeholder_payload(block: str, schema) -> Dict[str, Any]:
    """Baut die Antwort, die ein prompt-treues Modell liefern wuerde.

    Nur Felder, die das Schema kennt — genau das ist der Punkt des Befunds.
    """
    payload: Dict[str, Any] = {"ineligible": True, "ineligible_reason": "Lernplattform"}
    if "country" in schema.model_fields:
        match = re.search(r"country (\w\w)", block)
        assert match, "prompt nennt keinen country-Platzhalter"
        payload["country"] = match.group(1)
    if "voice_register" in schema.model_fields:
        match = re.search(r"voice_register ([a-z-]+)", block)
        assert match, "prompt nennt keinen voice_register-Platzhalter"
        payload["voice_register"] = match.group(1)
    if "age" in schema.model_fields:
        match = re.search(r"age (\d+)", block)
        assert match, "prompt nennt keinen age-Platzhalter"
        payload["age"] = int(match.group(1))
    if "display_name" in schema.model_fields:
        payload["display_name"] = "-"
        payload["handle"] = "-"
    if "mbti" in schema.model_fields:
        payload["mbti"] = "ISTJ"
    return payload


class TestCollectiveRejectionReachesTheCaller:
    def test_schema_valid_collective_rejection_raises_without_retry(
        self, generator, monkeypatch
    ) -> None:
        """Eine schema-gueltige Kollektiv-Ablehnung muss beim ersten Versuch
        greifen: kein Retry wegen Schema-Widerspruch, kein regelbasierter
        Fallback, der die abgelehnte Entitaet wieder einfuehrt."""
        calls: List[Dict[str, Any]] = []

        class _Llm:
            def __init__(self, **kwargs: Any) -> None:
                pass

            def chat_json(self, **kwargs: Any) -> Dict[str, Any]:
                calls.append(kwargs)
                payload = {
                    "bio": "",
                    "persona": "",
                    "country": "DE",
                    "interested_topics": [],
                    "voice_register": "neutral-de",
                    "ineligible": True,
                    "ineligible_reason": "Lernplattform, kein menschlicher Traeger",
                }
                # Genau die Validierung, die chat_json(schema=...) fahren wuerde.
                return kwargs["schema"].model_validate(payload).model_dump(mode="json")

        monkeypatch.setattr("app.llm.client.LLMClient", _Llm)

        with pytest.raises(PersonaIneligible) as excinfo:
            generator.generate_profile_from_entity(
                entity=_entity("Moodle", "Organization"), user_id=0, use_llm=True
            )

        assert len(calls) == 1, f"rejection needed {len(calls)} LLM attempts"
        assert calls[0]["schema"] is CollectivePersonaSchema
        assert "Lernplattform" in excinfo.value.reason
