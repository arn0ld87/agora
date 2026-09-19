"""``ParallelIPCHandler`` bucht Interview-Verbrauch auf den Report-Run
(Tech-Review Slice B4c).

Vor diesem Fix kannte ``ParallelIPCHandler`` (Default-Pfad Twitter+Reddit)
``budget_guard``/``report_run_id`` ueberhaupt nicht — jeder physische
Modellaufruf eines Report-Interviews blieb auf diesem Pfad unverbucht, das
Hard-Budget des Report-Runs war umgehbar. Stilvorlage:
``tests/scripts/test_sim_runtime_ipc.py`` (``IPCHandler``-Pendant).

Zusatz: BudgetExceededError-Handling (Slice 3.1, #1478 Codex P1, Runde 7).
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
from app.services.run_budget import BudgetExceededError  # noqa: E402  # BudgetExceededError is imported locally in the module; import from source for tests


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


class BudgetExceededFakeEnv(RecordingFakeEnv):
    """FakeEnv, das bei ``step`` ein ``BudgetExceededError`` wirft."""

    def __init__(self, guard: FakeBudgetGuard, dimension: str = "tokens", observed: int = 1000, threshold: int = 800) -> None:
        super().__init__(guard)
        self._budget_error = BudgetExceededError(dimension, observed, threshold)

    async def step(self, actions: Dict[Any, Any]) -> None:
        self.step_ran_while_attributed.append(self._guard.active_calls > 0)
        self.steps.append(actions)
        raise self._budget_error


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


# ---------------------------------------------------------------------------
# Slice 3.1 — BudgetExceededError handling regression tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_interview_single_platform_budget_exceeded_returns_structured_error(
    tmp_path: Path,
) -> None:
    """BudgetExceededError auf einzelner Plattform -> strukturiertes
    ``budget_exceeded``-Feld in der Response, ok=False."""
    guard = FakeBudgetGuard()
    env = BudgetExceededFakeEnv(guard, dimension="tokens", observed=1000, threshold=800)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    ok = await handler.handle_interview(
        "cmd1", 7, "prompt", platform="twitter", report_run_id="run-report-7"
    )
    assert ok is False
    # Response file written with budget_exceeded
    import json
    response_file = Path(tmp_path) / "ipc_responses" / "cmd1.json"
    assert response_file.exists()
    response = json.loads(response_file.read_text(encoding="utf-8"))
    assert response["status"] == "failed"
    assert response["budget_exceeded"] is not None
    assert response["budget_exceeded"]["dimension"] == "tokens"
    assert response["budget_exceeded"]["observed"] == 1000
    assert response["budget_exceeded"]["threshold"] == 800
    # Attribution still ran
    assert guard.attribute_calls == [("run-report-7", "report_interview")]


@pytest.mark.asyncio
async def test_handle_interview_both_platforms_budget_exceeded_on_one_detected_before_success_count(
    tmp_path: Path,
) -> None:
    """BudgetExceeded auf einer Plattform, andere erfolgreich -> Budget
    hat Vorrang vor success_count, Response traegt budget_exceeded."""
    guard = FakeBudgetGuard()
    twitter_env = BudgetExceededFakeEnv(guard, dimension="tokens", observed=1000, threshold=800)
    reddit_env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path,
        twitter_env=twitter_env,
        twitter_agent_graph=FakeAgentGraph(),
        reddit_env=reddit_env,
        reddit_agent_graph=FakeAgentGraph(),
        budget_guard=guard,
    )
    ok = await handler.handle_interview("cmd1", 3, "prompt", report_run_id="run-report-8")
    assert ok is False
    import json
    response_file = Path(tmp_path) / "ipc_responses" / "cmd1.json"
    response = json.loads(response_file.read_text(encoding="utf-8"))
    assert response["status"] == "failed"
    assert response["budget_exceeded"] is not None
    assert response["budget_exceeded"]["dimension"] == "tokens"
    # Reddit step still ran (attribution active)
    assert reddit_env.step_ran_while_attributed == [True]
    # Twitter step also ran
    assert twitter_env.step_ran_while_attributed == [True]


@pytest.mark.asyncio
async def test_handle_batch_interview_budget_exceeded_returns_structured_error(
    tmp_path: Path,
) -> None:
    """Batch-Interview: BudgetExceeded auf einer Plattform ->
    strukturiertes budget_exceeded in Response."""
    guard = FakeBudgetGuard()
    env = BudgetExceededFakeEnv(guard, dimension="cost", observed=5000, threshold=3000)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    ok = await handler.handle_batch_interview(
        "cmd1",
        [{"agent_id": 1, "prompt": "a"}, {"agent_id": 2, "prompt": "b"}],
        platform="twitter",
        report_run_id="run-report-9",
    )
    assert ok is False
    import json
    response_file = Path(tmp_path) / "ipc_responses" / "cmd1.json"
    response = json.loads(response_file.read_text(encoding="utf-8"))
    assert response["status"] == "failed"
    assert response["budget_exceeded"] is not None
    assert response["budget_exceeded"]["dimension"] == "cost"
    assert response["budget_exceeded"]["observed"] == 5000
    assert response["budget_exceeded"]["threshold"] == 3000
    assert guard.attribute_calls == [("run-report-9", "report_interview")]


@pytest.mark.asyncio
async def test_handle_batch_interview_both_platforms_budget_exceeded_first_wins(
    tmp_path: Path,
) -> None:
    """Batch beide Plattformen: Twitter BudgetExceeded, Reddit OK ->
    Twitter-Dimension gewinnt (first budget_exceeded wins)."""
    guard = FakeBudgetGuard()
    twitter_env = BudgetExceededFakeEnv(guard, dimension="tokens", observed=1000, threshold=800)
    reddit_env = RecordingFakeEnv(guard)
    handler = _make_handler(
        tmp_path,
        twitter_env=twitter_env,
        twitter_agent_graph=FakeAgentGraph(),
        reddit_env=reddit_env,
        reddit_agent_graph=FakeAgentGraph(),
        budget_guard=guard,
    )
    ok = await handler.handle_batch_interview(
        "cmd1",
        [{"agent_id": 1, "prompt": "a"}],
        platform=None,  # both platforms
        report_run_id="run-report-10",
    )
    assert ok is False
    import json
    response_file = Path(tmp_path) / "ipc_responses" / "cmd1.json"
    response = json.loads(response_file.read_text(encoding="utf-8"))
    assert response["status"] == "failed"
    assert response["budget_exceeded"] is not None
    assert response["budget_exceeded"]["dimension"] == "tokens"  # Twitter dimension wins
    # Both platforms still ran (attribution active)
    assert twitter_env.step_ran_while_attributed == [True]
    assert reddit_env.step_ran_while_attributed == [True]


@pytest.mark.asyncio
async def test_interview_single_platform_budget_exceeded_client_reraises(
    tmp_path: Path,
) -> None:
    """Der Parallelrunner schreibt eine Response, die der Client wieder in
    ``BudgetExceededError`` uebersetzt.

    Der Test geht den echten Weg statt ihn nachzubilden: Handler ->
    Response-JSON -> ``IPCResponse.from_dict`` -> ``_reraise_if_budget_exceeded``.
    Damit bricht er auch dann, wenn nur die Feldnamen im geschriebenen JSON
    von dem abweichen, was die Client-Deserialisierung erwartet — genau die
    Luecke, die #1478 offen gelassen hatte.
    """
    guard = FakeBudgetGuard()
    env = BudgetExceededFakeEnv(guard, dimension="time", observed=3600, threshold=1800)
    handler = _make_handler(
        tmp_path, twitter_env=env, twitter_agent_graph=FakeAgentGraph(), budget_guard=guard
    )
    ok = await handler.handle_interview(
        "cmd1", 7, "prompt", platform="twitter", report_run_id="run-report-11"
    )
    assert ok is False

    import json

    from app.services.run_budget import BudgetExceededError
    from app.services.sim.interview_client import _reraise_if_budget_exceeded
    from app.services.simulation_ipc import IPCResponse

    response_file = Path(tmp_path) / "ipc_responses" / "cmd1.json"
    response = IPCResponse.from_dict(json.loads(response_file.read_text(encoding="utf-8")))

    with pytest.raises(BudgetExceededError) as excinfo:
        _reraise_if_budget_exceeded(response)

    assert excinfo.value.dimension == "time"
    assert excinfo.value.observed == 3600
    assert excinfo.value.threshold == 1800