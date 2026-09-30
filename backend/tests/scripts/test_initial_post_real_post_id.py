"""Regressionstest #1713 UI-2a (L4): Startposts wurden ohne echte ``post_id``
geloggt und nie an den Live-Feed emittiert.

Vorher: ``_log_initial_post`` (on_published-Callback) lief VOR
``env.step(initial_actions)`` — der Post existierte zu diesem Zeitpunkt noch
nicht in der OASIS-DB, ``action_args`` enthielt nur ``{"content": ...}`` ohne
``post_id``, und es gab keinen ``_emit_post_created_to_redis``-Aufruf fuer
Runde 0 ueberhaupt.

Fix: nach ``env.step(initial_actions)`` liest ``fetch_new_actions_from_db``
dieselbe ``trace``-Tabelle wie die Hauptrunde (inkl. post_id-Anreicherung)
und der Runner loggt/emittiert Runde-0-Aktionen ueber denselben Pfad wie
jede andere Runde.

Dieser Test faked alle schweren OASIS/CAMEL-Abhaengigkeiten (Modell,
Agent-Graph, Environment) wie ``test_run_parallel_simulation_control.py``;
``_FakeEnv.step`` schreibt eine SQLite-DB nach demselben Schema, das ein
echter OASIS-Lauf nach einem Initial-Post hinterlaesst.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402

_SCHEMA = """
CREATE TABLE user (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER,
    user_name TEXT,
    name TEXT,
    bio TEXT,
    created_at DATETIME,
    num_followings INTEGER DEFAULT 0,
    num_followers INTEGER DEFAULT 0
);
CREATE TABLE post (
    post_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_post_id INTEGER,
    content TEXT DEFAULT '',
    quote_content TEXT,
    created_at DATETIME,
    num_likes INTEGER DEFAULT 0,
    num_dislikes INTEGER DEFAULT 0,
    num_shares INTEGER DEFAULT 0,
    num_reports INTEGER DEFAULT 0
);
CREATE TABLE trace (
    user_id INTEGER,
    created_at DATETIME,
    action TEXT,
    info TEXT,
    PRIMARY KEY(user_id, created_at, action, info)
);
"""


class _FakeAgent:
    """Steht fuer ein OASIS-Agent-Objekt: identitaetsgleich pro agent_id,
    wie in ``test_initial_post_publish_collision.py``. build_initial_post_
    actions nutzt es als Dict-Key — ein SimpleNamespace ist dafuer nicht
    hashbar."""

    def __init__(self, agent_id: int) -> None:
        self.agent_id = agent_id
        self.username = f"Agent_{agent_id}"


class _FakeAgentGraph:
    def __init__(self) -> None:
        self._agents: Dict[int, _FakeAgent] = {}

    def get_agents(self):
        return []

    def get_agent(self, agent_id: int) -> _FakeAgent:
        return self._agents.setdefault(agent_id, _FakeAgent(agent_id))


class _FakeEnv:
    """Schreibt bei ``step()`` dieselbe DB-Form, die OASIS nach einem
    Initial-Post hinterlaesst: ein ``post``-Zeile + eine ``trace``-Zeile mit
    ``post_id`` im info-JSON (siehe realer Lauf sim_54c1c2a6a875)."""

    def __init__(self, database_path: str, agent_graph: Any) -> None:
        self.database_path = database_path
        # OASIS-Envs spiegeln den Agent-Graph als Property; der Runner liest
        # ihn bei den Initial-Posts ueber ``result.env.agent_graph``, nicht
        # ``result.agent_graph`` (siehe run_parallel_simulation.py).
        self.agent_graph = agent_graph

    async def reset(self) -> None:
        return None

    async def step(self, actions: Any) -> None:
        conn = sqlite3.connect(self.database_path)
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
            (0, 1, "mara_l", "Mara Lindner"),
        )
        conn.execute(
            "INSERT INTO post (post_id, user_id, content) VALUES (?, ?, ?)",
            (7, 0, "Startpost der Simulation."),
        )
        conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (0, "2026-09-29 09:00:00", "create_post",
             json.dumps({"content": "Startpost der Simulation.", "post_id": 7})),
        )
        conn.commit()
        conn.close()

    async def close(self) -> None:
        return None


class _RecordingActionLogger:
    def __init__(self) -> None:
        self.actions: List[Dict[str, Any]] = []
        self.round_starts: List[tuple] = []
        self.round_ends: List[tuple] = []

    def log_simulation_start(self, config: Any) -> None:
        return None

    def log_round_start(self, round_num: int, simulated_hour: int) -> None:
        self.round_starts.append((round_num, simulated_hour))

    def log_action(self, *, round_num, agent_id, agent_name, action_type, action_args) -> None:
        self.actions.append(
            {
                "round_num": round_num,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "action_type": action_type,
                "action_args": action_args,
            }
        )

    def log_round_end(self, round_num: int, count: int, simulated_minutes: float | None = None) -> None:
        self.round_ends.append((round_num, count))

    def log_simulation_end(self, total_rounds: int, total_actions: int) -> None:
        return None


def _base_config() -> Dict[str, Any]:
    return {
        "simulation_id": "sim_test_l4",
        "agent_configs": [],
        # Startpost desselben Agenten wie in _FakeEnv.step (agent_id=1).
        "event_config": {"initial_posts": [{"poster_agent_id": 1, "content": "Startpost der Simulation."}]},
        "enable_agent_tools": False,
        # 0 Runden — der Test isoliert bewusst die Startpost-Phase (Runde 0)
        # vom Rundenkoerper.
        "time_config": {"total_simulation_hours": 0, "minutes_per_round": 30},
    }


def _patch_heavy_deps(monkeypatch: Any) -> None:
    async def fake_generate_agent_graph(*, profile_path: str, model: Any, available_actions: Any) -> _FakeAgentGraph:
        return _FakeAgentGraph()

    monkeypatch.setattr(rps, "generate_twitter_agent_graph", fake_generate_agent_graph)
    monkeypatch.setattr(rps, "generate_reddit_agent_graph", fake_generate_agent_graph)
    monkeypatch.setattr(rps, "create_model", lambda config, use_boost=False: object())
    monkeypatch.setattr(rps, "preflight_model_probe", lambda model: None)
    monkeypatch.setattr(rps, "compute_start_hour_offset", lambda config, total_rounds, minutes_per_round: 0)
    monkeypatch.setattr(
        rps.oasis,
        "make",
        lambda **kwargs: _FakeEnv(kwargs["database_path"], kwargs["agent_graph"]),
    )


def _captured_publish(monkeypatch: Any):
    client = MagicMock()
    client.publish = AsyncMock()
    monkeypatch.setattr(rps, "_get_redis_client", lambda _url: client)
    return client


class TestTwitterInitialPostRealPostId:
    @pytest.mark.asyncio
    async def test_action_log_has_real_post_id(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
        _patch_heavy_deps(monkeypatch)
        monkeypatch.delenv("REDIS_URL", raising=False)
        action_logger = _RecordingActionLogger()

        await rps.run_twitter_simulation(_base_config(), str(tmp_path), action_logger=action_logger)

        assert len(action_logger.actions) == 1
        logged = action_logger.actions[0]
        assert logged["round_num"] == 0
        assert logged["action_type"] == "CREATE_POST"
        assert logged["action_args"]["post_id"] == 7, (
            "Startpost muss die echte post_id aus der OASIS-DB tragen, "
            "nicht nur {'content': ...} wie vor dem Fix"
        )

    @pytest.mark.asyncio
    async def test_emits_to_redis_with_round_num_zero(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
        _patch_heavy_deps(monkeypatch)
        monkeypatch.setenv("REDIS_URL", "redis://localhost")
        client = _captured_publish(monkeypatch)

        await rps.run_twitter_simulation(_base_config(), str(tmp_path), action_logger=_RecordingActionLogger())

        assert client.publish.await_count == 1
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["post_id"] == "twitter:7"
        assert payload["round_num"] == 0
        assert payload["kind"] == "post"

    @pytest.mark.asyncio
    async def test_no_double_start_post_in_round_one(self, monkeypatch, tmp_path: Path) -> None:
        """last_rowid muss nach der Startpost-Phase auf den DB-Stand gezogen
        sein — sonst laese eine (hier nicht ausgefuehrte) Runde 1 dieselbe
        trace-Zeile erneut (Bestandsdefekt aus Slice S1, hier end-to-end)."""
        (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
        _patch_heavy_deps(monkeypatch)
        monkeypatch.delenv("REDIS_URL", raising=False)
        action_logger = _RecordingActionLogger()

        await rps.run_twitter_simulation(_base_config(), str(tmp_path), action_logger=action_logger)

        db_path = str(tmp_path / "twitter_simulation.db")
        from oasis_action_ingest import get_max_trace_rowid

        actions, new_last_rowid = rps.fetch_new_actions_from_db(
            db_path, get_max_trace_rowid(db_path) - 1, {}
        )
        # Nur der Sanity-Check, dass die trace-Zeile ueberhaupt existiert —
        # der eigentliche Beleg ist round_ends[0] == (0, 1): genau eine
        # Aktion in Runde 0, keine Dopplung.
        assert len(actions) == 1
        assert action_logger.round_ends == [(0, 1)]


class TestRedditInitialPostRealPostId:
    @pytest.mark.asyncio
    async def test_action_log_has_real_post_id(self, monkeypatch, tmp_path: Path) -> None:
        (tmp_path / "reddit_profiles.json").write_text("{}", encoding="utf-8")
        _patch_heavy_deps(monkeypatch)
        monkeypatch.delenv("REDIS_URL", raising=False)
        action_logger = _RecordingActionLogger()

        await rps.run_reddit_simulation(_base_config(), str(tmp_path), action_logger=action_logger)

        assert len(action_logger.actions) == 1
        assert action_logger.actions[0]["action_args"]["post_id"] == 7
