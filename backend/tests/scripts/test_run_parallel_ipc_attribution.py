"""``ParallelIPCHandler`` bucht Interview-Verbrauch auf den Report-Run
(Tech-Review Slice B4c).

Vor diesem Fix kannte ``ParallelIPCHandler`` (Default-Pfad Twitter+Reddit)
``budget_guard``/``report_run_id`` ueberhaupt nicht — jeder physische
Modellaufruf eines Report-Interviews blieb auf diesem Pfad unverbucht, das
Hard-Budget des Report-Runs war umgehbar. Stilvorlage:
``tests/scripts/test_sim_runtime_ipc.py`` (``IPCHandler``-Pendant).
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


class FakeAgent:
    def __init__(self, agent_id: int) -> None:
        self.agent_id = agent_id

    def __hash__(self) -> int:
        return hash(self.agent_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FakeAgent) and other.agent_id == self.agent_id


class FakeAgentGraph:
    def get_agent(self, agent_id: int) -> FakeAgent:
        return FakeAgent(agent_id)


class _FakeAttributionCtx:
    def __init__(self, guard: "FakeBudgetGuard") -> None:
        self._guard = guard

    def __enter__(self) -> None:
        self._guard.active_calls += 1
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self._guard.active_calls -= 1
        return False


class FakeBudgetGuard:
    """Testdouble fuer ``SubprocessBudgetGuard`` (analog test_sim_runtime_ipc.py)."""

    def __init__(self) -> None:
        self.attribute_calls: list[tuple[str, str]] = []
        self.active_calls = 0

    def attribute_to(self, run_id: str, stage: str) -> _FakeAttributionCtx:
        self.attribute_calls.append((run_id, stage))
        return _FakeAttributionCtx(self)


class RecordingFakeEnv:
    """Faked OASIS-Environment; zeichnet auf, ob ``step`` waehrend einer
    aktiven Budget-Attribution lief."""

    def __init__(self, guard: FakeBudgetGuard) -> None:
        self._guard = guard
        self.step_ran_while_attributed: list[bool] = []
        self.steps: list[Dict[Any, Any]] = []

    async def step(self, actions: Dict[Any, Any]) -> None:
        self.step_ran_while_attributed.append(self._guard.active_calls > 0)
        self.steps.append(actions)


def _make_handler(
    tmp_path: Path,
    *,
    twitter_env: Any = None,
    twitter_agent_graph: Any = None,
    reddit_env: Any = None,
    reddit_agent_graph: Any = None,
    budget_guard: Any = None,
) -> "rps.ParallelIPCHandler":
    return rps.ParallelIPCHandler(
        simulation_dir=str(tmp_path),
        twitter_env=twitter_env,
        twitter_agent_graph=twitter_agent_graph,
        reddit_env=reddit_env,
        reddit_agent_graph=reddit_agent_graph,
        budget_guard=budget_guard,
    )


@pytest.mark.asyncio
async def test_handle_interview_single_platform_attributes_to_report_run(tmp_path: Path) -> None:
    guard = FakeBudgetGuard()
    env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    ok = await handler.handle_interview(
        "cmd1", 7, "Wie siehst du das?", platform="twitter", report_run_id="run-report-1"
    )
    assert ok is True
    assert guard.attribute_calls == [("run-report-1", "report_interview")]
    assert env.step_ran_while_attributed == [True]


@pytest.mark.asyncio
async def test_handle_interview_both_platforms_attributes_each_step(tmp_path: Path) -> None:
    guard = FakeBudgetGuard()
    twitter_env = RecordingFakeEnv(guard)
    reddit_env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path,
        twitter_env=twitter_env,
        twitter_agent_graph=FakeAgentGraph(),
        reddit_env=reddit_env,
        reddit_agent_graph=FakeAgentGraph(),
        budget_guard=guard,
    )
    ok = await handler.handle_interview("cmd1", 3, "prompt", report_run_id="run-report-2")
    assert ok is True
    assert sorted(guard.attribute_calls) == [
        ("run-report-2", "report_interview"),
        ("run-report-2", "report_interview"),
    ]
    assert twitter_env.step_ran_while_attributed == [True]
    assert reddit_env.step_ran_while_attributed == [True]


@pytest.mark.asyncio
async def test_handle_batch_interview_attributes_to_report_run(tmp_path: Path) -> None:
    guard = FakeBudgetGuard()
    env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    ok = await handler.handle_batch_interview(
        "cmd1",
        [{"agent_id": 1, "prompt": "a"}, {"agent_id": 2, "prompt": "b"}],
        platform="twitter",
        report_run_id="run-report-3",
    )
    assert ok is True
    assert guard.attribute_calls == [("run-report-3", "report_interview")]
    assert env.step_ran_while_attributed == [True]


@pytest.mark.asyncio
async def test_handle_interview_without_report_run_id_never_attributes(tmp_path: Path) -> None:
    """Rueckwaertskompatibilitaet: kein ``report_run_id`` -> Guard bleibt unangetastet."""
    guard = FakeBudgetGuard()
    env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    ok = await handler.handle_interview("cmd1", 7, "prompt", platform="twitter")
    assert ok is True
    assert guard.attribute_calls == []
    assert env.step_ran_while_attributed == [False]


@pytest.mark.asyncio
async def test_handle_interview_without_budget_guard_ignores_report_run_id(tmp_path: Path) -> None:
    """Rueckwaertskompatibilitaet: kein injizierter Guard -> report_run_id wird ignoriert."""
    env = RecordingFakeEnv(FakeBudgetGuard())  # Guard existiert, wird dem Handler aber nicht gegeben.
    handler = _make_handler(tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph())
    ok = await handler.handle_interview(
        "cmd1", 7, "prompt", platform="twitter", report_run_id="run-report-4"
    )
    assert ok is True
    assert len(env.steps) == 1


@pytest.mark.asyncio
async def test_execute_command_interview_forwards_report_run_id(tmp_path: Path) -> None:
    guard = FakeBudgetGuard()
    env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    assert await handler._execute_command(
        "c1",
        rps.CommandType.INTERVIEW,
        {"agent_id": 1, "prompt": "p", "platform": "twitter", "report_run_id": "run-report-5"},
    ) is True
    assert guard.attribute_calls == [("run-report-5", "report_interview")]


@pytest.mark.asyncio
async def test_execute_command_batch_forwards_report_run_id(tmp_path: Path) -> None:
    guard = FakeBudgetGuard()
    env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    assert await handler._execute_command(
        "c1",
        rps.CommandType.BATCH_INTERVIEW,
        {
            "interviews": [{"agent_id": 1, "prompt": "p"}],
            "platform": "twitter",
            "report_run_id": "run-report-6",
        },
    ) is True
    assert guard.attribute_calls == [("run-report-6", "report_interview")]
