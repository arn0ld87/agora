"""Agentengedaechtnis begrenzen (#1772).

Die Tests nutzen die echten CAMEL-Klassen (``ChatHistoryMemory``,
``ScoreBasedContextCreator``, ``MemoryRecord``, ``FunctionCallingMessage``)
aus dem venv; nur der Token-Zaehler ist ein einfacher Zeichenzaehler, damit
kein tiktoken-Download noetig ist. Kein LLM, kein Netz.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, List

import pytest
from camel.memories import ChatHistoryMemory, MemoryRecord, ScoreBasedContextCreator
from camel.messages import BaseMessage, FunctionCallingMessage
from camel.types import OpenAIBackendRole
from camel.utils import BaseTokenCounter

from app.services.run_budget import BudgetExceededError

# backend/scripts auf sys.path, wie zur Laufzeit des OASIS-Subprozesses.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

agent_memory = importlib.import_module("agent_memory")
agent_tools = importlib.import_module("agent_tools")


class _CharCounter(BaseTokenCounter):
    """4 Zeichen = 1 Token; reicht fuer Groessenvergleiche ohne tiktoken."""

    def count_tokens_from_messages(self, messages: List[Any]) -> int:
        return sum(len(str(m.get("content") or "")) + len(str(m.get("tool_calls") or "")) for m in messages) // 4

    def encode(self, text: str) -> List[int]:
        return list(range(len(text) // 4))

    def decode(self, token_ids: List[int]) -> str:
        return "x" * (4 * len(token_ids))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (agent_memory.ENV_PRUNE_FEEDS, agent_memory.ENV_KEEP_FEEDS, agent_memory.ENV_TOKEN_CAP):
        monkeypatch.delenv(name, raising=False)


# --- Hilfen: Gedaechtnis wie OASIS/CAMEL es fuellt --------------------------------


def _new_memory(token_limit: int = 262_144) -> ChatHistoryMemory:
    creator = ScoreBasedContextCreator(_CharCounter(), token_limit)
    memory = ChatHistoryMemory(creator, agent_id="agent-1")
    system = BaseMessage.make_assistant_message(role_name="system", content="You are persona X.")
    memory.write_records([MemoryRecord(message=system, role_at_backend=OpenAIBackendRole.SYSTEM)])
    return memory


def _feed_text(number: int, size: int) -> str:
    body = f"[feed #{number}] " + ("post-json " * size)
    return f"{agent_memory.FEED_MESSAGE_PREFIX} the platform environments. Here is your social media environment: {body}"


def _write_activation(memory: ChatHistoryMemory, number: int, feed_size: int = 200) -> List[str]:
    """Schreibt Feed, Tool-Call, Tool-Ergebnis und Textantwort einer Aktivierung.

    Gibt die UUIDs der *eigenen* Datensaetze (Tool-Call, Ergebnis, Antwort) zurueck.
    """
    call_id = f"call_{number}"
    feed = BaseMessage.make_user_message(role_name="User", content=_feed_text(number, feed_size))
    tool_call = FunctionCallingMessage(
        role_name="assistant",
        role_type=feed.role_type,
        meta_dict=None,
        content="",
        func_name="create_comment",
        args={"post_id": number, "content": f"my comment {number}"},
        tool_call_id=call_id,
    )
    tool_result = FunctionCallingMessage(
        role_name="assistant",
        role_type=feed.role_type,
        meta_dict=None,
        content="",
        func_name="create_comment",
        result={"success": True, "comment_id": number},
        tool_call_id=call_id,
    )
    answer = BaseMessage.make_assistant_message(role_name="assistant", content=f"done {number}")
    own = [
        MemoryRecord(message=tool_call, role_at_backend=OpenAIBackendRole.ASSISTANT),
        MemoryRecord(message=tool_result, role_at_backend=OpenAIBackendRole.FUNCTION),
        MemoryRecord(message=answer, role_at_backend=OpenAIBackendRole.ASSISTANT),
    ]
    memory.write_records([MemoryRecord(message=feed, role_at_backend=OpenAIBackendRole.USER), *own])
    return [str(r.uuid) for r in own]


def _records(memory: ChatHistoryMemory) -> List[MemoryRecord]:
    return [c.memory_record for c in memory.retrieve()]


def _role(record: MemoryRecord) -> str:
    return record.role_at_backend.value


def _feed_contents(memory: ChatHistoryMemory) -> List[str]:
    return [r.message.content for r in _records(memory) if _role(r) == "user"]


class _Agent:
    def __init__(self, memory: Any) -> None:
        self.memory = memory


class _Graph:
    def __init__(self, memories: List[Any]) -> None:
        self._agents = [(i, _Agent(m)) for i, m in enumerate(memories)]

    def get_agents(self) -> List[Any]:
        return self._agents


# --- Feed-Pruning --------------------------------------------------------------------


def test_prune_replaces_old_feeds_and_keeps_own_actions() -> None:
    memory = _new_memory()
    own_uuids: List[str] = []
    for n in range(1, 7):
        own_uuids += _write_activation(memory, n)
    before = _records(memory)

    result = agent_memory.prune_memory_feeds(memory, keep_feeds=2)

    after = _records(memory)
    assert result.replaced == 4
    assert result.tokens_after < result.tokens_before
    assert len(after) == len(before)
    # System vorn, unveraendert.
    assert _role(after[0]) == "system"
    assert after[0].message.content == before[0].message.content
    # Feeds der aeltesten vier Aktivierungen sind Platzhalter, die letzten zwei voll.
    feeds = _feed_contents(memory)
    assert [f.startswith(agent_memory.FEED_PLACEHOLDER_PREFIX) for f in feeds] == [True] * 4 + [False] * 2
    assert "#3 was removed" in feeds[2]
    assert feeds[4] == _feed_text(5, 200) and feeds[5] == _feed_text(6, 200)
    # Alle eigenen Aktionen unveraendert (UUID, Reihenfolge, Inhalt).
    own_after = [r for r in after if _role(r) != "user" and _role(r) != "system"]
    assert [str(r.uuid) for r in own_after] == own_uuids
    assert [r.to_dict() for r in own_after] == [
        r.to_dict() for r in before if _role(r) not in ("user", "system")
    ]
    # Rollenfolge bleibt erhalten (Feed wird ersetzt, nicht entfernt).
    assert [_role(r) for r in after] == [_role(r) for r in before]


def test_prune_never_splits_tool_call_from_tool_result() -> None:
    memory = _new_memory()
    for n in range(1, 8):
        _write_activation(memory, n)
    agent_memory.prune_memory_feeds(memory, keep_feeds=1)

    calls: dict = {}
    for record in _records(memory):
        call_id = getattr(record.message, "tool_call_id", None)
        if not call_id:
            continue
        kind = "call" if record.message.args is not None else "result"
        calls.setdefault(call_id, []).append(kind)
    assert len(calls) == 7
    assert all(sorted(kinds) == ["call", "result"] for kinds in calls.values())
    # Und CAMEL baut daraus weiterhin einen gueltigen Kontext.
    messages, _ = memory.get_context()
    assert messages[0]["role"] == "system"


def test_prune_keeps_current_feed_unchanged() -> None:
    memory = _new_memory()
    for n in range(1, 4):
        _write_activation(memory, n)
    agent_memory.prune_memory_feeds(memory, keep_feeds=1)
    assert _feed_contents(memory)[-1] == _feed_text(3, 200)


def test_prune_is_idempotent_and_does_not_touch_other_user_messages() -> None:
    memory = _new_memory()
    for n in range(1, 5):
        _write_activation(memory, n)
    interview = BaseMessage.make_user_message(role_name="User", content="Interview answer, not a feed.")
    memory.write_records([MemoryRecord(message=interview, role_at_backend=OpenAIBackendRole.USER)])

    first = agent_memory.prune_memory_feeds(memory, keep_feeds=1)
    snapshot = [r.to_dict() for r in _records(memory)]
    second = agent_memory.prune_memory_feeds(memory, keep_feeds=1)

    assert first.replaced == 3
    assert second.replaced == 0
    assert [r.to_dict() for r in _records(memory)] == snapshot
    assert "Interview answer, not a feed." in _feed_contents(memory)


def test_prune_with_fewer_activations_than_keep_changes_nothing() -> None:
    memory = _new_memory()
    for n in range(1, 4):
        _write_activation(memory, n)
    snapshot = [r.to_dict() for r in _records(memory)]
    assert agent_memory.prune_memory_feeds(memory, keep_feeds=4).replaced == 0
    assert [r.to_dict() for r in _records(memory)] == snapshot


def test_budget_aware_pruning_makes_room_for_the_next_feed() -> None:
    # Jeder Feed ~2.000 geschaetzte Tokens (6.000 Zeichen / 3); Obergrenze 8.192.
    memory = _new_memory(token_limit=8_192)
    for n in range(1, 5):
        _write_activation(memory, n, feed_size=600)
    without_cap = agent_memory.prune_memory_feeds(_clone(memory), keep_feeds=4, token_cap=0)
    with_cap = agent_memory.prune_memory_feeds(memory, keep_feeds=4, token_cap=8_192)

    assert without_cap.replaced == 0
    assert with_cap.replaced >= 1
    # Danach passt ein weiterer Feed in der Groesse des groessten bisherigen unter die Obergrenze.
    assert with_cap.tokens_after + 2_000 <= 8_192 + 100


def _clone(memory: ChatHistoryMemory) -> ChatHistoryMemory:
    twin = _new_memory()
    twin.clear()
    twin.write_records(_records(memory))
    return twin


# --- Rundenhook: Schalter, Fehlertoleranz, Sichtbarkeit -----------------------------------


def test_round_hook_is_disabled_by_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(agent_memory.ENV_PRUNE_FEEDS, "false")
    memory = _new_memory()
    for n in range(1, 8):
        _write_activation(memory, n)
    snapshot = [r.to_dict() for r in _records(memory)]
    logged: List[str] = []

    assert agent_memory.prune_graph_memories(_Graph([memory]), round_num=7, log=logged.append) is None

    assert [r.to_dict() for r in _records(memory)] == snapshot
    assert logged == []


def test_round_hook_uses_env_keep_and_logs_one_summary_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(agent_memory.ENV_KEEP_FEEDS, "2")
    memories = [_new_memory() for _ in range(3)]
    for memory in memories:
        for n in range(1, 7):
            _write_activation(memory, n)
    logged: List[str] = []

    summary = agent_memory.prune_graph_memories(_Graph(memories), round_num=6, log=logged.append)

    assert summary is not None
    assert (summary.agents_changed, summary.replaced, summary.failures) == (3, 12, 0)
    assert len(logged) == 1
    assert "round 6" in logged[0] and "replaced 12" in logged[0] and "3 agent(s)" in logged[0]
    # Eine zweite Runde ohne neue Aktivierung loggt nichts mehr.
    assert agent_memory.prune_graph_memories(_Graph(memories), round_num=7, log=logged.append).replaced == 0
    assert len(logged) == 1


class _BrokenMemory:
    def retrieve(self) -> List[Any]:
        raise RuntimeError("storage unavailable")


def test_pruning_error_in_one_agent_leaves_others_untouched_and_does_not_abort() -> None:
    good_a, good_b = _new_memory(), _new_memory()
    for memory in (good_a, good_b):
        for n in range(1, 8):
            _write_activation(memory, n)
    logged: List[str] = []

    summary = agent_memory.prune_graph_memories(
        _Graph([good_a, _BrokenMemory(), good_b]), round_num=3, log=logged.append
    )

    assert summary is not None
    assert summary.failures == 1
    assert summary.agents_changed == 2
    assert len(logged) == 1
    assert "1 agent(s) left unchanged after errors" in logged[0]
    assert "storage unavailable" in logged[0]
    for memory in (good_a, good_b):
        assert sum(f.startswith(agent_memory.FEED_PLACEHOLDER_PREFIX) for f in _feed_contents(memory)) == 3


def test_failed_rewrite_restores_original_memory() -> None:
    memory = _new_memory()
    for n in range(1, 7):
        _write_activation(memory, n)
    snapshot = [r.to_dict() for r in _records(memory)]
    real_write = memory.write_records
    calls = {"n": 0}

    def flaky_write(records: List[MemoryRecord]) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        real_write(records)

    memory.write_records = flaky_write  # type: ignore[method-assign]

    with pytest.raises(OSError):
        agent_memory.prune_memory_feeds(memory, keep_feeds=1)

    assert [r.to_dict() for r in _records(memory)] == snapshot


def test_budget_exceeded_is_not_swallowed() -> None:
    class _BudgetMemory:
        def retrieve(self) -> List[Any]:
            raise BudgetExceededError("tokens", 10, 5)

    with pytest.raises(BudgetExceededError):
        agent_memory.prune_graph_memories(_Graph([_BudgetMemory()]), round_num=1, log=lambda _m: None)


def test_policy_line_names_active_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    assert agent_memory.describe_memory_policy() == (
        "Agent memory limits: feed pruning = feeds of older activations replaced (keep last 4); "
        "memory token cap = 32000 tokens"
    )
    monkeypatch.setenv(agent_memory.ENV_PRUNE_FEEDS, "0")
    monkeypatch.setenv(agent_memory.ENV_TOKEN_CAP, "0")
    assert agent_memory.describe_memory_policy() == (
        "Agent memory limits: feed pruning = off; memory token cap = off"
    )


def test_feed_marker_matches_installed_oasis_source() -> None:
    """Drift-Schutz: die Feed-Erkennung haengt am Text aus OASIS' perform_action_by_llm."""
    spec = importlib.util.find_spec("oasis")
    assert spec is not None and spec.origin is not None
    source = (Path(spec.origin).parent / "social_agent" / "agent.py").read_text(encoding="utf-8")
    assert agent_memory.FEED_MESSAGE_PREFIX in source


