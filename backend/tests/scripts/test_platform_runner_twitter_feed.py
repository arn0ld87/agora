"""Regression #1713 (Slice S4): der Single-Platform-Runner
(``sim_runtime/platform_runner.py``) baut fuer Twitter ein eigenes
``oasis.Platform``-Objekt mit erweiterten Recsys-Parametern statt der engen
OASIS-Defaults an ``oasis.DefaultPlatformType.TWITTER`` weiterzureichen —
identisch zu ``run_parallel_simulation.run_twitter_simulation``
(``test_run_parallel_simulation_twitter_feed.py``). Reddit bleibt
unveraendert.

``SinglePlatformRunner.run()`` macht danach noch viel mehr (IPCHandler,
Runden-Schleife) — das ist hier nicht das Testziel. Der Test laesst
``run()`` bis zur Env-Erzeugung real durchlaufen und faengt alles danach ab,
weil nur die ``oasis.Platform``/``oasis.make``-Aufrufkwargs interessieren.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

platform_runner = pytest.importorskip("sim_runtime.platform_runner")
from app.services.simulation_activity_policy import (  # noqa: E402
    TWITTER_FOLLOWING_POST_COUNT,
    TWITTER_MAX_REC_POST_LEN,
    TWITTER_REFRESH_REC_POST_COUNT,
)


class _FakeAgentGraph:
    def get_agents(self):
        return []


class _FakeEnv:
    async def reset(self) -> None:
        return None


def _make_runner(tmp_path: Path, *, platform_type: Any, platform_slug: str, profile_filename: str, db_filename: str):
    runner = platform_runner.SinglePlatformRunner.__new__(platform_runner.SinglePlatformRunner)
    runner.config_path = str(tmp_path / "simulation_config.json")
    # total_simulation_hours=0 => total_rounds=0: die Runden-Schleife (IPC,
    # RoundBoundaryControl, Aktiv-Agenten-Auswahl) laeuft gar nicht erst an.
    # Nur die Env-Erzeugung (oasis.Platform/oasis.make) ist das Testziel.
    runner.config = {
        "simulation_id": "sim-test",
        "agent_configs": [],
        "time_config": {"total_simulation_hours": 0, "minutes_per_round": 60},
    }
    runner.simulation_dir = str(tmp_path)
    runner.wait_for_commands = False
    runner.env = None
    runner.agent_graph = None
    runner.ipc_handler = None
    runner.tool_loop = None
    runner.redis_bridge = None
    runner.action_logger = None
    runner.PLATFORM_NAME = platform_slug.capitalize()
    runner.PLATFORM_SLUG = platform_slug
    runner.PROFILE_FILENAME = profile_filename
    runner.DB_FILENAME = db_filename
    runner.PLATFORM_TYPE = platform_type
    runner.AVAILABLE_ACTIONS = []

    async def fake_graph_generator(*, profile_path: str, model: Any, available_actions: Any) -> _FakeAgentGraph:
        return _FakeAgentGraph()

    runner.GRAPH_GENERATOR = fake_graph_generator
    return runner


def _patch_env_setup(monkeypatch: Any) -> Dict[str, Any]:
    captured: Dict[str, Any] = {}

    monkeypatch.setattr(platform_runner, "preflight_model_probe", lambda model: None)
    monkeypatch.setattr(platform_runner, "compute_start_hour_offset", lambda config, total_rounds, minutes_per_round: 0)

    def fake_platform(**kwargs: Any):
        captured["platform_kwargs"] = kwargs
        return ("fake-platform", kwargs)

    def fake_make(**kwargs: Any):
        captured["make_kwargs"] = kwargs
        return _FakeEnv()

    monkeypatch.setattr(platform_runner.oasis, "Platform", fake_platform)
    monkeypatch.setattr(platform_runner.oasis, "make", fake_make)

    return captured


@pytest.mark.asyncio
async def test_twitter_feed_parameters_are_passed_to_oasis_platform(
    monkeypatch: Any, tmp_path: Path
) -> None:
    (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
    captured = _patch_env_setup(monkeypatch)
    runner = _make_runner(
        tmp_path,
        platform_type=platform_runner.oasis.DefaultPlatformType.TWITTER,
        platform_slug="twitter",
        profile_filename="twitter_profiles.csv",
        db_filename="twitter_simulation.db",
    )
    monkeypatch.setattr(runner, "_create_model", lambda: object())

    # Alles nach der Env-Erzeugung (IPCHandler, Runden-Schleife) ist hier
    # nicht gemockt und darf den Test nicht zum Fehlschlagen bringen — nur
    # die Platform-/make-Kwargs sind das Testziel.
    with contextlib.suppress(Exception):
        await runner.run()

    assert "platform_kwargs" in captured, "oasis.Platform wurde nicht aufgerufen"
    platform_kwargs = captured["platform_kwargs"]
    assert platform_kwargs["recsys_type"] == "twhin-bert"
    assert platform_kwargs["refresh_rec_post_count"] == TWITTER_REFRESH_REC_POST_COUNT
    assert platform_kwargs["max_rec_post_len"] == TWITTER_MAX_REC_POST_LEN
    assert platform_kwargs["following_post_count"] == TWITTER_FOLLOWING_POST_COUNT
    assert platform_kwargs["db_path"] == captured["make_kwargs"]["database_path"]
    assert captured["make_kwargs"]["platform"] == ("fake-platform", platform_kwargs)


@pytest.mark.asyncio
async def test_reddit_uses_default_platform_type_unchanged(
    monkeypatch: Any, tmp_path: Path
) -> None:
    (tmp_path / "reddit_profiles.json").write_text("{}", encoding="utf-8")
    captured = _patch_env_setup(monkeypatch)
    runner = _make_runner(
        tmp_path,
        platform_type=platform_runner.oasis.DefaultPlatformType.REDDIT,
        platform_slug="reddit",
        profile_filename="reddit_profiles.json",
        db_filename="reddit_simulation.db",
    )
    monkeypatch.setattr(runner, "_create_model", lambda: object())

    with contextlib.suppress(Exception):
        await runner.run()

    assert "platform_kwargs" not in captured, "Reddit darf kein oasis.Platform bauen"
    assert captured["make_kwargs"]["platform"] == platform_runner.oasis.DefaultPlatformType.REDDIT
