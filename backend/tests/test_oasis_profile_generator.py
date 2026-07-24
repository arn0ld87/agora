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

from app.services import oasis_profile_generator as _mod
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