# --- Obergrenze fuer das Token-Limit -----------------------------------------------------------


class _Creator:
    def __init__(self, limit: int) -> None:
        self._token_limit = limit

    @property
    def token_limit(self) -> int:
        return self._token_limit


class _FakeMemory:
    def __init__(self, limit: int) -> None:
        self.creator = _Creator(limit)

    def get_context_creator(self) -> _Creator:
        return self.creator


class _FakeAgent:
    def __init__(self, limit: int, model: str = "unknown-model") -> None:
        self.memory = _FakeMemory(limit)
        self.model_backend = type("Backend", (), {"model_type": model})()


def _enforce(limit: int, monkeypatch: pytest.MonkeyPatch, context_limit: str = "262144", model: str = "unknown-model") -> int:
    monkeypatch.setenv("LLM_CONTEXT_LIMIT", context_limit)
    monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
    agent = _FakeAgent(limit, model)
    graph = _Graph([])
    graph._agents = [(0, agent)]
    agent_tools.enforce_memory_token_limit(graph)
    return agent.memory.creator.token_limit


def test_cap_applies_when_camel_falls_back_to_unbounded_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # ModelType.token_limit liefert 999_999_999 fuer Modelle mit max_completion_tokens.
    assert _enforce(999_999_999, monkeypatch) == 32_000


