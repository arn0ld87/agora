from __future__ import annotations

from pathlib import Path
import importlib.util
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
MODULE_PATH = SCRIPTS_DIR / "_sim_common.py"
spec = importlib.util.spec_from_file_location("_sim_common", MODULE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not create module spec for {MODULE_PATH}")
_sim_common = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _sim_common
spec.loader.exec_module(_sim_common)


def test_resolve_runtime_paths_returns_expected_layout():
    script_path = Path("/tmp/agora/backend/scripts/run_twitter_simulation.py")
    resolved_script = script_path.resolve()
    paths = _sim_common.resolve_runtime_paths(script_path)

    assert paths.scripts_dir == resolved_script.parent
    assert paths.backend_dir == resolved_script.parent.parent
    assert paths.project_root == resolved_script.parent.parent.parent


@pytest.mark.parametrize("description", ["OASIS Twitter Simulation", "OASIS Reddit Simulation"])
def test_build_single_platform_parser_supports_shared_args(description: str):
    parser = _sim_common.build_single_platform_parser(description)
    args = parser.parse_args(["--config", "simulation_config.json", "--max-rounds", "12", "--no-wait"])

    assert args.config == "simulation_config.json"
    assert args.max_rounds == 12
    assert args.no_wait is True


def test_build_parallel_parser_supports_platform_switches():
    parser = _sim_common.build_parallel_parser()
    args = parser.parse_args([
        "--config", "simulation_config.json",
        "--twitter-only",
        "--max-rounds", "7",
        "--no-wait",
    ])

    assert args.config == "simulation_config.json"
    assert args.twitter_only is True
    assert args.reddit_only is False
    assert args.max_rounds == 7
    assert args.no_wait is True


def test_max_tokens_warning_filter_matches_only_target_warning():
    warning = "Invalid or missing max_tokens value in request"
    other = "totally different warning"

    assert _sim_common.should_filter_max_tokens_warning(warning) is True
    assert _sim_common.should_filter_max_tokens_warning(other) is False


def _run_help(script_name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), "--help"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=20,
    )


@pytest.mark.parametrize(
    ("script_name", "expected_text"),
    [
        ("run_twitter_simulation.py", "OASIS Twitter Simulation"),
        ("run_reddit_simulation.py", "OASIS Reddit Simulation"),
        ("run_parallel_simulation.py", "OASIS Dual-Platform Parallel Simulation"),
    ],
)
def test_runner_help_smoke_exits_zero(script_name: str, expected_text: str):
    result = _run_help(script_name)
    assert result.returncode == 0
    assert expected_text in result.stdout
    assert "--config" in result.stdout
