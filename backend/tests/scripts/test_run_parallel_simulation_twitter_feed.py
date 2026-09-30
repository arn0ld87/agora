"""Regression #1713 (Slice S4): der Twitter-Feed bekommt eigene
Recsys-Parameter statt der engen OASIS-Defaults (``oasis/environment/env.py``:
``refresh_rec_post_count=2``, ``max_rec_post_len=2``,
``following_post_count=3``). ``run_parallel_simulation.run_twitter_simulation``
baut dafuer ein eigenes ``oasis.Platform``-Objekt statt
``oasis.DefaultPlatformType.TWITTER`` direkt an ``oasis.make`` zu uebergeben.

Reddit bleibt unveraendert (weiterhin ``oasis.DefaultPlatformType.REDDIT``),
siehe ``test_reddit_uses_default_platform_type`` unten.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402
from sim_runtime.run_control import RoundAction, RoundDecision  # noqa: E402
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


class _ImmediateStopControl:
    """Signalisiert STOP bereits fuer Runde 0 — die Env-Erzeugung (oasis.make/
    oasis.Platform) liegt VOR dem ersten Control-Check, laeuft also in jedem
    Fall, bevor die Schleife abbricht (siehe budget_abort_info-Tests in
    ``test_run_parallel_simulation_control.py``)."""

    def check(self, round_num: int) -> RoundDecision:
        return RoundDecision(RoundAction.STOP)


def _patch_env_setup(monkeypatch: Any) -> Dict[str, Any]:
    captured: Dict[str, Any] = {}

    monkeypatch.setattr(rps, "RoundBoundaryControl", lambda *a, **kw: _ImmediateStopControl())

    async def fake_generate_agent_graph(*, profile_path: str, model: Any, available_actions: Any) -> _FakeAgentGraph:
        return _FakeAgentGraph()

    monkeypatch.setattr(rps, "generate_twitter_agent_graph", fake_generate_agent_graph)
    monkeypatch.setattr(rps, "generate_reddit_agent_graph", fake_generate_agent_graph)
    monkeypatch.setattr(rps, "create_model", lambda config, use_boost=False: object())
    monkeypatch.setattr(rps, "preflight_model_probe", lambda model: None)
    monkeypatch.setattr(rps, "compute_start_hour_offset", lambda config, total_rounds, minutes_per_round: 0)

    def fake_platform(**kwargs: Any):
        captured["platform_kwargs"] = kwargs
        return ("fake-platform", kwargs)

    def fake_make(**kwargs: Any):
        captured["make_kwargs"] = kwargs
        return _FakeEnv()

    monkeypatch.setattr(rps.oasis, "Platform", fake_platform)
    monkeypatch.setattr(rps.oasis, "make", fake_make)

    return captured


def _base_config() -> Dict[str, Any]:
    return {
        "agent_configs": [],
        "event_config": {},
        "enable_agent_tools": False,
        "time_config": {"total_simulation_hours": 1, "minutes_per_round": 30},
    }


@pytest.mark.asyncio
async def test_twitter_feed_parameters_are_passed_to_oasis_platform(
    monkeypatch: Any, tmp_path: Path
) -> None:
    (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
    captured = _patch_env_setup(monkeypatch)

    await rps.run_twitter_simulation(_base_config(), str(tmp_path))

    assert "platform_kwargs" in captured, "oasis.Platform wurde nicht aufgerufen"
    platform_kwargs = captured["platform_kwargs"]
    assert platform_kwargs["recsys_type"] == "twhin-bert"
    assert platform_kwargs["refresh_rec_post_count"] == TWITTER_REFRESH_REC_POST_COUNT
    assert platform_kwargs["max_rec_post_len"] == TWITTER_MAX_REC_POST_LEN
    assert platform_kwargs["following_post_count"] == TWITTER_FOLLOWING_POST_COUNT
    assert platform_kwargs["db_path"] == captured["make_kwargs"]["database_path"]

    # Das gebaute Platform-Objekt wird an oasis.make durchgereicht, nicht
    # DefaultPlatformType.TWITTER direkt.
    assert captured["make_kwargs"]["platform"] == ("fake-platform", platform_kwargs)


@pytest.mark.asyncio
async def test_reddit_uses_default_platform_type_unchanged(
    monkeypatch: Any, tmp_path: Path
) -> None:
    (tmp_path / "reddit_profiles.json").write_text("{}", encoding="utf-8")
    captured = _patch_env_setup(monkeypatch)

    await rps.run_reddit_simulation(_base_config(), str(tmp_path))

    assert "platform_kwargs" not in captured, "Reddit darf kein oasis.Platform bauen"
    assert captured["make_kwargs"]["platform"] == rps.oasis.DefaultPlatformType.REDDIT
