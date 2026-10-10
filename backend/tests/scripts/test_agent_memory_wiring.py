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

    def fake_install(agent_graph: Any, *, max_comments: Any = None, log: Any = None) -> int:
        events.append("install_comment_cap")
        return 0

    monkeypatch.setattr(rps, "install_feed_comment_cap", fake_install)


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

    # Kommentardeckel einmal vor der ersten Runde (#1772); pro Runde genau ein Pruning,
    # direkt nach dem Schritt; Rundennummer 1-basiert wie im Action-Log.
    assert events == ["install_comment_cap", "step", "prune", "step", "prune"], platform
    assert [c["round_num"] for c in prune_calls] == [1, 2]
    assert all(c["graph"] is result.agent_graph for c in prune_calls)
    assert all(callable(c["log"]) for c in prune_calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile_file", "runner_name"),
    [
        ("twitter_profiles.csv", "run_twitter_simulation"),
        ("reddit_profiles.json", "run_reddit_simulation"),
    ],
)
async def test_both_parallel_loops_install_stance_anchor(
    monkeypatch: Any, tmp_path: Path, profile_file: str, runner_name: str
) -> None:
    """#1779: Haltungsanker je Aktivierung, genau einmal je Graph, mit der (ausgerichteten)
    Konfiguration der Schleife, nach dem Kommentardeckel und vor der ersten Runde."""
    (tmp_path / profile_file).write_text("{}" if profile_file.endswith("json") else "", encoding="utf-8")
    events: List[str] = []
    _patch(monkeypatch, events, [])
    anchor_calls: List[Dict[str, Any]] = []

    def fake_anchor(agent_graph: Any, agent_configs: Any, contested_statement: Any, *, log: Any = None) -> int:
        events.append("install_stance_anchor")
        anchor_calls.append(
            {"graph": agent_graph, "configs": agent_configs, "statement": contested_statement, "log": log}
        )
        return 1

    monkeypatch.setattr(rps, "install_stance_anchor", fake_anchor)
    config = _config()
    config["agent_configs"] = [{"agent_id": 0, "stance": "opposing", "sentiment_bias": -0.5}]
    config["contested_question"] = {"statement": "Der Kreistag schließt den Kreißsaal."}

    result = await getattr(rps, runner_name)(config, str(tmp_path))

    assert events == ["install_comment_cap", "install_stance_anchor", "step", "prune", "step", "prune"]
    assert len(anchor_calls) == 1
    (call,) = anchor_calls
    assert call["graph"] is result.agent_graph
    assert call["configs"] is config["agent_configs"]
    assert call["statement"] == "Der Kreistag schließt den Kreißsaal."
    assert callable(call["log"])


def test_single_platform_runner_installs_the_anchor_only_without_react_loop(
    monkeypatch: Any,
) -> None:
    """#1779: Der Single-Platform-Runner verankert die Haltung im Feed, solange kein ReAct-Loop
    läuft; mit ``tool_loop`` injiziert dieser sie je Runde selbst (kein doppelter Anker)."""
    from sim_runtime import platform_runner

    calls: List[Dict[str, Any]] = []

    def fake_anchor(agent_graph: Any, agent_configs: Any, contested_statement: Any, *, log: Any = None) -> int:
        calls.append({"graph": agent_graph, "configs": agent_configs, "statement": contested_statement})
        return 3

    monkeypatch.setattr(platform_runner, "install_stance_anchor", fake_anchor)
    runner = platform_runner.SinglePlatformRunner.__new__(platform_runner.SinglePlatformRunner)
    runner.agent_graph = object()
    runner.config = {
        "agent_configs": [{"agent_id": 0, "stance": "supportive"}],
        "contested_question": {"statement": "S"},
    }

    runner.tool_loop = object()
    assert runner._install_stance_anchor() == 0
    assert calls == []

    runner.tool_loop = None
    assert runner._install_stance_anchor() == 3
    assert calls == [{"graph": runner.agent_graph, "configs": runner.config["agent_configs"], "statement": "S"}]


def test_single_platform_runner_wires_the_anchor_after_the_tool_loop_decision() -> None:
    source = (_SCRIPTS_DIR / "sim_runtime" / "platform_runner.py").read_text(encoding="utf-8")
    loop_created = source.index("self.tool_loop = create_tool_aware_loop(")
    anchor = source.index("self._install_stance_anchor()")
    assert anchor > loop_created
    assert anchor < source.index("await self.env.step(actions)")


def test_single_platform_runner_prunes_after_env_step() -> None:
    source = (_SCRIPTS_DIR / "sim_runtime" / "platform_runner.py").read_text(encoding="utf-8")
    step = source.index("await self.env.step(actions)")
    prune = source.index("prune_graph_memories(self.agent_graph")
    assert prune > step
    assert "describe_memory_policy()" in source
    # Kommentardeckel wird vor dem Aufbau der OASIS-Umgebung eingehaengt.
    assert source.index("install_feed_comment_cap(self.agent_graph") < source.index("oasis.make(")
