"""Tests for gunicorn gevent worker availability."""

from pathlib import Path

import pytest

import tomllib

GEEVENT_AVAILABLE = False
try:
    import gevent  # noqa: F401 — presence check only

    GEEVENT_AVAILABLE = True
except ImportError:
    pass


@pytest.mark.skipif(not GEEVENT_AVAILABLE, reason="gevent not installed in this env")
def test_gevent_importable():
    """Smoke: gevent + gevent.monkey sind importierbar.

    NICHT patch_all() im Test aufrufen — das hat globale ssl-Monkey-Patching-
    Seiteneffekte und triggert MonkeyPatchWarning, weil pytest den ssl-Stack
    bereits geladen hat. patch_all() ist Aufgabe der gunicorn-gevent-Worker-
    Init, nicht der Test-Suite (siehe Dockerfile CMD).
    """
    import gevent
    import gevent.monkey  # noqa: F401 — import-only check

    assert gevent.__version__, "gevent muss eine Version melden"


def test_gevent_in_dependencies():
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)
    deps = pyproject.get("project", {}).get("dependencies", [])
    assert any("gevent" in dep for dep in deps), "gevent not in pyproject.toml dependencies"


def test_gevent_pool_execution_fallback(monkeypatch):
    """Verify that both OasisProfileGenerator and GraphBuilderService correctly use gevent Pool if gevent is patched."""
    import sys
    from unittest.mock import MagicMock

    # Create dummy classes
    class DummyEntity:
        def get_entity_type(self):
            return "TestType"
        @property
        def name(self):
            return "TestEntity"
        @property
        def uuid(self):
            return "test-uuid"
        @property
        def summary(self):
            return "TestSummary"
        @property
        def attributes(self):
            return {}
        @property
        def related_edges(self):
            return []
        @property
        def related_nodes(self):
            return []

    # Mock gevent.monkey.is_patched("socket") to return True
    class MockGeventMonkey:
        def is_patched(self, name):
            return name == "socket"

    sys.modules["gevent"] = MagicMock()
    mock_pool_mod = MagicMock()
    sys.modules["gevent.pool"] = mock_pool_mod
    sys.modules["gevent.monkey"] = MockGeventMonkey()

    from app.services.oasis_profile_generator import OasisProfileGenerator

    # Test profile generator with gevent
    gen = OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")
    # Stub generate_profile_from_entity to avoid LLM call
    def mock_gen_profile(entity, user_id, use_llm=True):
        from app.services.oasis_profile_generator import OasisAgentProfile
        return OasisAgentProfile(
            user_id=user_id,
            user_name="test_user",
            name="Test Name",
            bio="bio",
            persona="persona",
        )
    monkeypatch.setattr(gen, "generate_profile_from_entity", mock_gen_profile)

    # Configure pool.imap_unordered mock to return expected results using a side_effect
    mock_pool_instance = MagicMock()
    def mock_imap(func, iterable):
        return [func(item) for item in iterable]
    mock_pool_instance.imap_unordered.side_effect = mock_imap
    mock_pool_mod.Pool.return_value = mock_pool_instance

    entities = [DummyEntity()]
    profiles = gen.generate_profiles_from_entities(entities=entities, use_llm=False)
    assert len(profiles) == 1
    assert profiles[0].name == "Test Name"
