"""#1759 C4: ohne ``project_name`` heißt das Projekt nach dem ersten Dokument."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.graph_build import _default_project_name


def _files(*names: str) -> list:
    return [SimpleNamespace(filename=name) for name in names]


def test_explicit_name_wins():
    assert _default_project_name("  Klinikreform  ", _files("a.pdf")) == "Klinikreform"


def test_missing_name_uses_first_document_stem():
    assert _default_project_name(None, _files("Gesetzentwurf_Krankenhaus.pdf", "b.md")) == (
        "Gesetzentwurf_Krankenhaus"
    )


def test_blank_name_skips_files_without_filename():
    assert _default_project_name("   ", _files("", "notiz.txt")) == "notiz"


def test_path_components_are_stripped():
    assert _default_project_name("", _files("../../etc/analyse.docx")) == "analyse"


def test_no_name_and_no_files_keeps_placeholder():
    assert _default_project_name(None, _files("")) == "Unnamed Project"
