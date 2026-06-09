"""
Tests for backend/scripts/check_version_drift.py.

Covers the happy path (all sources agree) and drift detection
(package.json out of sync with pyproject.toml).
Tests are subprocess-free: we call the internal helpers directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "check_version_drift.py"


# ---------------------------------------------------------------------------
# Helpers — load the module without importing the full app package
# ---------------------------------------------------------------------------

def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_version_drift", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReadPyprojectVersion:
    def test_reads_current_version(self, tmp_path):
        mod = _load_script()
        # Plant a minimal pyproject.toml in a fake repo root.
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        (backend_dir / "pyproject.toml").write_text(
            '[project]\nname = "agora-backend"\nversion = "1.2.3"\n'
        )
        assert mod.read_pyproject_version(tmp_path) == "1.2.3"

    def test_raises_when_version_missing(self, tmp_path):
        mod = _load_script()
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        (backend_dir / "pyproject.toml").write_text("[project]\nname = \"agora-backend\"\n")
        with pytest.raises(ValueError, match="version not found"):
            mod.read_pyproject_version(tmp_path)


class TestReadPackageJsonVersion:
    def test_reads_version(self, tmp_path):
        mod = _load_script()
        (tmp_path / "package.json").write_text(json.dumps({"version": "1.0.0"}))
        assert mod.read_package_json_version(tmp_path) == "1.0.0"


class TestReadReadmeBadgeVersion:
    def test_returns_none_when_no_badge(self, tmp_path):
        mod = _load_script()
        (tmp_path / "README.md").write_text("# Agora\n\nNo badge here.\n")
        assert mod.read_readme_badge_version(tmp_path) is None

    def test_extracts_version_from_badge(self, tmp_path):
        mod = _load_script()
        readme_content = (
            "[![Version](https://img.shields.io/badge/Version-1.0.0-brightgreen"
            "?style=flat-square)](./CHANGELOG.md)\n"
        )
        (tmp_path / "README.md").write_text(readme_content)
        assert mod.read_readme_badge_version(tmp_path) == "1.0.0"


class TestMain:
    def _make_repo(self, tmp_path: Path, *, pyproject_ver: str, pkg_json_ver: str) -> None:
        """Scaffold the minimal file tree that main() needs."""
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        (backend_dir / "pyproject.toml").write_text(
            f'[project]\nname = "agora-backend"\nversion = "{pyproject_ver}"\n'
        )
        (tmp_path / "package.json").write_text(json.dumps({"version": pkg_json_ver}))
        (tmp_path / "README.md").write_text("# Agora\n")

    def test_returns_0_when_all_agree(self, tmp_path, monkeypatch):
        mod = _load_script()
        self._make_repo(tmp_path, pyproject_ver="1.0.0", pkg_json_ver="1.0.0")

        # Patch _repo_root() to point at our tmp tree.
        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)
        # Patch read_init_version to return matching string without importing app.
        monkeypatch.setattr(mod, "read_init_version", lambda root: "1.0.0")

        assert mod.main() == 0

    def test_returns_1_on_drift(self, tmp_path, monkeypatch):
        mod = _load_script()
        self._make_repo(tmp_path, pyproject_ver="1.0.0", pkg_json_ver="0.9.0")

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "read_init_version", lambda root: "1.0.0")

        assert mod.main() == 1

    def test_live_repo_is_consistent(self):
        """Smoke-test against the actual repository — all sources must agree."""
        mod = _load_script()
        result = mod.main()
        assert result == 0, (
            "Version drift detected in the actual repo. "
            "Run `python backend/scripts/check_version_drift.py` for details."
        )
