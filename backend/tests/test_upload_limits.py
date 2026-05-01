"""
Upload-Hardening-Regression (Slice 12, F5 of repo review).

Pins the documented behaviour of the upload pipeline:

* ``app.api.graph.allowed_file`` filters by extension AND PDF magic bytes.
* ``app.config.Config.MAX_CONTENT_LENGTH`` is the hard upload cap (50 MB).
* ``ProjectManager.save_file_to_project`` runs ``secure_filename`` plus a
  defensive prefix-check so path-traversal filenames never escape the
  projects directory.

The tests target the public surface — ``allowed_file`` for content checks and
the actual save method (with a temp directory) for traversal — instead of
hitting the Flask blueprint, so they remain stable against route refactors.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app.api.graph import allowed_file
from app.config import Config
from app.models.project import ProjectManager


def _file_storage(filename: str, body: bytes) -> FileStorage:
    return FileStorage(stream=io.BytesIO(body), filename=filename)


# ── Extension / magic-byte gate ─────────────────────────────────────────────


def test_allowed_extensions_are_locked():
    """The whitelist exists and matches what the doc promises."""
    assert Config.ALLOWED_EXTENSIONS == {"pdf", "md", "txt", "markdown"}


def test_rejects_unknown_extension():
    """``.exe`` (or any extension not on the whitelist) is rejected."""
    fs = _file_storage("malware.exe", b"MZ\x90\x00")
    assert allowed_file(fs) is False


def test_rejects_pdf_without_magic_header():
    """A file claiming ``.pdf`` but missing the ``%PDF`` magic is rejected."""
    fs = _file_storage("notreally.pdf", b"<html>not a pdf</html>")
    assert allowed_file(fs) is False


def test_accepts_real_pdf_header():
    """A minimal PDF magic header passes the content check."""
    fs = _file_storage("doc.pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    assert allowed_file(fs) is True


def test_accepts_text_extensions_without_magic():
    """``.md`` / ``.txt`` / ``.markdown`` skip the magic-byte gate."""
    for fname in ("doc.md", "notes.txt", "doc.markdown"):
        fs = _file_storage(fname, b"plain content\n")
        assert allowed_file(fs) is True, fname


def test_rejects_missing_filename():
    """Empty ``filename`` short-circuits before any further check."""
    fs = FileStorage(stream=io.BytesIO(b""), filename="")
    assert allowed_file(fs) is False


def test_rejects_filename_without_extension():
    """No extension, no upload."""
    fs = _file_storage("README", b"plain")
    assert allowed_file(fs) is False


# ── Size cap ─────────────────────────────────────────────────────────────────


def test_max_content_length_is_50_mb():
    """``Config.MAX_CONTENT_LENGTH`` matches the 50 MB the docs promise."""
    assert Config.MAX_CONTENT_LENGTH == 50 * 1024 * 1024


# ── Path-traversal hardening ────────────────────────────────────────────────


def _fresh_projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point ``ProjectManager.PROJECTS_DIR`` at an isolated tmp tree."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    return projects_dir


def test_save_file_to_project_strips_path_traversal_filename(tmp_path, monkeypatch):
    """``../../etc/passwd`` is normalised by ``secure_filename`` and saved
    under a UUID — the traversal segments never reach the FS."""
    projects_dir = _fresh_projects_dir(tmp_path, monkeypatch)
    project = ProjectManager.create_project(name="traversal-test")

    fs = _file_storage("../../etc/passwd", b"root:x:0:0:root:/root:/bin/bash\n")
    info = ProjectManager.save_file_to_project(project.project_id, fs, "../../etc/passwd")

    saved = Path(info["path"])
    # File must live inside the projects dir.
    assert str(saved).startswith(str(projects_dir.resolve())), saved
    # The saved filename is a UUID + extension, never the traversal payload.
    assert "etc" not in saved.name and "passwd" not in saved.name, saved.name
    assert ".." not in saved.parts


def test_save_file_to_project_rejects_invalid_project_id(tmp_path, monkeypatch):
    """Path-traversal in ``project_id`` is rejected before any disk write."""
    _fresh_projects_dir(tmp_path, monkeypatch)
    fs = _file_storage("doc.txt", b"plain")

    with pytest.raises(ValueError):
        ProjectManager.save_file_to_project("../escape", fs, "doc.txt")
