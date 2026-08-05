"""Regression tests for the OASIS persona LLM-call wiring.

These tests guard against two MiniMax-M3 regressions in
``OasisProfileGenerator._generate_profile_with_llm``:

1. The method used to call the **raw** ``OpenAI`` client
   (``self.client.chat.completions.create``) with only
   ``response_format={"type": "json_object"}`` — no strict schema, no
   ``thinking.type: disabled``. MiniMax-M3 then emitted up to 63 % of the
   token budget as readable reasoning text *inside* ``content`` →
   ``json.loads`` failed ("Extra data", "Expecting value") → 3-fold retry
   loop → persona generation took ~1:30 per persona instead of ~15-20 s
   (30 personas × parallel=10 + retries = 30-40+ min apparent hang).

2. Even with the schema fix, M3 writes very detailed personas
   (2349+ tokens), so ``max_tokens=8192`` truncated mid-JSON.
   ``max_tokens`` must be >= 16384.

The fix routes the call through ``LLMClient.chat_json`` with a strict
``PersonaProfileSchema`` and ``force_no_thinking=True``, mirroring the
ontology-generator fix in PR #858.
"""

from __future__ import annotations

import pytest

from app.services import oasis_profile_generator as _mod
from unittest.mock import patch, MagicMock

from app.services.oasis_profile_generator import (
    OasisProfileGenerator,
    PersonaProfileSchema,
)


class _CapturingLLMClient:
    """Stub that captures ``chat_json`` kwargs and returns a valid persona dict.

    Avoids real LLM_API_KEY resolution and network calls. Pinned values satisfy
    ``_validate_profile_metadata`` (age 18-75, valid gender/mbti/country,
    valid voice_register) so the retry loop is not triggered.
    """

    last_instance = None

    def __init__(self, *args, **kwargs):
        _CapturingLLMClient.last_instance = self
        self.captured_kwargs = None

    def chat(self, *args, **kwargs):  # pragma: no cover - not called
        raise AssertionError("chat() must not be called by _generate_profile_with_llm")

    def chat_json(self, messages, temperature=0.7, max_tokens=8192,
                  schema=None, schema_name="structured_response",
                  context="chat_json", force_no_thinking=False, **kwargs):
        self.captured_kwargs = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "schema": schema,
            "schema_name": schema_name,
            "context": context,
            "force_no_thinking": force_no_thinking,
        }
        return {
            "display_name": "Lena Hoffmann",
            "handle": "lena_hoffmann",
            "bio": "Mobilitätsberaterin aus München.",
            "persona": "Ausführliche Personenbeschreibung.",
            "age": 41,
            "gender": "female",
            "mbti": "INTJ",
            "country": "DE",
            "profession": "Verkehrsplanerin",
            "interested_topics": ["Radinfrastruktur", "Stadtplanung"],
            "voice_register": "neutral-de",
        }


def _make_generator():
    """Build a generator with a dummy api_key so the constructor passes."""
    return OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")


def test_generate_profile_with_llm_uses_persona_profile_schema(monkeypatch):
    """Regression: _generate_profile_with_llm must call chat_json with
    schema=PersonaProfileSchema.

    Without a strict Pydantic schema, MiniMax-M3 mixes prose into the JSON
    (finish=stop, budget not exhausted) → parse failures. Passing the schema
    forces the provider into strict ``json_schema`` mode.
    """
    monkeypatch.setattr(_mod, "_LLMClient_alias", _CapturingLLMClient, raising=False)
    # Patch the inline import target inside _generate_profile_with_llm.
    import app.llm.client as _client_mod
    monkeypatch.setattr(_client_mod, "LLMClient", _CapturingLLMClient)

    gen = _make_generator()
    result = gen._generate_profile_with_llm(
        entity_name="ADFC Muenchen",
        entity_type="CyclingAdvocate",
        entity_summary="Cycling advocacy group.",
        entity_attributes={},
        context="Radweg-Konflikt München",
    )

    assert result["display_name"] == "Lena Hoffmann"
    assert result["age"] == 41
    # The stub instance captured the kwargs on the FIRST call of this
    # generator's _generate_profile_with_llm. Retrieve it via the patched class.
    assert _CapturingLLMClient.last_instance is not None
    captured = _CapturingLLMClient.last_instance.captured_kwargs
    assert captured is not None, "chat_json was not called"
    assert captured["schema"] is PersonaProfileSchema, (
        "_generate_profile_with_llm must pass schema=PersonaProfileSchema so "
        "MiniMax-M3 answers in strict json_schema mode"
    )
    assert captured["schema_name"] == "persona_profile"


