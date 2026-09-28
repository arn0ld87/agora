"""SEC-1 / #1669 Slice B: CodeQL py/path-injection in der SPA-Catch-all-Route.

``app._resolve_spa_static_file`` ist der isolierte Fixpunkt fuer
``app/__init__.py:create_app().serve_spa`` (Alert #7,
``backend/app/__init__.py:623`` auf ``origin/main`` @ ``9eb20a931``): der rohe
``frontend_dist / path`` + ``.is_file()``-Check vor ``send_from_directory``
liest den Dateisystem-Zustand ausserhalb der SPA-Wurzel, bevor Werkzeugs
eigene Containment-Pruefung greift. Diese Suite fixiert, dass ein
Escape-Versuch wie ein fehlendes Dateisystem-Objekt behandelt wird (``None``)
und legitime, verschachtelte Client-Routen unveraendert aufgeloest werden.
"""

from __future__ import annotations

import pytest

from app import _resolve_spa_static_file


@pytest.fixture
def dist_root(tmp_path):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('x')", encoding="utf-8")
    # Datei ausserhalb der SPA-Wurzel, deren Existenz ein Traversal-Versuch
    # nicht ueber ein anderes Antwortverhalten verraten darf.
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "../../secret.txt",
        "a/../../secret.txt",
        "..",
    ],
)
def test_resolve_spa_static_file_rejects_traversal(dist_root, path):
    assert _resolve_spa_static_file(dist_root, path) is None


def test_resolve_spa_static_file_rejects_absolute_part(dist_root, tmp_path):
    outside = tmp_path / "secret.txt"
    assert _resolve_spa_static_file(dist_root, str(outside)) is None


def test_resolve_spa_static_file_resolves_nested_asset(dist_root):
    target = _resolve_spa_static_file(dist_root, "assets/app.js")
    assert target is not None
    assert target.endswith("assets/app.js")


def test_resolve_spa_static_file_returns_none_for_missing_file(dist_root):
    # Client-Route ohne Datei-Gegenstueck -> SPA-Fallback (index.html), kein
    # Fehler.
    assert _resolve_spa_static_file(dist_root, "some/client/route") is None


def test_resolve_spa_static_file_returns_none_for_empty_path(dist_root):
    assert _resolve_spa_static_file(dist_root, "") is None
