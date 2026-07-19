"""
Tests for backend/scripts/check_version_drift.py.

Covers the happy path (all sources agree on the canonical VERSION file),
drift detection (any manifest out of sync with VERSION), and the
``--write`` synchronization mode (including idempotency).
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


def _scaffold_repo(
    tmp_path: Path,
    *,
    version_file: str,
    pyproject_ver: str,
    pkg_json_ver: str,
    frontend_pkg_json_ver: str,
    readme_badge_ver: str | None = None,
) -> None:
    """Build a minimal fake repo tree with all version-bearing files."""
    (tmp_path / "VERSION").write_text(f"{version_file}\n")

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "pyproject.toml").write_text(
        f'[project]\nname = "agora-backend"\nversion = "{pyproject_ver}"\n'
    )

    (tmp_path / "package.json").write_text(
        json.dumps({"name": "agora", "version": pkg_json_ver}, indent=2) + "\n"
    )

    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text(
        json.dumps({"name": "frontend", "version": frontend_pkg_json_ver}, indent=2) + "\n"
    )

    if readme_badge_ver is not None:
        (tmp_path / "README.md").write_text(
            "[![Version](https://img.shields.io/badge/Version-"
            f"{readme_badge_ver}-brightgreen?style=flat-square)](./VERSION)\n"
        )
    else:
        (tmp_path / "README.md").write_text("# Agora\n")


class TestReadVersionFile:
    def test_reads_current_version(self, tmp_path):
        mod = _load_script()
        (tmp_path / "VERSION").write_text("0.8.0\n")
        assert mod.read_version_file(tmp_path) == "0.8.0"

    def test_raises_when_empty(self, tmp_path):
        mod = _load_script()
        (tmp_path / "VERSION").write_text("   \n")
        with pytest.raises(ValueError, match="VERSION file is empty"):
            mod.read_version_file(tmp_path)

    @pytest.mark.parametrize("bad", ["1.0", "v1.0.0", "0.8", "abc", "1.0.0.0"])
    def test_raises_on_invalid_semver(self, tmp_path, bad):
        mod = _load_script()
        (tmp_path / "VERSION").write_text(f"{bad}\n")
        with pytest.raises(ValueError, match="not a valid SemVer"):
            mod.read_version_file(tmp_path)

    @pytest.mark.parametrize(
        "bad",
        [
            "01.2.3",  # leading zero in MAJOR
            "1.02.3",  # leading zero in MINOR
            "1.2.03",  # leading zero in PATCH
            "1.2.3-01",  # leading zero in numeric prerelease identifier
            "1.2.3-..",  # empty prerelease identifier segments
            "1.2.3-alpha..1",  # empty prerelease identifier segment in middle
            "1.2.3+..",  # empty build identifier segments
            "1.2.3-",  # trailing dash with nothing after
            "1.2.3+",  # trailing plus with nothing after
            "١.2.3",  # Unicode digit (Arabic-indic) in MAJOR
        ],
    )
    def test_rejects_non_canonical_semver(self, tmp_path, bad):
        """Canonical SemVer regex rejects leading zeroes, empty identifiers, Unicode digits."""
        mod = _load_script()
        (tmp_path / "VERSION").write_text(f"{bad}\n")
        with pytest.raises(ValueError, match="not a valid SemVer"):
            mod.read_version_file(tmp_path)

    @pytest.mark.parametrize("good", ["0.8.0", "1.2.3", "0.8.0-rc.1", "1.0.0+build.5"])
    def test_accepts_valid_semver(self, tmp_path, good):
        mod = _load_script()
        (tmp_path / "VERSION").write_text(f"{good}\n")
        assert mod.read_version_file(tmp_path) == good


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


class TestReadFrontendPackageJsonVersion:
    def test_reads_version(self, tmp_path):
        mod = _load_script()
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "package.json").write_text(json.dumps({"version": "0.8.0"}))
        assert mod.read_frontend_package_json_version(tmp_path) == "0.8.0"


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
    def test_returns_0_when_all_agree(self, tmp_path, monkeypatch):
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="0.8.0",
            pkg_json_ver="0.8.0",
            frontend_pkg_json_ver="0.8.0",
        )

        # Patch _repo_root() to point at our tmp tree.
        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)
        # Patch read_init_version to return matching string without importing app.
        monkeypatch.setattr(mod, "read_init_version", lambda root: "0.8.0")

        assert mod.main([]) == 0

    def test_returns_1_when_package_json_drifts(self, tmp_path, monkeypatch):
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="0.8.0",
            pkg_json_ver="0.9.0",
            frontend_pkg_json_ver="0.8.0",
        )

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "read_init_version", lambda root: "0.8.0")

        assert mod.main([]) == 1

    def test_returns_1_when_pyproject_drifts(self, tmp_path, monkeypatch):
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="0.7.0",
            pkg_json_ver="0.8.0",
            frontend_pkg_json_ver="0.8.0",
        )

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "read_init_version", lambda root: "0.8.0")

        assert mod.main([]) == 1

    def test_returns_1_when_frontend_package_json_drifts(self, tmp_path, monkeypatch):
        """frontend/package.json is part of the drift check."""
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="0.8.0",
            pkg_json_ver="0.8.0",
            frontend_pkg_json_ver="0.5.0",
        )

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "read_init_version", lambda root: "0.8.0")

        assert mod.main([]) == 1

    def test_live_repo_is_consistent(self):
        """Smoke-test against the actual repository — all sources must agree."""
        mod = _load_script()
        result = mod.main([])
        assert result == 0, (
            "Version drift detected in the actual repo. "
            "Run `python backend/scripts/check_version_drift.py` for details."
        )


class TestWriteMode:
    def test_write_synchronizes_all_sources(self, tmp_path, monkeypatch):
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="1.0.0",
            pkg_json_ver="1.0.0",
            frontend_pkg_json_ver="1.0.0",
            readme_badge_ver="1.0.0",
        )

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)

        assert mod.main(["--write"]) == 0

        assert mod.read_pyproject_version(tmp_path) == "0.8.0"
        assert mod.read_package_json_version(tmp_path) == "0.8.0"
        assert mod.read_frontend_package_json_version(tmp_path) == "0.8.0"
        assert mod.read_readme_badge_version(tmp_path) == "0.8.0"

    def test_write_does_not_touch_app_init(self, tmp_path, monkeypatch):
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="1.0.0",
            pkg_json_ver="1.0.0",
            frontend_pkg_json_ver="1.0.0",
        )
        app_dir = tmp_path / "backend" / "app"
        app_dir.mkdir()
        init_content = '__version__ = "unrelated-literal"\n'
        (app_dir / "__init__.py").write_text(init_content)

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)

        assert mod.main(["--write"]) == 0
        assert (app_dir / "__init__.py").read_text() == init_content

    def test_write_is_idempotent(self, tmp_path, monkeypatch):
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="1.0.0",
            pkg_json_ver="1.0.0",
            frontend_pkg_json_ver="1.0.0",
            readme_badge_ver="1.0.0",
        )

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)

        assert mod.main(["--write"]) == 0
        snapshot = {
            "pyproject": (tmp_path / "backend" / "pyproject.toml").read_text(),
            "package_json": (tmp_path / "package.json").read_text(),
            "frontend_package_json": (tmp_path / "frontend" / "package.json").read_text(),
            "readme": (tmp_path / "README.md").read_text(),
        }

        assert mod.main(["--write"]) == 0
        assert (tmp_path / "backend" / "pyproject.toml").read_text() == snapshot["pyproject"]
        assert (tmp_path / "package.json").read_text() == snapshot["package_json"]
        assert (
            tmp_path / "frontend" / "package.json"
        ).read_text() == snapshot["frontend_package_json"]
        assert (tmp_path / "README.md").read_text() == snapshot["readme"]

    def test_write_accepts_fix_alias(self, tmp_path, monkeypatch):
        mod = _load_script()
        _scaffold_repo(
            tmp_path,
            version_file="0.8.0",
            pyproject_ver="1.0.0",
            pkg_json_ver="1.0.0",
            frontend_pkg_json_ver="1.0.0",
        )

        monkeypatch.setattr(mod, "_repo_root", lambda: tmp_path)

        assert mod.main(["--fix"]) == 0
        assert mod.read_pyproject_version(tmp_path) == "0.8.0"