def test_generate_profile_with_llm_passes_force_no_thinking_true(monkeypatch):
    """Regression: _generate_profile_with_llm must set force_no_thinking=True.

    Without it MiniMax-M3 emits up to 63 % of the token budget as readable
    reasoning text inside ``content`` → invalid JSON → retry loop → extreme
    slowdown / apparent hang.
    """
    import app.llm.client as _client_mod
    monkeypatch.setattr(_client_mod, "LLMClient", _CapturingLLMClient)

    gen = _make_generator()
    gen._generate_profile_with_llm(
        entity_name="Oberbuergermeister Muenchen",
        entity_type="Mayor",
        entity_summary="Mayor of Munich.",
        entity_attributes={},
        context="Radweg-Konflikt München",
    )

    captured = _CapturingLLMClient.last_instance.captured_kwargs
    assert captured is not None, "chat_json was not called"
    assert captured["force_no_thinking"] is True, (
        "_generate_profile_with_llm must pass force_no_thinking=True so "
        "MiniMax-M3 reasoning output is disabled and the token budget is "
        "available for the JSON content"
    )


def test_generate_profile_with_llm_uses_sufficient_max_tokens(monkeypatch):
    """Regression: max_tokens must be >= 16384.

    M3 writes very detailed personas (2349+ tokens observed). The old 8192
    truncated mid-JSON ("likely truncated — try raising max_token").
    """
    import app.llm.client as _client_mod
    monkeypatch.setattr(_client_mod, "LLMClient", _CapturingLLMClient)

    gen = _make_generator()
    gen._generate_profile_with_llm(
        entity_name="ADFC Muenchen",
        entity_type="CyclingAdvocate",
        entity_summary="Cycling advocacy group.",
        entity_attributes={},
        context="Radweg-Konflikt München",
    )

    captured = _CapturingLLMClient.last_instance.captured_kwargs
    assert captured is not None, "chat_json was not called"
    assert captured["max_tokens"] >= 16384, (
        "max_tokens must be >= 16384 — M3 produces 2349+ token personas and "
        "8192 truncated mid-JSON"
    )


@pytest.mark.parametrize('level,expected_max_tokens', [
    ('compact', 8192),
    ('standard', 16384),
    ('rich', 32768),
])
def test_generate_profile_with_llm_derives_max_tokens_from_detail_level(
    monkeypatch, hermetic_settings, level, expected_max_tokens,
):
    """Issue #868: max_tokens must be derived from AGORA_PERSONA_DETAIL_LEVEL.

    compact/standard/rich map to 8192/16384/32768 so the output token budget
    tracks the requested persona detail level instead of a fixed constant.
    """
    monkeypatch.setenv('AGORA_PERSONA_DETAIL_LEVEL', level)
    import app.llm.client as _client_mod
    monkeypatch.setattr(_client_mod, "LLMClient", _CapturingLLMClient)

    gen = _make_generator()
    gen._generate_profile_with_llm(
        entity_name="ADFC Muenchen",
        entity_type="CyclingAdvocate",
        entity_summary="Cycling advocacy group.",
        entity_attributes={},
        context="Radweg-Konflikt München",
    )

    captured = _CapturingLLMClient.last_instance.captured_kwargs
    assert captured is not None, "chat_json was not called"
    assert captured["max_tokens"] == expected_max_tokens, (
        f"AGORA_PERSONA_DETAIL_LEVEL={level!r} must yield max_tokens="
        f"{expected_max_tokens}, got {captured['max_tokens']}"
    )


