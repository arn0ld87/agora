"""Tests für backend/scripts/check_complexity.py (MAI-17 / #1084).

Deckt das erweiterte Allowlist-Format ab: eine optionale cc-Obergrenze je
Eintrag (`<key>  # cc<=<N>`), rückwärtskompatibel zum reinen
Duldungs-Schlüssel ohne Obergrenze.

Tests sind subprocess-frei für die Parsing-Logik (load_allowlist) und
monkeypatchen subprocess.run für main(), um radon-Output zu simulieren.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "check_complexity.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_complexity", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


# ---------------------------------------------------------------------------
# load_allowlist — Parsing des erweiterten Formats
# ---------------------------------------------------------------------------


class TestLoadAllowlist:
    def test_entry_without_max_cc_behaves_like_before(self, tmp_path, monkeypatch):
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("app/foo.py::bar\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)

        entries = mod.load_allowlist()
        assert entries == {"app/foo.py::bar": None}

    def test_entry_with_max_cc_is_parsed(self, tmp_path, monkeypatch):
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("app/foo.py::bar  # cc<=33\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)

        entries = mod.load_allowlist()
        assert entries == {"app/foo.py::bar": 33}

    def test_comment_line_is_ignored(self, tmp_path, monkeypatch):
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("# nur ein Kommentar\napp/foo.py::bar\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)

        entries = mod.load_allowlist()
        assert entries == {"app/foo.py::bar": None}

    def test_blank_line_is_ignored(self, tmp_path, monkeypatch):
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("\n   \napp/foo.py::bar\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)

        entries = mod.load_allowlist()
        assert entries == {"app/foo.py::bar": None}

    def test_broken_max_cc_value_falls_back_to_none(self, tmp_path, monkeypatch):
        """Ein nicht-parsebarer Wert darf das Gate nicht crashen lassen."""
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("app/foo.py::bar  # cc<=abc\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)

        entries = mod.load_allowlist()
        assert entries == {"app/foo.py::bar": None}


# ---------------------------------------------------------------------------
# main() — Gate-Verhalten mit simuliertem radon-Output
# ---------------------------------------------------------------------------


def _radon_json(name: str, path: str, complexity: int, rank: str = "D") -> str:
    import json as _json

    return _json.dumps(
        {
            path: [
                {
                    "name": name,
                    "lineno": 1,
                    "complexity": complexity,
                    "rank": rank,
                    "classname": "",
                }
            ]
        }
    )


class TestMainWithAllowlistCeiling:
    def test_entry_without_ceiling_is_still_tolerated(self, tmp_path, monkeypatch, capsys):
        """(a) Ohne Obergrenze bleibt jede Komplexität geduldet — unverändert."""
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("app/foo.py::bar\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *a, **kw: _FakeCompletedProcess(
                _radon_json("bar", "app/foo.py", complexity=99, rank="F")
            ),
        )

        assert mod.main() == 0
        assert "OK:" in capsys.readouterr().out

    def test_entry_over_ceiling_fails_gate(self, tmp_path, monkeypatch, capsys):
        """(b) Mit Obergrenze failt das Gate bei Überschreitung."""
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("app/foo.py::bar  # cc<=21\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *a, **kw: _FakeCompletedProcess(
                _radon_json("bar", "app/foo.py", complexity=30, rank="D")
            ),
        )

        assert mod.main() == 1
        err = capsys.readouterr().err
        assert "cc<=21" in err
        assert "complexity=30" in err

    def test_entry_within_ceiling_passes(self, tmp_path, monkeypatch, capsys):
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("app/foo.py::bar  # cc<=33\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *a, **kw: _FakeCompletedProcess(
                _radon_json("bar", "app/foo.py", complexity=33, rank="D")
            ),
        )

        assert mod.main() == 0
        assert "OK:" in capsys.readouterr().out

    def test_entry_below_ceiling_emits_notice_but_does_not_fail(
        self, tmp_path, monkeypatch, capsys
    ):
        mod = _load_script()
        allowlist = tmp_path / "radon-allowlist.txt"
        allowlist.write_text("app/foo.py::bar  # cc<=33\n")
        monkeypatch.setattr(mod, "ALLOWLIST", allowlist)
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *a, **kw: _FakeCompletedProcess(
                _radon_json("bar", "app/foo.py", complexity=25, rank="D")
            ),
        )

        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "Hinweis" in out
        assert "cc<=33" in out
