"""Unit tests for the shared ``sim_runtime.runtime_execution`` deep module."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from camel.types import ModelPlatformType

from scripts.sim_runtime.runtime_execution import (
    allowed_emit_action_types,
    configure_platform_agent_graph,
    create_simulation_llm_model,
    emit_round_actions_to_redis,
    execute_initial_posts_round,
    resolve_graph_agent_names,
)


class _DummyAgent:
    def __init__(self, agent_id: int, name: str = "", user_name: str = "") -> None:
        self.agent_id = agent_id
        self.user_info = MagicMock()
        self.user_info.name = name or user_name or f"Agent_{agent_id}"
        self.user_info.user_name = user_name
        self.max_iteration = 1
        self.memory = MagicMock()
        self.env = MagicMock()
        self.perform_action_by_data = MagicMock()


class _DummyGraph:
    def __init__(self, agents: List[tuple[int, _DummyAgent]]) -> None:
        self._agents = agents

    def get_agents(self):
        return list(self._agents)

    def get_agent(self, agent_id: int) -> _DummyAgent:
        for aid, agent in self._agents:
            if aid == agent_id:
                return agent
        raise KeyError(agent_id)


def test_allowed_emit_action_types_by_platform() -> None:
    assert allowed_emit_action_types("twitter") == ("CREATE_POST", "REPOST", "QUOTE_POST")
    assert allowed_emit_action_types("reddit") == ("CREATE_POST", "CREATE_COMMENT")


def test_create_simulation_llm_model_openai_and_boost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "common-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-4o-mini")
    monkeypatch.setenv("LLM_BOOST_API_KEY", "boost-key")
    monkeypatch.setenv("LLM_BOOST_BASE_URL", "https://boost.example/v1")
    monkeypatch.setenv("LLM_BOOST_MODEL_NAME", "boost-model")

    factory = MagicMock()
    factory.create.return_value = "created-model"

    res_common = create_simulation_llm_model(
        {},
        use_boost=False,
        model_factory=factory,
        claude_cli_transport_check=lambda: False,
        cli_transport_check=lambda: False,
        workspace_credential_scope_check=lambda: False,
        platform_detector=lambda m, u: ModelPlatformType.OPENAI,
    )
    assert res_common == "created-model"
    assert factory.create.call_args.kwargs["model_type"] == "gpt-4o-mini"
    assert factory.create.call_args.kwargs["api_key"] == "common-key"

    res_boost = create_simulation_llm_model(
        {},
        use_boost=True,
        model_factory=factory,
        claude_cli_transport_check=lambda: False,
        cli_transport_check=lambda: False,
        workspace_credential_scope_check=lambda: False,
        platform_detector=lambda m, u: ModelPlatformType.OPENAI,
    )
    assert res_boost == "created-model"
    assert factory.create.call_args.kwargs["model_type"] == "boost-model"
    assert factory.create.call_args.kwargs["api_key"] == "boost-key"


def test_resolve_graph_agent_names_fills_fallback_from_graph() -> None:
    agent0 = _DummyAgent(0, name="Alice")
    agent1 = _DummyAgent(1, name="Bob")
    graph = _DummyGraph([(0, agent0), (1, agent1)])

    names = resolve_graph_agent_names(
        {"agent_configs": [{"agent_id": 0, "entity_name": "Configured Alice"}]},
        graph,
    )
    assert names[0] == "Configured Alice"
    assert names[1] == "Bob"


def test_configure_platform_agent_graph_binds_limits_and_returns_names() -> None:
    agent0 = _DummyAgent(0, name="Alice")
    graph = _DummyGraph([(0, agent0)])

    limits, names = configure_platform_agent_graph(
        graph,
        {"llm_model": "gpt-4o-mini", "agent_configs": [{"agent_id": 0, "entity_name": "Alice"}]},
        platform_slug="twitter",
    )
    assert names == {0: "Alice"}


def test_emit_round_actions_to_redis_emits_only_allowed_platform_actions() -> None:
    emitted: List[Dict[str, Any]] = []

    async def _fake_emit(**kwargs: Any) -> None:
        emitted.append(kwargs)

    count = asyncio.run(
        emit_round_actions_to_redis(
            actions=[
                {
                    "action_type": "CREATE_POST",
                    "agent_id": 0,
                    "agent_name": "Alice",
                    "action_args": {"content": "Hello world", "post_id": 10},
                },
                {
                    "action_type": "LIKE_POST",
                    "agent_id": 0,
                    "agent_name": "Alice",
                    "action_args": {"post_id": 10},
                },
            ],
            platform_slug="twitter",
            simulation_id="sim_test",
            redis_url="redis://localhost:6379/0",
            round_num=2,
            sim_clock_anchor=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            start_hour_offset=0,
            simulated_minutes=60,
            minutes_per_round=30,
            emit_fn=_fake_emit,
        )
    )

    assert count == 1
    assert len(emitted) == 1
    assert emitted[0]["platform"] == "twitter"
    assert emitted[0]["action_data"]["action_args"]["content"] == "Hello world"
    assert emitted[0]["round_num"] == 2


def test_execute_initial_posts_round_steps_env_and_emits_actions() -> None:
    agent0 = _DummyAgent(0, name="Alice")
    graph = _DummyGraph([(0, agent0)])
    env = MagicMock()
    env.agent_graph = graph

    async def _fake_step(actions):
        return None

    env.step.side_effect = _fake_step

    emitted: List[Dict[str, Any]] = []

    async def _fake_emit(**kwargs: Any) -> None:
        emitted.append(kwargs)

    new_rowid, posted = asyncio.run(
        execute_initial_posts_round(
            env=env,
            config={
                "event_config": {
                    "initial_posts": [{"poster_agent_id": 0, "content": "Kickoff post"}]
                }
            },
            platform_slug="twitter",
            db_path="/tmp/fake.db",
            agent_names={0: "Alice"},
            last_rowid=0,
            action_logger=None,
            simulation_id="sim_init",
            redis_url="redis://localhost:6379/0",
            sim_clock_anchor=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            start_hour_offset=0,
            minutes_per_round=30,
            build_initial_actions_fn=lambda posts, g: ({agent0: "act"}, 1),
            fetch_actions_fn=lambda db, rowid, names: (
                [
                    {
                        "action_type": "CREATE_POST",
                        "agent_id": 0,
                        "agent_name": "Alice",
                        "action_args": {"content": "Kickoff post", "post_id": 1},
                    }
                ],
                7,
            ),
            emit_fn=_fake_emit,
        )
    )

    assert posted == 1
    assert new_rowid == 7
    assert env.step.call_count == 1
    assert len(emitted) == 1
    assert emitted[0]["round_num"] == 0
