"""Tests fuer backend/scripts/select_pr_tests.py (CI-PR-Test-Splitting)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import select_pr_tests  # noqa: E402
from select_pr_tests import (  # noqa: E402
    CORE_TEST_TARGETS,
    get_changed_files,
    main,
    map_changed_file_to_tests,
    resolve_base_ref,
    select_tests,
)


def test_core_targets_contain_required_suites() -> None:
    """Sicherstellen, dass alle verpflichtenden Core-Suites definiert sind."""
    required = {
        "tests/contracts",
        "tests/regression",
        "tests/unit",
        "tests/security",
        "tests/dependencies",
        "tests/services/report_agent",
        "tests/test_confidence_calculator.py",
        "tests/test_evidence_binder.py",
        "tests/llm",
        "tests/storage",
    }
    assert required.issubset(set(CORE_TEST_TARGETS))


def test_resolve_base_ref_explicit() -> None:
    assert resolve_base_ref("custom/branch") == "custom/branch"


def test_resolve_base_ref_fallback() -> None:
    with patch("subprocess.run") as mock_run:
        # Erster Aufruf fehlschlagen, zweiter gelingen
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]
        ref = resolve_base_ref()
        assert ref == "refs/remotes/origin/main"


def test_get_changed_files_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="backend/app/api/runs.py\nbackend/tests/api/test_runs.py\nfrontend/App.vue\n",
        )
        files = get_changed_files("origin/main")
        assert files == [
            "backend/app/api/runs.py",
            "backend/tests/api/test_runs.py",
            "frontend/App.vue",
        ]


def test_get_changed_files_empty_or_failure() -> None:
    assert get_changed_files(None) == []
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert get_changed_files("origin/main") == []


def test_map_changed_file_tests_dir() -> None:
    # Testdatei
    mapped = map_changed_file_to_tests("backend/tests/test_evidence_binder.py")
    assert mapped == ["tests/test_evidence_binder.py"]

    # Unterordner-Testdatei
    mapped_sub = map_changed_file_to_tests("tests/security/test_supabase_jwt.py")
    assert mapped_sub == ["tests/security/test_supabase_jwt.py"]


def test_map_changed_file_dependencies() -> None:
    assert map_changed_file_to_tests("backend/pyproject.toml") == ["tests/dependencies"]
    assert map_changed_file_to_tests("backend/uv.lock") == ["tests/dependencies"]


def test_map_changed_file_outside_backend() -> None:
    assert map_changed_file_to_tests("frontend/src/views/Home.vue") == []
    assert map_changed_file_to_tests("docs/STATUS.md") == []


def test_map_changed_file_app_modules() -> None:
    # contracts ist im Core abgedeckt
    assert map_changed_file_to_tests("backend/app/contracts/report.py") == []

    # utils -> test_file_parser.py existiert unter tests/utils/
    mapped_utils = map_changed_file_to_tests("backend/app/utils/file_parser.py")
    assert "tests/utils/test_file_parser.py" in mapped_utils

    # config.py -> dediziertes tests/config-Verzeichnis enthalten
    mapped_config = map_changed_file_to_tests("backend/app/config.py")
    assert "tests/config" in mapped_config

    # Unbekannte App-Datei -> konservativer Fallback statt leerer Liste
    mapped_unknown = map_changed_file_to_tests("backend/app/models/nonexistent_xyz_model.py")
    assert len(mapped_unknown) > 0
    assert "tests/api" in mapped_unknown
    assert "tests/services" in mapped_unknown

    # scripts -> test_check_voice.py existiert
    mapped_script = map_changed_file_to_tests("backend/scripts/check_voice.py")
    assert "tests/scripts/test_check_voice.py" in mapped_script or len(mapped_script) > 0


def test_select_tests_includes_core_and_ignores_contracts() -> None:
    with patch.object(select_pr_tests, "get_changed_files", return_value=[]):
        all_tests = select_tests(ignore_contracts=False)
        assert "tests/contracts" in all_tests
        assert "tests/security" in all_tests

        without_contracts = select_tests(ignore_contracts=True)
        assert "tests/contracts" not in without_contracts
        assert "tests/security" in without_contracts


def test_select_tests_adds_changed_files() -> None:
    changed = ["backend/tests/scripts/test_check_voice.py"]
    with patch.object(select_pr_tests, "get_changed_files", return_value=changed):
        targets = select_tests(ignore_contracts=True)
        assert "tests/scripts/test_check_voice.py" in targets


def test_main_cli_output(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(sys, "argv", ["select_pr_tests.py", "--count"]):
        assert main() == 0
        out, _ = capsys.readouterr()
        count = int(out.strip())
        assert count >= 9

    with patch.object(sys, "argv", ["select_pr_tests.py", "--json"]):
        assert main() == 0
        out, _ = capsys.readouterr()
        assert "tests/regression" in out
