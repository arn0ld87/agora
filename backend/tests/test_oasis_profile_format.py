"""Serialization tests for OasisAgentProfile.

Guards against regressions where ``source_entity_uuid``/``source_entity_type``
get dropped during JSON serialization, which downstream causes
``missing_entity_link`` quality findings for every auto-generated persona.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.oasis_profile_generator import (
    OasisAgentProfile,
    OasisProfileGenerator,
)
from app.services.entity_reader import EntityNode


def _profile(**overrides):
    base = dict(
        user_id=1,
        user_name="alice",
        name="Alice",
        bio="bio",
        persona="persona",
        source_entity_uuid="uuid-123",
        source_entity_type="Person",
    )
    base.update(overrides)
    return OasisAgentProfile(**base)


def test_to_reddit_format_includes_entity_link():
    out = _profile().to_reddit_format()
    assert out["source_entity_uuid"] == "uuid-123"
    assert out["source_entity_type"] == "Person"


def test_to_twitter_format_includes_entity_link():
    out = _profile().to_twitter_format()
    assert out["source_entity_uuid"] == "uuid-123"
    assert out["source_entity_type"] == "Person"


def test_reddit_format_omits_entity_link_when_unset():
    out = _profile(source_entity_uuid=None, source_entity_type=None).to_reddit_format()
    assert "source_entity_uuid" not in out
    assert "source_entity_type" not in out


def test_twitter_format_omits_entity_link_when_unset():
    out = _profile(source_entity_uuid=None, source_entity_type=None).to_twitter_format()
    assert "source_entity_uuid" not in out
    assert "source_entity_type" not in out


def test_save_reddit_json_persists_entity_link(tmp_path):
    gen = OasisProfileGenerator.__new__(OasisProfileGenerator)
    profiles = [_profile(), _profile(user_id=2, user_name="bob",
                                     source_entity_uuid=None,
                                     source_entity_type=None)]
    out_path = tmp_path / "reddit_profiles.json"
    gen._save_reddit_json(profiles, str(out_path))

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data[0]["source_entity_uuid"] == "uuid-123"
    assert data[0]["source_entity_type"] == "Person"
    assert "source_entity_uuid" not in data[1]
    assert "source_entity_type" not in data[1]


def _fake_llm_response(payload):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(payload)),
                finish_reason="stop",
            )
        ]
    )


def test_generate_profile_with_llm_retries_when_required_metadata_missing():
    gen = OasisProfileGenerator.__new__(OasisProfileGenerator)
    gen.model_name = "test-model"
    gen.base_url = None
    gen.language = "de"
    gen._build_individual_persona_prompt = lambda *args, **kwargs: "prompt"
    gen._get_system_prompt = lambda is_individual: "system"
    gen._is_individual_entity = lambda entity_type: True
    gen._generate_profile_rule_based = lambda *args, **kwargs: {
        "display_name": "Fallback Name",
        "handle": "fallback_name",
        "bio": "Fallback",
        "persona": "Fallback Persona",
        "age": 41,
        "gender": "female",
        "mbti": "INTJ",
        "country": "DE",
    }

    responses = iter([
        _fake_llm_response({
            "display_name": "Felix Weber",
            "handle": "felix_weber",
            "bio": "Bio",
            "persona": "Persona mit ENTP und 48 Jahre.",
        }),
        _fake_llm_response({
            "display_name": "Mara Scholz",
            "handle": "mara_scholz",
            "bio": "Bio",
            "persona": "Persona mit konsistenten Feldern.",
            "age": 48,
            "gender": "female",
            "mbti": "ENTP",
            "country": "DE",
        }),
    ])
    gen.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: next(responses))
        )
    )

    result = gen._generate_profile_with_llm("Entity", "Person", "Summary", {}, "")

    assert result["display_name"] == "Mara Scholz"
    assert result["age"] == 48
    assert result["gender"] == "female"
    assert result["mbti"] == "ENTP"
    assert result["country"] == "DE"


def test_generate_profile_with_llm_falls_back_with_complete_metadata():
    gen = OasisProfileGenerator.__new__(OasisProfileGenerator)
    gen.model_name = "test-model"
    gen.base_url = None
    gen.language = "de"
    gen._build_individual_persona_prompt = lambda *args, **kwargs: "prompt"
    gen._get_system_prompt = lambda is_individual: "system"
    gen._is_individual_entity = lambda entity_type: True
    gen._generate_profile_rule_based = lambda *args, **kwargs: {
        "display_name": "Fallback Name",
        "handle": "fallback_name",
        "bio": "Fallback",
        "persona": "Fallback Persona",
        "age": 41,
        "gender": "female",
        "mbti": "INTJ",
        "country": "DE",
    }
    gen.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: _fake_llm_response({
                    "bio": "Bio",
                    "persona": "Persona ohne strukturierte Pflichtfelder.",
                })
            )
        )
    )

    result = gen._generate_profile_with_llm("Entity", "Person", "Summary", {}, "")

    assert result["age"] == 41
    assert result["gender"] == "female"
    assert result["mbti"] == "INTJ"
    assert result["country"] == "DE"


def test_generate_profiles_replaces_duplicate_last_names(monkeypatch):
    gen = OasisProfileGenerator.__new__(OasisProfileGenerator)
    gen.graph_id = None
    gen._print_generated_profile = lambda *args, **kwargs: None
    picked_names = iter(["Mara Scholz", "Jonas Becker", "Lea Hoffmann"])
    gen._pick_dach_name = lambda: next(picked_names)
    gen._generate_username = lambda name: name.lower().replace(" ", "_")

    def fake_generate(entity, user_id, use_llm=True):
        return OasisAgentProfile(
            user_id=user_id,
            user_name=f"user_{user_id}",
            name=["Felix Weber", "Anna Weber", "Markus Weber"][user_id],
            bio="Bio",
            persona="Persona",
            age=40 + user_id,
            gender="male",
            mbti="INTJ",
            country="DE",
        )

    gen.generate_profile_from_entity = fake_generate
    entities = [
        EntityNode(str(idx), f"Entity {idx}", ["Entity", "Person"], "Summary", {})
        for idx in range(3)
    ]

    profiles = gen.generate_profiles_from_entities(
        entities,
        use_llm=True,
        parallel_count=1,
    )

    last_names = [profile.name.split()[-1] for profile in profiles]
    assert len(last_names) == len(set(last_names))