def test_cap_lowers_the_floor_raised_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # apply_camel_context_floor setzt neue Creator auf 262144; die Obergrenze zieht sie herunter.
    assert _enforce(262_144, monkeypatch) == 32_000


def test_floor_still_raises_small_limits_but_never_above_the_resolved_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _enforce(8_192, monkeypatch) == 32_000
    # Kleineres aufgeloestes Modell-Budget als die Obergrenze: das Budget gewinnt, Floor gilt weiter.
    assert _enforce(8_192, monkeypatch, context_limit="16000") == 16_000


def test_cap_env_override_and_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(agent_memory.ENV_TOKEN_CAP, "64000")
    assert _enforce(999_999_999, monkeypatch) == 64_000
    monkeypatch.setenv(agent_memory.ENV_TOKEN_CAP, "0")
    # Aus: altes Verhalten, ein zu grosses Limit bleibt stehen, ein zu kleines wird angehoben.
    assert _enforce(999_999_999, monkeypatch) == 999_999_999
    assert _enforce(8_192, monkeypatch) == 262_144


def test_cap_never_drops_below_camel_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(agent_memory.ENV_TOKEN_CAP, "1000")
    assert agent_memory.resolve_memory_token_cap() == agent_memory.MIN_MEMORY_TOKEN_CAP
    monkeypatch.setenv(agent_memory.ENV_TOKEN_CAP, "not-a-number")
    assert agent_memory.resolve_memory_token_cap() == agent_memory.DEFAULT_MEMORY_TOKEN_CAP


