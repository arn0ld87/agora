"""Characterization-Tests für ``sim_runtime.ipc``.

Sichern das Verhalten des aus den Single-Platform-Runnern extrahierten
``IPCHandler``-Netzwerks ohne die torch-abhängige Oasis-Laufzeit: alle
Oasis-Symbole (``ManualAction``, ``ActionType.INTERVIEW``) werden als
Fakes injiziert, sodass der Test-Tree auf dieser Maschine ohne
OASIS/torch-Crash läuft. Verhaltensanker: Datei-IPC-Layout,
Response-Format, Command-Dedup gegen den Redis-Bus, Interview-Dispatch
und die ``_execute_command``-True/False-Matrix (Close-Env → ``False``).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from sim_runtime.ipc import (  # noqa: E402
    ENV_STATUS_FILE,
    IPC_COMMANDS_DIR,
    IPC_RESPONSES_DIR,
    CommandType,
    IPCHandler,
)

INTERVIEW_VALUE = "interview"


class FakeActionType:
    value = INTERVIEW_VALUE


class FakeManualAction:
    def __init__(self, *, action_type: Any, action_args: Dict[str, Any]) -> None:
        self.action_type = action_type
        self.action_args = action_args


class FakeAgent:
    def __init__(self, agent_id: int) -> None:
        self.agent_id = agent_id

    def __hash__(self) -> int:
        return hash(self.agent_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FakeAgent) and other.agent_id == self.agent_id


class FakeAgentGraph:
    def __init__(self, valid_ids: set[int] | None = None) -> None:
        self.valid_ids = valid_ids

    def get_agent(self, agent_id: int) -> FakeAgent:
        if self.valid_ids is not None and agent_id not in self.valid_ids:
            raise KeyError(agent_id)
        return FakeAgent(agent_id)


class FakeEnv:
    def __init__(self, *, raise_on_step: bool = False) -> None:
        self.raise_on_step = raise_on_step
        self.steps: list[Dict[Any, Any]] = []

    async def step(self, actions: Dict[Any, Any]) -> None:
        if self.raise_on_step:
            raise RuntimeError("boom")
        self.steps.append(actions)


class FakeBridge:
    def __init__(self, *, active: bool = True) -> None:
        self.active = active
        self.published: list[tuple[str, Dict[str, Any]]] = []

    async def publish_response(self, command_id: str, response: Dict[str, Any]) -> None:
        self.published.append((command_id, response))


def _make_handler(
    tmp_path: Path,
    *,
    env: Any | None = None,
    agent_graph: Any | None = None,
    redis_bridge: Any | None = None,
    db_filename: str = "twitter_simulation.db",
) -> IPCHandler:
    return IPCHandler(
        str(tmp_path),
        env if env is not None else FakeEnv(),
        agent_graph if agent_graph is not None else FakeAgentGraph(),
        db_filename=db_filename,
        interview_action_type=FakeActionType(),
        manual_action_cls=FakeManualAction,
        redis_bridge=redis_bridge,
    )


def test_command_type_constants():
    assert CommandType.INTERVIEW == "interview"
    assert CommandType.BATCH_INTERVIEW == "batch_interview"
    assert CommandType.CLOSE_ENV == "close_env"


def test_ipc_directory_constants():
    assert IPC_COMMANDS_DIR == "ipc_commands"
    assert IPC_RESPONSES_DIR == "ipc_responses"
    assert ENV_STATUS_FILE == "env_status.json"


def test_init_creates_directories(tmp_path: Path):
    handler = _make_handler(tmp_path)
    assert os.path.isdir(tmp_path / IPC_COMMANDS_DIR)
    assert os.path.isdir(tmp_path / IPC_RESPONSES_DIR)
    assert handler.db_filename == "twitter_simulation.db"


def test_update_status_writes_status_and_timestamp(tmp_path: Path):
    handler = _make_handler(tmp_path)
    handler.update_status("running")
    data = json.loads((tmp_path / ENV_STATUS_FILE).read_text(encoding="utf-8"))
    assert data["status"] == "running"
    assert "timestamp" in data


def test_poll_command_returns_oldest_first(tmp_path: Path):
    handler = _make_handler(tmp_path)
    cmds = tmp_path / IPC_COMMANDS_DIR
    older = cmds / "a.json"
    newer = cmds / "b.json"
    newer.write_text(json.dumps({"command_id": "second"}), encoding="utf-8")
    os.utime(newer, (1, 1))
    older.write_text(json.dumps({"command_id": "first"}), encoding="utf-8")
    os.utime(older, (0, 0))
    assert handler.poll_command()["command_id"] == "first"


def test_poll_command_skips_invalid_json(tmp_path: Path):
    handler = _make_handler(tmp_path)
    cmds = tmp_path / IPC_COMMANDS_DIR
    (cmds / "broken.json").write_text("{not json", encoding="utf-8")
    (cmds / "ok.json").write_text(json.dumps({"command_id": "ok"}), encoding="utf-8")
    assert handler.poll_command()["command_id"] == "ok"


def test_poll_command_no_dir_returns_none(tmp_path: Path):
    handler = _make_handler(tmp_path)
    # Directory exists (created in __init__) but is empty.
    assert handler.poll_command() is None


@pytest.mark.asyncio
async def test_send_response_writes_file_and_deletes_command(tmp_path: Path):
    handler = _make_handler(tmp_path)
    cmds = tmp_path / IPC_COMMANDS_DIR
    (cmds / "cmd1.json").write_text("{}", encoding="utf-8")
    await handler.send_response("cmd1", "completed", result={"x": 1})
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "cmd1.json").read_text(encoding="utf-8"))
    assert resp["command_id"] == "cmd1"
    assert resp["status"] == "completed"
    assert resp["result"] == {"x": 1}
    assert "timestamp" in resp
    assert not (cmds / "cmd1.json").exists()


@pytest.mark.asyncio
async def test_send_response_mirrors_to_redis_when_bridge_active(tmp_path: Path):
    bridge = FakeBridge(active=True)
    handler = _make_handler(tmp_path, redis_bridge=bridge)
    await handler.send_response("cmd1", "completed")
    assert bridge.published == [("cmd1", json.loads(
        (tmp_path / IPC_RESPONSES_DIR / "cmd1.json").read_text(encoding="utf-8")
    ))]


@pytest.mark.asyncio
async def test_send_response_no_mirror_when_bridge_inactive(tmp_path: Path):
    bridge = FakeBridge(active=False)
    handler = _make_handler(tmp_path, redis_bridge=bridge)
    await handler.send_response("cmd1", "completed")
    assert bridge.published == []


@pytest.mark.asyncio
async def test_handle_interview_success(tmp_path: Path):
    env = FakeEnv()
    handler = _make_handler(tmp_path, env=env, agent_graph=FakeAgentGraph({7}))
    ok = await handler.handle_interview("cmd1", 7, "Wie siehst du das?")
    assert ok is True
    assert len(env.steps) == 1
    action = next(iter(env.steps[0].values()))
    assert isinstance(action, FakeManualAction)
    assert action.action_type.value == INTERVIEW_VALUE
    assert action.action_args == {"prompt": "Wie siehst du das?"}
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "cmd1.json").read_text(encoding="utf-8"))
    assert resp["status"] == "completed"
    assert resp["result"]["agent_id"] == 7


@pytest.mark.asyncio
async def test_handle_interview_failure_sends_failed(tmp_path: Path):
    env = FakeEnv(raise_on_step=True)
    handler = _make_handler(tmp_path, env=env, agent_graph=FakeAgentGraph({7}))
    ok = await handler.handle_interview("cmd1", 7, "prompt")
    assert ok is False
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "cmd1.json").read_text(encoding="utf-8"))
    assert resp["status"] == "failed"
    assert "boom" in resp["error"]


@pytest.mark.asyncio
async def test_handle_batch_interview_success(tmp_path: Path):
    env = FakeEnv()
    handler = _make_handler(tmp_path, env=env, agent_graph=FakeAgentGraph({1, 2}))
    ok = await handler.handle_batch_interview("cmd1", [
        {"agent_id": 1, "prompt": "a"},
        {"agent_id": 2, "prompt": "b"},
    ])
    assert ok is True
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "cmd1.json").read_text(encoding="utf-8"))
    assert resp["status"] == "completed"
    assert resp["result"]["interviews_count"] == 2
    # JSON serialisiert int-Keys zu Strings — das ist das Original-Verhalten.
    assert set(resp["result"]["results"].keys()) == {"1", "2"}


@pytest.mark.asyncio
async def test_handle_batch_interview_no_valid_agents(tmp_path: Path):
    handler = _make_handler(tmp_path, agent_graph=FakeAgentGraph(set()))
    ok = await handler.handle_batch_interview("cmd1", [{"agent_id": 9, "prompt": "x"}])
    assert ok is False
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "cmd1.json").read_text(encoding="utf-8"))
    assert resp["status"] == "failed"
    assert resp["error"] == "No valid Agents"


def test_get_interview_result_no_db(tmp_path: Path):
    handler = _make_handler(tmp_path, db_filename="reddit_simulation.db")
    result = handler._get_interview_result(42)
    assert result == {"agent_id": 42, "response": None, "timestamp": None}
    # db_filename drives the path — assert it is respected.
    assert handler.db_filename == "reddit_simulation.db"


def test_get_interview_result_reads_db(tmp_path: Path):
    handler = _make_handler(tmp_path, db_filename="twitter_simulation.db")
    conn = sqlite3.connect(tmp_path / "twitter_simulation.db")
    conn.execute(
        "CREATE TABLE trace (user_id INTEGER, info TEXT, created_at TEXT, action TEXT)"
    )
    conn.execute(
        "INSERT INTO trace (user_id, info, created_at, action) VALUES (?, ?, ?, ?)",
        (5, json.dumps({"response": "hallo"}), "2026-01-01T00:00:00", INTERVIEW_VALUE),
    )
    conn.commit()
    conn.close()
    result = handler._get_interview_result(5)
    assert result["agent_id"] == 5
    assert result["response"] == "hallo"
    assert result["timestamp"] == "2026-01-01T00:00:00"


@pytest.mark.asyncio
async def test_execute_command_interview_returns_true(tmp_path: Path):
    handler = _make_handler(tmp_path, agent_graph=FakeAgentGraph({1}))
    assert await handler._execute_command("c1", CommandType.INTERVIEW, {"agent_id": 1, "prompt": "p"}) is True


@pytest.mark.asyncio
async def test_execute_command_batch_returns_true(tmp_path: Path):
    handler = _make_handler(tmp_path, agent_graph=FakeAgentGraph({1}))
    assert await handler._execute_command("c1", CommandType.BATCH_INTERVIEW, {"interviews": []}) is True


@pytest.mark.asyncio
async def test_execute_command_close_env_returns_false(tmp_path: Path):
    handler = _make_handler(tmp_path)
    assert await handler._execute_command("c1", CommandType.CLOSE_ENV, {}) is False
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "c1.json").read_text(encoding="utf-8"))
    assert resp["status"] == "completed"
    assert resp["result"] == {"message": "Environment will close"}


@pytest.mark.asyncio
async def test_execute_command_unknown_returns_true_and_failed(tmp_path: Path):
    handler = _make_handler(tmp_path)
    assert await handler._execute_command("c1", "bogus", {}) is True
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "c1.json").read_text(encoding="utf-8"))
    assert resp["status"] == "failed"
    assert "bogus" in resp["error"]


@pytest.mark.asyncio
async def test_process_commands_no_command_returns_true(tmp_path: Path):
    handler = _make_handler(tmp_path)
    assert await handler.process_commands() is True


@pytest.mark.asyncio
async def test_process_commands_dedup_skips_seen_and_cleans_file(tmp_path: Path):
    handler = _make_handler(tmp_path)
    cmds = tmp_path / IPC_COMMANDS_DIR
    (cmds / "dup.json").write_text(json.dumps({"command_id": "dup", "command_type": "close_env"}), encoding="utf-8")
    handler.seen_command_ids.add("dup")
    # Must NOT dispatch close_env (which would return False) — dedup short-circuits.
    assert await handler.process_commands() is True
    assert not (cmds / "dup.json").exists()


@pytest.mark.asyncio
async def test_process_commands_dispatches_close_env(tmp_path: Path):
    handler = _make_handler(tmp_path)
    cmds = tmp_path / IPC_COMMANDS_DIR
    (cmds / "stop.json").write_text(
        json.dumps({"command_id": "stop", "command_type": CommandType.CLOSE_ENV, "args": {}}),
        encoding="utf-8",
    )
    assert await handler.process_commands() is False
    assert "stop" in handler.seen_command_ids


@pytest.mark.asyncio
async def test_dispatch_bus_event_no_command_id_returns(tmp_path: Path):
    handler = _make_handler(tmp_path)
    # No correlation_id, no command_id — must not raise and must not dispatch.
    await handler.dispatch_bus_event({"type": CommandType.INTERVIEW, "payload": {}})
    assert handler.seen_command_ids == set()


@pytest.mark.asyncio
async def test_dispatch_bus_event_dedup_skips_seen(tmp_path: Path):
    handler = _make_handler(tmp_path)
    handler.seen_command_ids.add("already")
    await handler.dispatch_bus_event({"correlation_id": "already", "type": CommandType.CLOSE_ENV, "payload": {}})
    # CLOSE_ENV would return False if dispatched; dedup must prevent it.
    assert os.listdir(tmp_path / IPC_RESPONSES_DIR) == []


@pytest.mark.asyncio
async def test_dispatch_bus_event_correlation_id_fallback(tmp_path: Path):
    handler = _make_handler(tmp_path, agent_graph=FakeAgentGraph({3}))
    # correlation_id missing → fall back to command_id.
    await handler.dispatch_bus_event({
        "command_id": "via-cmd",
        "type": CommandType.INTERVIEW,
        "payload": {"agent_id": 3, "prompt": "p"},
    })
    assert "via-cmd" in handler.seen_command_ids
    resp = json.loads((tmp_path / IPC_RESPONSES_DIR / "via-cmd.json").read_text(encoding="utf-8"))
    assert resp["status"] == "completed"


@pytest.mark.asyncio
async def test_file_then_redis_dedup(tmp_path: Path):
    """File polling first, then Redis bridge delivers the same id → no double dispatch."""
    handler = _make_handler(tmp_path, agent_graph=FakeAgentGraph({1}))
    cmds = tmp_path / IPC_COMMANDS_DIR
    (cmds / "shared.json").write_text(
        json.dumps({"command_id": "shared", "command_type": CommandType.INTERVIEW, "args": {"agent_id": 1, "prompt": "p"}}),
        encoding="utf-8",
    )
    assert await handler.process_commands() is True
    responses_before = set(os.listdir(tmp_path / IPC_RESPONSES_DIR))
    # Redis delivers the same id after file polling already handled it.
    await handler.dispatch_bus_event({"correlation_id": "shared", "type": CommandType.INTERVIEW, "payload": {"agent_id": 1, "prompt": "p"}})
    assert set(os.listdir(tmp_path / IPC_RESPONSES_DIR)) == responses_before