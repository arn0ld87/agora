"""Obergrenze je Aktivierung für Simulationsagenten (#1779, Schritt 2.4).

OASIS/CAMEL führt in dem einen Modellaufruf einer Aktivierung **alle** vom
Modell zurückgegebenen Tool-Calls aus (``camel/agents/chat_agent.py``,
Schleife ``for tool_call_request in tool_call_requests``). Es gibt keine
Obergrenze; gemessen wurden im Median fünf Aktionen je Aktivierung. Das
Aktivitätsmodell (``app/services/simulation_activity_model.py``) legt je
Aktivierung höchstens ``max_text_actions_per_activation`` Textaktionen und
``max_reactions_per_activation`` Reaktionen fest. Ein Satz im Profiltext
macht die Grenzen dem Modell bekannt, durchgesetzt werden sie hier.

Eingriff ohne Patch an OASIS oder CAMEL: Jede Aktion ist beim Agenten ein
``FunctionTool`` in ``agent.tool_dict`` (CAMEL ``ChatAgent._internal_tools``),
dessen ``func`` die Methode von ``SocialAction`` ist. CAMEL ruft sie über
``tool.async_call`` bzw. ``await tool.func(**args)``. ``install_activation_limits``
tauscht ``func`` der begrenzten Aktionen gegen einen Umschlag mit gleichem
Namen und gleicher Signatur (``functools.wraps``). Der Umschlag zählt je
Aktivierung und führt überzählige Aufrufe **nicht aus**: das Modell erhält
stattdessen ``{"success": False, "error": "limit reached: ..."}``.

Der Zähler gilt nur zwischen ``ActivationLimits.begin_round()`` und
``end_round()``, also genau um ``env.step``. Startbeiträge
(``ManualAction``) laufen nicht über die Tools; Interviews finden nach der
Runde statt, wenn der Zähler abgeschaltet ist.
"""

from __future__ import annotations

import functools
import inspect
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Mapping, NamedTuple, Optional

from app.contracts.simulation_activity_contract import ActivityModelConfig
from app.services.simulation_activity_model import (
    REACTION_ACTION_NAMES,
    TEXT_ACTION_NAMES,
    activity_limits_sentence,
    activity_model_from_time_config,
)

logger = logging.getLogger(__name__)

KIND_TEXT = "text"
KIND_REACTION = "reaction"
_MARKER = "_agora_activation_limited"


class ActivationLimiter:
    """Zähler eines Agenten für eine Aktivierung."""

    def __init__(self, max_text: int, max_reactions: int) -> None:
        self.max_text = max_text
        self.max_reactions = max_reactions
        self.armed = False
        self.text_used = 0
        self.reactions_used = 0
        self.blocked_text = 0
        self.blocked_reactions = 0

    def reset(self) -> None:
        """Beginnt eine Aktivierung: Zähler auf null, Begrenzung aktiv."""
        self.armed = True
        self.text_used = 0
        self.reactions_used = 0
        self.blocked_text = 0
        self.blocked_reactions = 0

    def disarm(self) -> None:
        """Beendet die Aktivierung: außerhalb der Runde wird nichts begrenzt."""
        self.armed = False

    def acquire(self, kind: str) -> bool:
        """Verbraucht einen Platz; ``False``, wenn die Grenze erreicht ist."""
        if not self.armed:
            return True
        if kind == KIND_TEXT:
            if self.text_used < self.max_text:
                self.text_used += 1
                return True
            self.blocked_text += 1
            return False
        if self.reactions_used < self.max_reactions:
            self.reactions_used += 1
            return True
        self.blocked_reactions += 1
        return False

    def refusal(self, kind: str) -> Dict[str, Any]:
        """Rückmeldung an das Modell für eine nicht ausgeführte Aktion."""
        if kind == KIND_TEXT:
            what, limit = "text actions (post, comment, quote)", self.max_text
        else:
            what, limit = "reactions (like, dislike, repost, follow, mute)", self.max_reactions
        return {
            "success": False,
            "error": (
                f"limit reached: at most {limit} {what} per activation; "
                "this action was not executed"
            ),
        }


def _limited(func: Callable[..., Any], kind: str, limiter: ActivationLimiter) -> Callable[..., Any]:
    """Umschlag um eine Aktionsfunktion; Name, Signatur und Async-Art bleiben."""
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def limited_async(*args: Any, **kwargs: Any) -> Any:
            if not limiter.acquire(kind):
                return limiter.refusal(kind)
            return await func(*args, **kwargs)

        setattr(limited_async, _MARKER, True)
        return limited_async

    @functools.wraps(func)
    def limited_sync(*args: Any, **kwargs: Any) -> Any:
        if not limiter.acquire(kind):
            return limiter.refusal(kind)
        return func(*args, **kwargs)

    setattr(limited_sync, _MARKER, True)
    return limited_sync


def _kind_of(action_name: str) -> Optional[str]:
    if action_name in TEXT_ACTION_NAMES:
        return KIND_TEXT
    if action_name in REACTION_ACTION_NAMES:
        return KIND_REACTION
    return None


class RoundLimitSummary(NamedTuple):
    """Zahl der in einer Runde nicht ausgeführten Aktionen."""

    agents: int
    blocked_agents: int
    blocked_text: int
    blocked_reactions: int


