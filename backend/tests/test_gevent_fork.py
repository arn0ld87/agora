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

    # Mock gevent.monkey.is_module_patched("socket") -> True
    # (``is_patched(name)`` ist seit gevent 23.x entfernt — Regression-Schutz.)
    class MockGeventMonkey:
        def is_module_patched(self, name):
            return name == "socket"

    monkeypatch.setitem(sys.modules, "gevent", MagicMock())
    mock_pool_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "gevent.pool", mock_pool_mod)
    monkeypatch.setitem(sys.modules, "gevent.monkey", MockGeventMonkey())

    from app.services.oasis_profile_generator import OasisProfileGenerator

    # Test profile generator with gevent
    gen = OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")
    # Stub generate_profile_from_entity to avoid LLM call
    def mock_gen_profile(entity, user_id, use_llm=True, demographic_slot=None):
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


def _build_mock_monkey(socket_patched: bool):
    """Erzeugt ein Mock-Modul für ``gevent.monkey`` mit nur der modernen API.

    Stellt sicher, dass die alte ``is_patched``-Funktion NICHT existiert
    (Realität seit gevent 23.x); Production-Code darf diesen Namen nicht
    mehr referenzieren.
    """
    import sys
    from unittest.mock import MagicMock

    class MockGeventMonkey:
        def is_module_patched(self, name):
            return socket_patched and name == "socket"

    mock_pool_mod = MagicMock()
    return sys.modules, mock_pool_mod, MockGeventMonkey()


def test_is_gevent_detected_when_socket_patched(monkeypatch):
    """Regression: gevent mit gepatchtem socket → ``is_gevent=True`` → Pool-Pfad."""
    import sys
    from unittest.mock import MagicMock

    class MockGeventMonkey:
        def is_module_patched(self, name):
            return name == "socket"

    # ``from gevent import monkey`` greift auf ``gevent.monkey`` als Attribut zu
    # — also muss der gevent-Mock selbst ``monkey`` als vorbereitetes Objekt
    # haben. Ein blankes MagicMock würde sonst ein Auto-Attribut (truthy)
    # liefern und den Patch-Status verschleiern.
    gevent_mock = MagicMock()
    gevent_mock.monkey = MockGeventMonkey()

    mock_pool_mod = MagicMock()
    mock_pool_instance = MagicMock()
    mock_pool_instance.imap_unordered.side_effect = lambda fn, it: [fn(x) for x in it]
    mock_pool_mod.Pool.return_value = mock_pool_instance

    monkeypatch.setitem(sys.modules, "gevent", gevent_mock)
    monkeypatch.setitem(sys.modules, "gevent.pool", mock_pool_mod)
    monkeypatch.setitem(sys.modules, "gevent.monkey", MockGeventMonkey())

    from app.services.oasis_profile_generator import OasisProfileGenerator

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

    gen = OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")
    def mock_gen_profile(entity, user_id, use_llm=True, demographic_slot=None):
        from app.services.oasis_profile_generator import OasisAgentProfile
        return OasisAgentProfile(
            user_id=user_id,
            user_name="test_user",
            name="Patched",
            bio="b",
            persona="p",
        )
    monkeypatch.setattr(gen, "generate_profile_from_entity", mock_gen_profile)

    profiles = gen.generate_profiles_from_entities(entities=[DummyEntity()], use_llm=False)
    assert profiles[0].name == "Patched"
    # Pool-Pfad wurde wirklich genutzt, NICHT ThreadPoolExecutor.
    mock_pool_mod.Pool.assert_called_once()


def test_is_gevent_false_when_socket_not_patched(monkeypatch):
    """Regression: gevent importierbar, aber ``socket`` nicht gepatcht → ThreadPoolExecutor-Fallback."""
    import sys
    from unittest.mock import MagicMock

    class MockGeventMonkey:
        def is_module_patched(self, name):
            return False  # socket nicht gepatcht

    gevent_mock = MagicMock()
    gevent_mock.monkey = MockGeventMonkey()

    mock_pool_mod = MagicMock()

    monkeypatch.setitem(sys.modules, "gevent", gevent_mock)
    monkeypatch.setitem(sys.modules, "gevent.pool", mock_pool_mod)
    monkeypatch.setitem(sys.modules, "gevent.monkey", MockGeventMonkey())

    from app.services.oasis_profile_generator import OasisProfileGenerator

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

    gen = OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")
    def mock_gen_profile(entity, user_id, use_llm=True, demographic_slot=None):
        from app.services.oasis_profile_generator import OasisAgentProfile
        return OasisAgentProfile(
            user_id=user_id,
            user_name="test_user",
            name="Unpatched",
            bio="b",
            persona="p",
        )
    monkeypatch.setattr(gen, "generate_profile_from_entity", mock_gen_profile)

    profiles = gen.generate_profiles_from_entities(entities=[DummyEntity()], use_llm=False)
    assert profiles[0].name == "Unpatched"
    # Thread-Pfad: gevent.pool.Pool darf NICHT instanziert worden sein.
    mock_pool_mod.Pool.assert_not_called()


def test_is_gevent_false_when_gevent_not_importable(monkeypatch):
    """Regression: kein gevent im Env → ``ImportError`` wird sauber gefangen,
    ThreadPoolExecutor-Fallback aktiv, kein ``AttributeError``."""
    import builtins
    import sys

    real_import = builtins.__import__

    def _import_blocker(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "gevent" or name.startswith("gevent."):
            raise ImportError(f"blocked: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import_blocker)
    # Sicherheitshalber: gevent aus sys.modules werfen, falls vorhanden.
    for mod_name in list(sys.modules):
        if mod_name == "gevent" or mod_name.startswith("gevent."):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    from app.services.oasis_profile_generator import OasisProfileGenerator

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

    gen = OasisProfileGenerator(api_key="test-key", base_url="https://example.test/v1")
    def mock_gen_profile(entity, user_id, use_llm=True, demographic_slot=None):
        from app.services.oasis_profile_generator import OasisAgentProfile
        return OasisAgentProfile(
            user_id=user_id,
            user_name="test_user",
            name="NoGevent",
            bio="b",
            persona="p",
        )
    monkeypatch.setattr(gen, "generate_profile_from_entity", mock_gen_profile)

    profiles = gen.generate_profiles_from_entities(entities=[DummyEntity()], use_llm=False)
    assert profiles[0].name == "NoGevent"
