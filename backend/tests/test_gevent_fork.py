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
