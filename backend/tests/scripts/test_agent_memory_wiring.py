"""Verdrahtung des Feed-Pruning in den Runden-Schleifen (#1772).

``run_parallel_simulation`` ruft ``prune_graph_memories`` nach jedem
``env.step`` beider Plattform-Schleifen; ``SinglePlatformRunner.run`` tut es
ebenso. Die Schleifen laufen hier mit Fakes (kein OASIS-Env, kein LLM).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402
from sim_runtime.run_control import RoundAction, RoundDecision  # noqa: E402


class _Agent:
    username = "mara"


class _Graph:
    def get_agents(self) -> List[Any]:
        return [(1, _Agent())]


class _Env:
    def __init__(self, events: List[str]) -> None:
        self._events = events

    async def reset(self) -> None:
        return None

    async def step(self, actions: Dict[Any, Any]) -> None:
        self._events.append("step")


class _Control:
    def check(self, round_num: int) -> RoundDecision:
        return RoundDecision(RoundAction.CONTINUE)


def _patch(monkeypatch: Any, events: List[str], prune_calls: List[Dict[str, Any]]) -> None:
    async def fake_graph(*, profile_path: str, model: Any, available_actions: Any) -> _Graph:
        return _Graph()

    def fake_prune(agent_graph: Any, *, round_num: Any = None, log: Any = None) -> None:
        events.append("prune")
        prune_calls.append({"graph": agent_graph, "round_num": round_num, "log": log})

    monkeypatch.setattr(rps, "RoundBoundaryControl", lambda simulation_dir, budget_guard: _Control())
    monkeypatch.setattr(rps, "generate_twitter_agent_graph", fake_graph)
    monkeypatch.setattr(rps, "generate_reddit_agent_graph", fake_graph)
    monkeypatch.setattr(rps, "create_model", lambda config, use_boost=False: object())
    monkeypatch.setattr(rps, "preflight_model_probe", lambda model: None)
    monkeypatch.setattr(rps, "compute_start_hour_offset", lambda config, total_rounds, minutes_per_round: 0)
    monkeypatch.setattr(rps.oasis, "make", lambda **kwargs: _Env(events))
    monkeypatch.setattr(
        rps, "get_active_agents_for_round", lambda env, config, simulated_hour, round_num: [(1, _Agent())]
    )
    monkeypatch.setattr(rps, "fetch_new_actions_from_db", lambda db_path, last_rowid, names: ([], last_rowid))
    monkeypatch.setattr(rps, "prune_graph_memories", fake_prune)


def _config() -> Dict[str, Any]:
    return {
        "agent_configs": [],
        "event_config": {},
        "enable_agent_tools": False,
        # 1h / 30min => 2 Runden
        "time_config": {"total_simulation_hours": 1, "minutes_per_round": 30},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "profile_file", "runner_name"),
    [
        ("twitter", "twitter_profiles.csv", "run_twitter_simulation"),
        ("reddit", "reddit_profiles.json", "run_reddit_simulation"),
    ],
)
async def test_round_loop_prunes_after_every_step(
    monkeypatch: Any, tmp_path: Path, platform: str, profile_file: str, runner_name: str
) -> None:
    (tmp_path / profile_file).write_text("{}" if profile_file.endswith("json") else "", encoding="utf-8")
    events: List[str] = []
    prune_calls: List[Dict[str, Any]] = []
    _patch(monkeypatch, events, prune_calls)

    result = await getattr(rps, runner_name)(_config(), str(tmp_path))

    # Pro Runde genau ein Pruning, direkt nach dem Schritt; Rundennummer 1-basiert wie im Action-Log.
    assert events == ["step", "prune", "step", "prune"], platform
    assert [c["round_num"] for c in prune_calls] == [1, 2]
    assert all(c["graph"] is result.agent_graph for c in prune_calls)
    assert all(callable(c["log"]) for c in prune_calls)


def test_single_platform_runner_prunes_after_env_step() -> None:
    source = (_SCRIPTS_DIR / "sim_runtime" / "platform_runner.py").read_text(encoding="utf-8")
    step = source.index("await self.env.step(actions)")
    prune = source.index("prune_graph_memories(self.agent_graph")
    assert prune > step
    assert "describe_memory_policy()" in source
