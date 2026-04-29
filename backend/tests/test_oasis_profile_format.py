"""Serialization tests for OasisAgentProfile.

Guards against regressions where ``source_entity_uuid``/``source_entity_type``
get dropped during JSON serialization, which downstream causes
``missing_entity_link`` quality findings for every auto-generated persona.
"""

from __future__ import annotations

from app.services.oasis_profile_generator import OasisAgentProfile


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
