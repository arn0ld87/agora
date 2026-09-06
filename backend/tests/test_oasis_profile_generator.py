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

import logging
import re

import pytest

from app.services import oasis_profile_generator as _mod
from unittest.mock import patch, MagicMock

from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import (
    OasisAgentProfile,
    OasisProfileGenerator,
    PersonaIneligible,
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
        self.init_kwargs = kwargs

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


def test_constructor_does_not_env_fallback_for_codex_cli(monkeypatch):
    """Regression for Issue #1418.

    ``codex_cli`` (transport="cli", #1405) hat weder base_url noch api_key —
    das ist der Normalfall, kein unaufgeloester Zustand. Ohne
    ``provider_type`` fuellte der Konstruktor ``self.base_url`` mit
    ``Config.LLM_BASE_URL`` auf (beobachtet: das aus der codex_cli-Route
    geroutete Modell ``gpt-5.6-luna`` ging an ``https://api.minimax.io/v1``
    → HTTP 400 "unknown model").
    """
    from app.config import Config

    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://api.minimax.io/v1")
    monkeypatch.setattr(Config, "LLM_API_KEY", "env-minimax-key")

    gen = OasisProfileGenerator(provider_type="codex_cli", model_name="gpt-5.6-luna")

    assert gen.base_url is None
    assert gen.api_key != "env-minimax-key"


def test_generate_profile_with_llm_passes_provider_type_for_codex_cli(monkeypatch):
    """Regression for Issue #1418: ohne ``provider_type`` an ``_LLMClient``
    weitergereicht erkennt ``LLMClient`` codex_cli nicht als
    Subprozess-Provider (``_codex_cli_active``) und versucht einen HTTP-Call
    gegen ``self.base_url`` — der dann aus dem generischen Fallback stammt.
    """
    import app.llm.client as _client_mod
    monkeypatch.setattr(_client_mod, "LLMClient", _CapturingLLMClient)

    gen = OasisProfileGenerator(provider_type="codex_cli", model_name="gpt-5.6-luna")
    gen._generate_profile_with_llm(
        entity_name="ADFC Muenchen",
        entity_type="CyclingAdvocate",
        entity_summary="Cycling advocacy group.",
        entity_attributes={},
        context="Radweg-Konflikt München",
    )

    assert _CapturingLLMClient.last_instance is not None
    init_kwargs = _CapturingLLMClient.last_instance.init_kwargs
    assert init_kwargs["provider_type"] == "codex_cli"
    assert init_kwargs["base_url"] is None


# ---------------------------------------------------------------------------
# Regression: eine abgelehnte Entitaet darf nie als "Successfully generated"
# geloggt werden (Produktionsbeleg: 8 von 23 Kandidaten wurden abgelehnt und
# tauchten trotzdem als Erfolgsmeldung im Log auf; der spaetere
# Reportabbruch "15/20 Personas" kam dadurch scheinbar aus dem Nichts).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _enable_oasis_log_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    """``setup_logger`` setzt ``propagate=False`` (app/utils/logger.py:226).

    Wie in ``tests/llm/test_init_logging.py``: Parent ``agora`` UND der
    Ziel-Logger ``agora.oasis_profile`` muessen beide auf ``propagate=True``
    gesetzt werden, sonst sieht ``caplog`` keine Records.
    """
    parent = logging.getLogger("agora")
    target = logging.getLogger("agora.oasis_profile")
    monkeypatch.setattr(parent, "propagate", True)
    monkeypatch.setattr(target, "propagate", True)


def _entity(name: str, entity_type: str) -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=["Entity", entity_type],
        summary="",
        attributes={},
    )


def _stub_generate_profile_from_entity(rejected_names: set[str]):
    """Ersetzt ``generate_profile_from_entity``: abgelehnte Namen werfen
    ``PersonaIneligible``, alle anderen liefern ein minimales gueltiges
    Profil. Kein LLM-Call, kein Netzwerk.
    """

    def _fake(self, *, entity, user_id, use_llm, demographic_slot=None, **_kw):
        entity_type = entity.get_entity_type() or "Entity"
        if entity.name in rejected_names:
            raise PersonaIneligible(
                entity.name, entity_type, "technisches Artefakt ohne eigene Interessenlage"
            )
        return OasisAgentProfile(
            user_id=user_id,
            user_name=f"user_{user_id}",
            name=entity.name,
            bio=f"{entity_type}: {entity.name}",
            persona="Eine Beispielperson.",
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )

    return _fake


def test_rejected_entity_is_not_logged_as_successfully_generated(monkeypatch, caplog):
    """Kernregression: die widerspruechliche Log-Sequenz aus dem Produktions-
    beleg (erst "Entitaet abgelehnt", dann trotzdem "Successfully generated
    persona" fuer dieselbe Entitaet) darf nicht mehr auftreten.
    """
    caplog.set_level(logging.INFO, logger="agora.oasis_profile")

    gen = _make_generator()
    monkeypatch.setattr(
        OasisProfileGenerator,
        "generate_profile_from_entity",
        _stub_generate_profile_from_entity({"digitaler Zwilling"}),
    )

    entities = [
        _entity("digitaler Zwilling", "Organization"),
        _entity("Max Mustermann", "Person"),
    ]

    profiles = gen.generate_profiles_from_entities(
        entities, use_llm=False, parallel_count=1
    )

    messages = [r.getMessage() for r in caplog.records if r.name == "agora.oasis_profile"]

    # Keine Erfolgsmeldung fuer die abgelehnte Entitaet.
    assert not any(
        "Successfully generated persona" in m and "digitaler Zwilling" in m
        for m in messages
    )
    # Die tatsaechliche Persona wird weiterhin korrekt als Erfolg gemeldet.
    assert any(
        "Successfully generated persona" in m and "Max Mustermann" in m
        for m in messages
    )
    # Die Ablehnungsmeldung nennt Name und Grund wahrheitsgemaess.
    assert any(
        "digitaler Zwilling" in m
        and "abgelehnt" in m
        and "technisches Artefakt ohne eigene Interessenlage" in m
        for m in messages
    )
    # Ohne Reservepool bleibt der Slot leer -- nur die echte Persona kommt zurueck.
    assert [p.name for p in profiles] == ["Max Mustermann"]


def test_persona_generation_summary_line_counts_with_rejections(monkeypatch, caplog):
    """Die Summenzeile am Ende muss Kandidaten, Ablehnungen und erzeugte
    Personas korrekt bilanzieren, ohne dass man die Einzelmeldungen zaehlen
    muss.
    """
    caplog.set_level(logging.INFO, logger="agora.oasis_profile")

    gen = _make_generator()
    monkeypatch.setattr(
        OasisProfileGenerator,
        "generate_profile_from_entity",
        _stub_generate_profile_from_entity({"digitaler Zwilling", "KI-Assistent"}),
    )

    entities = [
        _entity("digitaler Zwilling", "Organization"),
        _entity("KI-Assistent", "Product"),
        _entity("Max Mustermann", "Person"),
    ]

    gen.generate_profiles_from_entities(entities, use_llm=False, parallel_count=1)

    summary = [
        r.getMessage()
        for r in caplog.records
        if r.name == "agora.oasis_profile" and "Persona generation complete" in r.getMessage()
    ]
    assert len(summary) == 1
    assert "3 Kandidat(en) angetreten" in summary[0]
    assert "2 abgelehnt" in summary[0]
    assert "1 Personas erzeugt" in summary[0]


def test_persona_generation_summary_line_counts_without_rejections(monkeypatch, caplog):
    """Gegenprobe: ohne Ablehnungen muss die Bilanz 0 Ablehnungen und
    Kandidaten == erzeugte Personas ausweisen.
    """
    caplog.set_level(logging.INFO, logger="agora.oasis_profile")

    gen = _make_generator()
    monkeypatch.setattr(
        OasisProfileGenerator,
        "generate_profile_from_entity",
        _stub_generate_profile_from_entity(set()),
    )

    entities = [
        _entity("Max Mustermann", "Person"),
        _entity("Beispiel GmbH", "Company"),
    ]

    gen.generate_profiles_from_entities(entities, use_llm=False, parallel_count=1)

    summary = [
        r.getMessage()
        for r in caplog.records
        if r.name == "agora.oasis_profile" and "Persona generation complete" in r.getMessage()
    ]
    assert len(summary) == 1
    assert "2 Kandidat(en) angetreten" in summary[0]
    assert "0 abgelehnt" in summary[0]
    assert "2 Personas erzeugt" in summary[0]


def test_persona_generation_summary_line_stays_consistent_with_reserve_backfill(
    monkeypatch, caplog
):
    """Codex-Finding auf PR #1455: ``_backfill_rejected_slots`` haengt
    Ablehnungen aus dem Reserve-Backfill an ``rejected`` an, waehrend die
    Summenzeile zuvor nur die primaer angetretenen Kandidaten zaehlte. Fuer
    genau diese Folge — ein abgelehnter Primaerkandidat, ein abgelehnter
    Reservekandidat, ein erfolgreicher Reservekandidat — ergab das eine
    rechnerisch unmoegliche Bilanz (mehr Ablehnungen als Angetretene).
    """
    caplog.set_level(logging.INFO, logger="agora.oasis_profile")

    gen = _make_generator()
    monkeypatch.setattr(
        OasisProfileGenerator,
        "generate_profile_from_entity",
        _stub_generate_profile_from_entity({"Primär GmbH", "Reserve A"}),
    )

    entities = [_entity("Primär GmbH", "Organization")]
    reserve_entities = [
        _entity("Reserve A", "Organization"),
        _entity("Reserve B", "Organization"),
    ]

    profiles = gen.generate_profiles_from_entities(
        entities,
        use_llm=False,
        parallel_count=1,
        reserve_entities=reserve_entities,
    )

    # Der Slot wird aus der Reserve nachbesetzt.
    assert [p.name for p in profiles] == ["Reserve B"]

    summary = [
        r.getMessage()
        for r in caplog.records
        if r.name == "agora.oasis_profile" and "Persona generation complete" in r.getMessage()
    ]
    assert len(summary) == 1

    # Die Bilanz muss immer aufgehen: angetreten == abgelehnt + erzeugt.
    match = re.search(
        r"(\d+) Kandidat\(en\) angetreten, (\d+) abgelehnt, (\d+) Personas erzeugt",
        summary[0],
    )
    assert match is not None, summary[0]
    attempted, rejected_count, generated = (int(g) for g in match.groups())
    assert attempted == rejected_count + generated

    # Konkret fuer diese Konstellation: 1 Primaer- + 1 Reserve-Ablehnung,
    # 1 erfolgreicher Nachruecker, also 3 Angetretene.
    assert attempted == 3
    assert rejected_count == 2
    assert generated == 1