def test_generate_profile_with_llm_unknown_detail_level_uses_standard_max_tokens(
    monkeypatch, hermetic_settings,
):
    """Issue #868: unknown AGORA_PERSONA_DETAIL_LEVEL falls back to 'standard'
    budget (16384), mirroring _resolve_persona_detail_level's existing
    fallback (with logger.warning)."""
    monkeypatch.setenv('AGORA_PERSONA_DETAIL_LEVEL', 'bogus')
    import app.llm.client as _client_mod
    monkeypatch.setattr(_client_mod, "LLMClient", _CapturingLLMClient)

    gen = _make_generator()
    gen._generate_profile_with_llm(
        entity_name="ADFC Muenchen",
        entity_type="CyclingAdvocate",
        entity_summary="Cycling advocacy group.",
        entity_attributes={},
        context="Radweg-Konflikt München",
    )

    captured = _CapturingLLMClient.last_instance.captured_kwargs
    assert captured is not None, "chat_json was not called"
    assert captured["max_tokens"] == 16384, (
        "Unknown AGORA_PERSONA_DETAIL_LEVEL must fall back to 'standard' "
        "max_tokens=16384, matching _resolve_persona_detail_level's default"
    )


def test_persona_profile_schema_rejects_age_out_of_range():
    """PersonaProfileSchema must enforce age 18-75 (per prompt + validation)."""
    from pydantic import ValidationError

    valid = PersonaProfileSchema(
        display_name="Test Person", handle="test", age=30, gender="female",
        mbti="INTJ", country="DE", voice_register="neutral-de",
    )
    assert valid.age == 30

    for bad_age in (17, 76, 0):
        try:
            PersonaProfileSchema(
                display_name="Test", handle="t", age=bad_age, gender="male",
                mbti="INTJ", country="DE", voice_register="formal-de",
            )
            raise AssertionError(f"age={bad_age} should be rejected")
        except ValidationError:
            pass


def test_fix_truncated_json_method_removed():
    """Issue #869: _fix_truncated_json duplication must be removed."""
    gen = _make_generator()
    assert not hasattr(gen, "_fix_truncated_json"), (
        "Issue #869: OasisProfileGenerator._fix_truncated_json must be removed; "
        "truncation repair is delegated to app.llm.json_mode._try_repair_truncated_json."
    )


def test_try_fix_json_truncated_input_recovers_via_centralized_helper(monkeypatch):
    """Issue #869: _try_fix_json delegates truncation repair to the centralized helper."""
    from app.llm.json_mode import _try_repair_truncated_json

    # Spy that delegates to the real helper — proves _try_fix_json actually
    # routes through the centralized function (and not via a reintroduced
    # local repair path). Issue #869.
    calls = []

    def spy(payload):
        calls.append(payload)
        return _try_repair_truncated_json(payload)

    monkeypatch.setattr(
        "app.services.oasis_profile_generator._try_repair_truncated_json",
        spy,
    )

    gen = _make_generator()
    # Truncated mid-string: opening brace, key, value cut before the closing quote.
    truncated = '{"bio": "Lena lebt in Münch'

    # Sanity: the centralized helper repairs this case (closes the open string
    # and the unclosed top-level brace).
    repaired = _try_repair_truncated_json(truncated)
    assert repaired is not None, "centralized helper must repair this case"
    assert repaired.endswith('"}'), (
        f"centralized helper must close the open string + brace, got: {repaired!r}"
    )

    # Regression: _try_fix_json still recovers the payload and marks it as fixed.
    result = gen._try_fix_json(
        truncated, entity_name="Lena", entity_type="Person",
        entity_summary="Lena lebt in München",
    )
    assert isinstance(result, dict)
    assert result.get("_fixed") is True, (
        f"truncated input must be marked _fixed=True, got: {result!r}"
    )
    assert "bio" in result
    assert calls == [truncated], (
        f"_try_fix_json must delegate to the centralized helper with the original "
        f"truncated payload, got spy calls: {calls!r}"
    )


