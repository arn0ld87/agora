"""Serialization tests for OasisAgentProfile.

Guards against regressions where ``source_entity_uuid``/``source_entity_type``
get dropped during JSON serialization, which downstream causes
``missing_entity_link`` quality findings for every auto-generated persona.
"""

from __future__ import annotations

from collections import Counter
import json
from types import SimpleNamespace
from unittest.mock import patch

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


def test_reddit_format_always_writes_age_gender_mbti_keys_for_collective():
    """Seit #1246 fehlen bei Kollektiv-Personas die Schluessel ``age``,
    ``gender`` und ``mbti`` in ``reddit_profiles.json`` ganz, weil
    ``to_reddit_format()`` sie bei ``None`` vollstaendig ausliess statt nur
    den Wert wegzulassen. OASIS greift in agents_generator.py::process_agent
    ungeschuetzt auf agent_info[i]["mbti"]/["gender"]/["age"] zu. Fehlt der
    Schluessel (statt nur der Wert), reisst der Reddit-Zweig mit KeyError ab —
    und weil beide Plattformen ueber ein gemeinsames asyncio.gather laufen,
    den ganzen Subprozess mit.

    Kollektiv-Personas duerfen aber weiterhin keine erfundene Demografie
    tragen (#1246) — der Wert ist deshalb der Leerstring, nicht ``None``.
    """
    out = _profile(
        persona_kind="collective",
        age=None,
        gender=None,
        mbti=None,
    ).to_reddit_format()

    assert "age" in out
    assert "gender" in out
    assert "mbti" in out
    assert out["age"] == ""
    assert out["gender"] == ""
    assert out["mbti"] == ""


def test_reddit_format_keeps_real_values_for_individual():
    """Gegenprobe: eine individuelle Persona behaelt ihre echte Demografie."""
    out = _profile(
        persona_kind="individual",
        age=47,
        gender="female",
        mbti="INTJ",
    ).to_reddit_format()

    assert out["age"] == 47
    assert out["gender"] == "female"
    assert out["mbti"] == "INTJ"


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


def test_generate_profiles_replaces_duplicate_last_names(monkeypatch):
    gen = OasisProfileGenerator.__new__(OasisProfileGenerator)
    gen.graph_id = None
    gen._print_generated_profile = lambda *args, **kwargs: None
    picked_names = iter(["Mara Scholz", "Jonas Becker", "Lea Hoffmann"])
    picked_genders = []
    gen._pick_dach_name = lambda gender=None: picked_genders.append(gender) or next(picked_names)
    gen._generate_username = lambda name: name.lower().replace(" ", "_")

    def fake_generate(entity, user_id, use_llm=True, demographic_slot=None):
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
    assert picked_genders == ["male", "male"]


def test_generate_profiles_rebalances_demographics_when_llm_returns_single_mode(monkeypatch):
    payload = {
        "display_name": "Lena Hoffmann",
        "handle": "lena_hoffmann",
        "bio": "Mobilitätsberaterin aus München.",
        "persona": "Ausführliche Personenbeschreibung.",
        "age": 52,
        "gender": "female",
        "mbti": "ISTJ",
        "country": "DE",
        "profession": "Verkehrsplanerin",
        "interested_topics": ["Mobilität"],
        "voice_register": "neutral-de",
    }

    class _LLMStub:
        def __init__(self, *args, **kwargs):
            pass

        def chat_json(self, **kwargs):
            return dict(payload)

    with patch("app.services.oasis_profile_generator.OpenAI"), \
            patch("app.llm.client.LLMClient", _LLMStub):
        gen = OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")
        gen.graph_id = None
        gen._print_generated_profile = lambda *args, **kwargs: None

        entities = [
            EntityNode(str(idx), f"Entity {idx}", ["Entity", "Person"], "Summary", {})
            for idx in range(30)
        ]

        profiles = gen.generate_profiles_from_entities(
            entities,
            use_llm=True,
            parallel_count=1,
        )

    mbti_counts = Counter(profile.mbti for profile in profiles)
    age_counts = Counter(profile.age for profile in profiles)
    gender_counts = Counter(profile.gender for profile in profiles)

    assert max(mbti_counts.values()) <= 9
    assert max(age_counts.values()) <= 4
    assert max(gender_counts.values()) < 30
    assert len(gender_counts) >= 2
