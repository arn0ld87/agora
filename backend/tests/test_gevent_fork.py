"""Tests for gunicorn gevent worker availability."""

from pathlib import Path

import pytest

import tomllib

GEEVENT_AVAILABLE = False
try:
    import gevent
    import gevent.monkey
    GEEVENT_AVAILABLE = True
except ImportError:
    pass


@pytest.mark.skipif(not GEEVENT_AVAILABLE, reason="gevent not installed in this env")
def test_gevent_importable():
    # Verify gevent can be imported and monkey-patching works
    import gevent.monkey

    gevent.monkey.patch_all()
    assert gevent.monkey.is_module_patched("socket")


def test_gevent_in_dependencies():
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)
    deps = pyproject.get("project", {}).get("dependencies", [])
    assert any("gevent" in dep for dep in deps), "gevent not in pyproject.toml dependencies"