def test_try_fix_json_valid_input_parses_without_repair():
    """Issue #869: valid JSON parses via the unchanged downstream path (regex/json.loads)."""
    import json as _json

    gen = _make_generator()
    valid = _json.dumps({
        "bio": "Mobilitätsberaterin aus München.",
        "persona": "Ausführliche Personenbeschreibung.",
        "age": 41,
        "gender": "female",
        "mbti": "INTJ",
        "country": "DE",
        "voice_register": "neutral-de",
    })

    result = gen._try_fix_json(
        valid, entity_name="Lena", entity_type="Person",
        entity_summary="Lena lebt in München",
    )
    assert isinstance(result, dict)
    assert result.get("bio") == "Mobilitätsberaterin aus München."


@patch("app.services.oasis_profile_generator._resolve_persona_detail_level")
@patch("app.llm.client.LLMClient")
def test_issue_882_resolve_persona_detail_level_called_once_individual(mock_llm_client, mock_resolve_level):
    """
    Test that _resolve_persona_detail_level is called exactly once per persona generation for individual entities.
    """
    mock_resolve_level.return_value = {
        'max_tokens': 16384, 
        'context_limit': 1500,
        'word_count_de': 'ca. 200 Wörter',
        'word_count_en': 'approx. 200 words'
    }
    
    # Setup LLM mock
    mock_instance = mock_llm_client.return_value
    mock_instance.chat_json.return_value = {
        "bio": "Mocked Bio",
        "persona": "Mocked Persona",
        "age": 30,
        "gender": "male",
        "mbti": "INTJ",
        "country": "Germany",
        "profession": "Engineer",
        "interested_topics": ["Tech"],
        "voice_register": "neutral-de"
    }

    generator = _make_generator()
    generator._industry_quota_plan = MagicMock()

    with patch.object(generator, "_is_individual_entity", return_value=True), \
         patch.object(generator, "_get_system_prompt", return_value="sys_prompt"):
        
        generator._generate_profile_with_llm(
            entity_name="Max",
            entity_type="person",
            entity_summary="Summary",
            entity_attributes={},
            context="Context"
        )
        
        # Verify it was called exactly once
        assert mock_resolve_level.call_count == 1

@patch("app.services.oasis_profile_generator._resolve_persona_detail_level")
@patch("app.llm.client.LLMClient")
def test_issue_882_resolve_persona_detail_level_called_once_group(mock_llm_client, mock_resolve_level):
    """
    Test that _resolve_persona_detail_level is called exactly once per persona generation for group entities.
    """
    mock_resolve_level.return_value = {
        'max_tokens': 16384, 
        'context_limit': 1500,
        'word_count_de': 'ca. 200 Wörter',
        'word_count_en': 'approx. 200 words'
    }
    
    # Setup LLM mock
    mock_instance = mock_llm_client.return_value
    mock_instance.chat_json.return_value = {
        "bio": "Mocked Bio",
        "persona": "Mocked Persona",
        "age": 30,
        "gender": "male",
        "mbti": "INTJ",
        "country": "Germany",
        "profession": "Engineer",
        "interested_topics": ["Tech"],
        "voice_register": "neutral-de"
    }

    generator = _make_generator()
    generator._industry_quota_plan = MagicMock()

    with patch.object(generator, "_is_individual_entity", return_value=False), \
         patch.object(generator, "_get_system_prompt", return_value="sys_prompt"):
        
        generator._generate_profile_with_llm(
            entity_name="Group",
            entity_type="org",
            entity_summary="Summary",
            entity_attributes={},
            context="Context"
        )
        
        # Verify it was called exactly once
        assert mock_resolve_level.call_count == 1