def test_cap_applies_to_attach_tools_to_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "262144")
    monkeypatch.setenv("LLM_MODEL_CONTEXT_LIMITS_JSON", '{"big-model": 1048576}')

    class _Tool:
        name = "web_search"

    class _AttachAgent(_FakeAgent):
        def __init__(self) -> None:
            super().__init__(8_192, "big-model")
            self.system_message = type("M", (), {"content": "persona"})()
            self._original_system_message = type("M", (), {"content": "persona"})()
            self.max_iteration = 1
            self.tool_dict: dict = {}

        def add_tool(self, tool: Any) -> None:
            self.tool_dict[tool.name] = tool

        def init_messages(self) -> None:
            return None

    agent = _AttachAgent()
    graph = _Graph([])
    graph._agents = [(0, agent)]

    assert agent_tools.attach_tools_to_agents(graph, [_Tool()]) == 1
    assert agent.memory.creator.token_limit == 32_000

    monkeypatch.setenv(agent_memory.ENV_TOKEN_CAP, "0")
    agent_tools.attach_tools_to_agents(graph, [_Tool()])
    assert agent.memory.creator.token_limit == 1_048_576


def test_cap_applies_to_real_context_creator(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = ChatHistoryMemory(ScoreBasedContextCreator(_CharCounter(), 999_999_999), agent_id="a")
    agent = _Agent(memory)
    agent.model_backend = type("B", (), {"model_type": "x"})()  # type: ignore[attr-defined]
    monkeypatch.setenv("LLM_CONTEXT_LIMIT", "262144")
    graph = _Graph([])
    graph._agents = [(0, agent)]

    assert agent_tools.enforce_memory_token_limit(graph) == 1
    assert memory.get_context_creator().token_limit == 32_000


# --- Wirkung ----------------------------------------------------------------------------------


def _simulate_run(rounds: int, *, prune: bool, feed_size: int = 500) -> List[int]:
    """Ein Agent wird in jeder Runde aktiviert; liefert die Prompt-Groesse je Schritt."""
    memory = _new_memory()
    prompt_tokens: List[int] = []
    for n in range(1, rounds + 1):
        _write_activation(memory, n, feed_size=feed_size)
        _, tokens = memory.get_context()
        prompt_tokens.append(tokens)
        if prune:
            agent_memory.prune_memory_feeds(memory, keep_feeds=agent_memory.DEFAULT_KEEP_FEEDS)
    return prompt_tokens


def test_pruning_turns_quadratic_prompt_growth_into_a_plateau() -> None:
    rounds = 24
    unpruned = _simulate_run(rounds, prune=False)
    pruned = _simulate_run(rounds, prune=True)

    total_ratio = sum(unpruned) / sum(pruned)
    last_ratio = unpruned[-1] / pruned[-1]
    # Gemessen (Feed ~1.300 Tokens, vier behaltene Feeds): ohne Pruning 1.329 -> 31.804 Tokens je
    # Schritt (linear, Summe 397.596), mit Pruning 1.329 -> 8.007 (Plateau, Summe 159.581).
    assert unpruned[-1] > 5 * unpruned[3]
    assert pruned[-1] < 1.2 * pruned[11]
    # Pruning wirkt erst ab der fuenften Aktivierung; ueber 24 Runden faellt die Summe um ~2,5x,
    # der letzte Schritt um ~4x, und das Verhaeltnis waechst mit jeder weiteren Runde.
    assert total_ratio >= 2.4, f"expected total prompt tokens to shrink >= 2.4x, got {total_ratio:.2f}x"
    assert last_ratio >= 3.5, f"expected last prompt to shrink >= 3.5x, got {last_ratio:.2f}x"