class ActivationLimits:
    """Alle Zähler einer Plattform; wird um ``env.step`` herum ein- und ausgeschaltet."""

    def __init__(self, limiters: Dict[Any, ActivationLimiter], log: Callable[[str], None]) -> None:
        self._limiters = limiters
        self._log = log

    @property
    def agent_count(self) -> int:
        return len(self._limiters)

    def begin_round(self) -> None:
        """Vor ``env.step``: alle Zähler auf null und aktiv."""
        for limiter in self._limiters.values():
            limiter.reset()

    def end_round(self, round_num: int) -> RoundLimitSummary:
        """Nach ``env.step``: Zähler abschalten und die Runde als Logzeile ausweisen."""
        blocked_agents = blocked_text = blocked_reactions = 0
        for limiter in self._limiters.values():
            limiter.disarm()
            if limiter.blocked_text or limiter.blocked_reactions:
                blocked_agents += 1
            blocked_text += limiter.blocked_text
            blocked_reactions += limiter.blocked_reactions
        summary = RoundLimitSummary(
            agents=len(self._limiters),
            blocked_agents=blocked_agents,
            blocked_text=blocked_text,
            blocked_reactions=blocked_reactions,
        )
        self._log(
            "[activation-limit] "
            f"round={round_num} agents={summary.agents} blocked_agents={blocked_agents} "
            f"blocked_text={blocked_text} blocked_reactions={blocked_reactions}"
        )
        return summary


def install_activation_limits(
    agent_graph: Any,
    model: Optional[ActivityModelConfig],
    *,
    log: Optional[Callable[[str], None]] = None,
) -> Optional[ActivationLimits]:
    """Umhüllt die begrenzten Aktions-Tools jedes Agenten; ``None`` ohne Modell.

    Ohne Aktivitätsmodell (Altkonfiguration) bleibt alles beim bisherigen
    Verhalten. Ein Agent, bei dem kein Tool umhüllt werden konnte, wird
    gemeldet, weil für ihn die Grenze nicht gilt.
    """
    emit = log or logger.info
    if model is None or agent_graph is None:
        return None
    try:
        agents = list(agent_graph.get_agents())
    except Exception as exc:  # noqa: BLE001 — Begrenzung ist Zusatz, kein Laufabbruch
        emit(f"[activation-limit] not installed, get_agents failed: {exc}")
        return None
    limiters: Dict[Any, ActivationLimiter] = {}
    bindings = unprotected = 0
    for agent_id, agent in agents:
        limiter = ActivationLimiter(
            model.max_text_actions_per_activation, model.max_reactions_per_activation
        )
        wrapped = _wrap_agent_tools(agent, limiter)
        limiters[agent_id] = limiter
        bindings += wrapped
        if wrapped == 0:
            unprotected += 1
    line = (
        f"[activation-limit] text<={model.max_text_actions_per_activation} "
        f"reactions<={model.max_reactions_per_activation} per activation: "
        f"{bindings} tool binding(s) on {len(limiters) - unprotected} agent(s)"
    )
    if unprotected:
        line += f"; {unprotected} agent(s) WITHOUT enforcement (no action tool found)"
    emit(line)
    return ActivationLimits(limiters, emit)


def install_activation_limits_from_config(
    agent_graph: Any,
    config: Mapping[str, Any],
    *,
    log: Optional[Callable[[str], None]] = None,
) -> Optional[ActivationLimits]:
    """Wie :func:`install_activation_limits`, mit dem Modell aus der Konfiguration."""
    model = activity_model_from_time_config(config.get("time_config") or {})
    return install_activation_limits(agent_graph, model, log=log)


def append_activity_limits_to_prompts(
    agent_graph: Any,
    config: Mapping[str, Any],
    *,
    log: Optional[Callable[[str], None]] = None,
) -> int:
    """Hängt den Grenzen-Satz an die System-Nachricht jedes Agenten; Zahl der Agenten.

    Für den Single-Platform-Runner, der die Profildatei nicht umschreibt (der
    Parallel-Runner trägt den Satz über ``augment_profile_with_stance`` ein).
    CAMEL legt die System-Nachricht beim Aufbau als Snapshot in den Speicher;
    deshalb wird wie in ``attach_tools_to_agents`` die lebende Nachricht, die
    Originalnachricht und danach ``init_messages`` angepasst.
    """
    emit = log or logger.info
    sentence = activity_limits_sentence(config)
    if not sentence or agent_graph is None:
        return 0
    note = f"\n## Deine Aktivität\n{sentence}\n"
    patched = 0
    for agent_id, agent in list(agent_graph.get_agents()):
        try:
            for message in (getattr(agent, "system_message", None), getattr(agent, "_original_system_message", None)):
                if message is not None and hasattr(message, "content") and note not in message.content:
                    message.content = message.content + note
            if hasattr(agent, "init_messages"):
                agent.init_messages()
            patched += 1
        except Exception as exc:  # noqa: BLE001 — Prompt-Satz ist Zusatz, die Durchsetzung bleibt
            emit(f"[activation-limit] prompt note failed for agent {agent_id}: {exc}")
    emit(f"[activation-limit] prompt note added for {patched} agent(s)")
    return patched


@contextmanager
def round_activation_limits(limits: Optional[ActivationLimits], round_num: int) -> Iterator[None]:
    """Begrenzung um ``env.step`` einer Runde; ohne ``limits`` ohne Wirkung."""
    if limits is None:
        yield
        return
    limits.begin_round()
    try:
        yield
    finally:
        limits.end_round(round_num)


def _wrap_agent_tools(agent: Any, limiter: ActivationLimiter) -> int:
    """Tauscht ``func`` der begrenzten Aktions-Tools eines Agenten; Zahl der Umschläge."""
    tools = getattr(agent, "tool_dict", None)
    if not isinstance(tools, dict):
        return 0
    wrapped = 0
    for name, tool in list(tools.items()):
        kind = _kind_of(name)
        func = getattr(tool, "func", None)
        if kind is None or func is None:
            continue
        if getattr(func, _MARKER, False):
            # Erneute Installation: vom Original aus neu umhüllen, nie doppelt.
            func = func.__wrapped__
        tool.func = _limited(func, kind, limiter)
        wrapped += 1
    return wrapped
