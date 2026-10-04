"""Begrenzung des CAMEL-Agentengedächtnisses in der OASIS-Simulation (#1772).

Problem: OASIS legt jeden ``SocialAgent`` ohne ``message_window_size`` an, und
``SocialAgent.perform_action_by_llm`` schreibt bei jeder Aktivierung den
kompletten Feed als USER-Nachricht ins Gedächtnis. Agora hob das Token-Limit
des Gedächtnisses bisher nur an (``apply_camel_context_floor`` in
``_sim_common.py``, ``enforce_memory_token_limit`` in ``agent_tools.py``),
nie ab. Der Prompt je Agentenschritt wuchs dadurch über den Lauf linear mit
der Zahl der bisherigen Aktivierungen, die Summe über den Lauf quadratisch.

Zwei Maßnahmen, beide ohne Eingriff in OASIS/CAMEL:

1. **Feed-Pruning zwischen den Runden** (``prune_graph_memories``): Die
   Feed-Nachrichten früherer Aktivierungen werden durch einen kurzen
   Platzhalter ersetzt. Die eigenen Aktionen des Agenten (Assistant-Nachricht
   mit Tool-Call samt Tool-Ergebnis, Textantwort) bleiben unangetastet. Die
   Nachricht wird ersetzt statt gelöscht, damit die Rollenfolge erhalten
   bleibt (manche Provider lehnen zwei aufeinanderfolgende Assistant-
   Nachrichten ab) und Tool-Call/Tool-Ergebnis-Paare nie zerrissen werden.
2. **Obergrenze für das Gedächtnis-Token-Limit** (``cap_memory_token_limit``):
   getrennt vom Floor, der vor zu kleinen Limits schützt. Die Obergrenze
   schützt vor ungebremstem Wachstum, auch wenn CAMEL für ein Modell auf
   ``999_999_999`` zurückfällt (``ModelType.token_limit``).

Bewusst NICHT verwendet: ``ChatHistoryMemory(window_size=K)``. Das Fenster
schneidet die letzten K Datensätze roh aus dem Speicher
(``ChatHistoryBlock.retrieve``) und kann einen Tool-Call von seinem
Tool-Ergebnis trennen.

Das Modul hat keine Abhängigkeit auf ``camel`` oder ``oasis``; es arbeitet
ausschließlich über die öffentliche Gedächtnis-Schnittstelle
(``retrieve``/``clear``/``write_records``) und die Pydantic-Methoden der
Datensätze.
"""

from __future__ import annotations

import logging
import math
import os
import warnings
from typing import Any, Callable, Iterable, List, NamedTuple, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Konfiguration (Env, konservative Defaults) -----------------------------

ENV_PRUNE_FEEDS = "AGORA_SIM_MEMORY_PRUNE_FEEDS"
ENV_KEEP_FEEDS = "AGORA_SIM_MEMORY_KEEP_FEEDS"
ENV_TOKEN_CAP = "AGORA_SIM_MEMORY_TOKEN_CAP"  # noqa: S105 -- env key name, not a credential

DEFAULT_KEEP_FEEDS = 4
MIN_KEEP_FEEDS = 1
DEFAULT_MEMORY_TOKEN_CAP = 32_000
#: CAMELs eigener Default fuer ``ScoreBasedContextCreator``. Eine Obergrenze
#: darunter wuerde Agora hinter den Zustand zurueckwerfen, den der Floor
#: (``apply_camel_context_floor``) gerade verhindert.
MIN_MEMORY_TOKEN_CAP = 8_192

_FALSE_VALUES = frozenset({"0", "false", "no", "off", "n"})

# --- Erkennung der Feed-Nachrichten -----------------------------------------

#: Anfang der USER-Nachricht, die ``SocialAgent.perform_action_by_llm`` je
#: Aktivierung schreibt (oasis/social_agent/agent.py). Die Erkennung ist
#: bewusst an diesen Text gebunden: Andere USER-Nachrichten (z. B.
#: Interview-Aufzeichnungen) werden nie angefasst. Ein Drift-Test haelt den
#: Text gegen die installierte OASIS-Version fest.
FEED_MESSAGE_PREFIX = "Please perform social media actions after observing"

#: Anfang des Platzhalters. Dient auch der Idempotenz: ein Platzhalter wird
#: nicht erneut ersetzt.
FEED_PLACEHOLDER_PREFIX = "[Feed of your activation"

_USER_ROLE = "user"

#: Grobe Zeichen-pro-Token-Schaetzung fuer die Budgetpruefung. Bewusst
#: konservativ (JSON und deutsche Texte tokenisieren schlechter als 4:1).
_CHARS_PER_TOKEN = 3


class MemoryPolicy(NamedTuple):
    """Aufgelöste Gedächtnis-Begrenzung eines Laufs."""

    prune_feeds: bool
    keep_feeds: int
    token_cap: int  # 0 = keine Obergrenze


class PruneResult(NamedTuple):
    """Ergebnis des Pruning für ein einzelnes Gedächtnis."""

    replaced: int
    tokens_before: int
    tokens_after: int


class RoundPruneSummary(NamedTuple):
    """Zusammenfassung eines Rundenschritts über alle Agenten."""

    agents_changed: int
    replaced: int
    tokens_before: int
    tokens_after: int
    failures: int


# --- Env-Parsing --------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("[agent_memory] invalid %s=%r ignored, using %s", name, raw, default)
        return default


def prune_feeds_enabled() -> bool:
    raw = os.environ.get(ENV_PRUNE_FEEDS)
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in _FALSE_VALUES


def resolve_keep_feeds() -> int:
    return max(MIN_KEEP_FEEDS, _env_int(ENV_KEEP_FEEDS, DEFAULT_KEEP_FEEDS))


def resolve_memory_token_cap() -> int:
    """Obergrenze fuer das Gedaechtnis-Token-Limit; ``0`` heisst "aus"."""
    value = _env_int(ENV_TOKEN_CAP, DEFAULT_MEMORY_TOKEN_CAP)
    if value <= 0:
        return 0
    return max(value, MIN_MEMORY_TOKEN_CAP)


def load_memory_policy() -> MemoryPolicy:
    return MemoryPolicy(
        prune_feeds=prune_feeds_enabled(),
        keep_feeds=resolve_keep_feeds(),
        token_cap=resolve_memory_token_cap(),
    )


def describe_memory_policy(policy: Optional[MemoryPolicy] = None) -> str:
    """Eine Zeile fuer das Lauf-Log: welche Begrenzung ist aktiv."""
    p = policy or load_memory_policy()
    pruning = f"feeds of older activations replaced (keep last {p.keep_feeds})" if p.prune_feeds else "off"
    cap = f"{p.token_cap} tokens" if p.token_cap > 0 else "off"
    return f"Agent memory limits: feed pruning = {pruning}; memory token cap = {cap}"


# --- Obergrenze fuer das Token-Limit -------------------------------------------


def cap_memory_token_limit(limit: int) -> int:
    """Begrenzt ein aufgeloestes Gedaechtnis-Limit auf die Obergrenze (falls aktiv)."""
    cap = resolve_memory_token_cap()
    if cap <= 0:
        return limit
    return min(limit, cap)


def next_memory_token_limit(old_limit: Optional[int], resolved_limit: int) -> Optional[int]:
    """Neues Limit fuer einen bestehenden ``ScoreBasedContextCreator``.

    * Floor: liegt das aktuelle Limit unter dem aufgeloesten Budget (CAMEL-
      Default 8192), wird es angehoben.
    * Obergrenze: liegt es ueber der Obergrenze (z. B. ``999_999_999`` aus
      ``ModelType.token_limit``), wird es abgesenkt.

    Gibt ``None`` zurueck, wenn nichts zu aendern ist.
    """
    target = cap_memory_token_limit(resolved_limit)
    if old_limit is None or old_limit < target:
        return target
    cap = resolve_memory_token_cap()
    if cap > 0 and old_limit > cap:
        return target
    return None


# --- Feed-Pruning -----------------------------------------------------------------


def _role_value(record: Any) -> str:
    role = getattr(record, "role_at_backend", None)
    return str(getattr(role, "value", role) or "")


def _content(record: Any) -> str:
    content = getattr(getattr(record, "message", None), "content", None)
    return content if isinstance(content, str) else ""


def _is_feed(record: Any) -> bool:
    return _role_value(record) == _USER_ROLE and _content(record).startswith(FEED_MESSAGE_PREFIX)


def _is_placeholder(record: Any) -> bool:
    return _role_value(record) == _USER_ROLE and _content(record).startswith(FEED_PLACEHOLDER_PREFIX)


def estimate_record_tokens(record: Any) -> int:
    """Grobe Token-Schaetzung eines Datensatzes (Inhalt, Tool-Argumente, Ergebnis)."""
    message = getattr(record, "message", None)
    chars = len(_content(record))
    for attr in ("args", "result"):
        value = getattr(message, attr, None)
        if value is not None:
            chars += len(str(value))
    return math.ceil(chars / _CHARS_PER_TOKEN)


def _placeholder_text(activation_number: int) -> str:
    return (
        f"{FEED_PLACEHOLDER_PREFIX} #{activation_number} was removed to save context. "
        "Your own actions from that time are kept in the conversation.]"
    )


def _with_content(record: Any, content: str) -> Any:
    new_message = record.message.create_new_instance(content)
    return record.model_copy(update={"message": new_message})


def _load_records(memory: Any) -> List[Any]:
    with warnings.catch_warnings():
        # ChatHistoryBlock.retrieve warnt bei leerem Gedaechtnis.
        warnings.simplefilter("ignore")
        return [context_record.memory_record for context_record in memory.retrieve()]


def _plan_replacements(
    records: List[Any], keep_feeds: int, token_cap: int
) -> Tuple[List[int], int]:
    """Bestimmt die Indizes der zu ersetzenden Feed-Nachrichten.

    Gibt ``(indizes, geschaetzte_tokens_nach_ersetzung)`` zurueck.
    """
    activation_idx = [i for i, r in enumerate(records) if _is_feed(r) or _is_placeholder(r)]
    retained = set(activation_idx[-keep_feeds:])
    to_replace = [i for i in activation_idx if i not in retained and not _is_placeholder(records[i])]

    sizes = [estimate_record_tokens(r) for r in records]
    total = sum(sizes)
    for i in to_replace:
        total -= sizes[i] - estimate_record_tokens_placeholder(i, activation_idx)

    if token_cap > 0:
        full_feeds = [i for i in activation_idx if not _is_placeholder(records[i])]
        # Der naechste Feed ist ungefaehr so gross wie der groesste bisherige.
        # Passt er nicht mehr unter die Obergrenze, zerstueckelt CAMEL ihn in
        # ``ChatAgent.update_memory`` ("Slicing into smaller chunks"). Deshalb
        # werden bei Bedarf auch die an sich behaltenen aeltesten Feeds ersetzt.
        headroom = max((sizes[i] for i in full_feeds), default=0)
        for i in sorted(retained):
            if total + headroom <= token_cap:
                break
            if _is_placeholder(records[i]):
                continue
            total -= sizes[i] - estimate_record_tokens_placeholder(i, activation_idx)
            to_replace.append(i)
    return sorted(set(to_replace)), total


def estimate_record_tokens_placeholder(index: int, activation_idx: List[int]) -> int:
    number = activation_idx.index(index) + 1
    return math.ceil(len(_placeholder_text(number)) / _CHARS_PER_TOKEN)


def prune_memory_feeds(memory: Any, *, keep_feeds: int, token_cap: int = 0) -> PruneResult:
    """Ersetzt die Feeds aelterer Aktivierungen im Gedaechtnis durch Platzhalter.

    Behalten werden die Feeds der letzten ``keep_feeds`` Aktivierungen. Ist
    ``token_cap`` gesetzt und das Gedaechtnis samt einem weiteren Feed
    voraussichtlich groesser, werden zusaetzlich die aeltesten behaltenen
    Feeds ersetzt. Alles andere (System-Nachricht, eigene Aktionen, Tool-
    Ergebnisse) bleibt unveraendert und in der urspruenglichen Reihenfolge.

    Schlaegt das Zurueckschreiben fehl, wird der urspruengliche Stand
    wiederhergestellt und der Fehler weitergereicht.
    """
    records = _load_records(memory)
    activation_idx = [i for i, r in enumerate(records) if _is_feed(r) or _is_placeholder(r)]
    tokens_before = sum(estimate_record_tokens(r) for r in records)
    if not activation_idx:
        return PruneResult(0, tokens_before, tokens_before)

    indices, tokens_after = _plan_replacements(records, max(1, keep_feeds), token_cap)
    if not indices:
        return PruneResult(0, tokens_before, tokens_before)

    rewritten = list(records)
    for i in indices:
        number = activation_idx.index(i) + 1
        rewritten[i] = _with_content(records[i], _placeholder_text(number))

    try:
        memory.clear()
        memory.write_records(rewritten)
    except Exception:
        # Best effort: den Stand vor dem Eingriff zurueckschreiben.
        try:
            memory.clear()
            memory.write_records(records)
        except Exception:
            logger.error("[agent_memory] restore after failed rewrite failed", exc_info=True)
        raise
    return PruneResult(len(indices), tokens_before, tokens_after)


def _reraise_if_budget_exceeded(exc: BaseException) -> None:
    """Laesst ein hartes Budget durch den breiten Handler im Rundenhook.

    Das Pruning selbst ruft kein Modell auf; die Durchreichung ist eine
    Zusicherung, kein erwarteter Pfad (``BudgetExceededError`` ist das Ende
    des Laufs, nie ein Fehler mit Fallback).
    """
    try:
        from app.services.run_budget import reraise_if_budget_exceeded
    except ImportError:
        return
    reraise_if_budget_exceeded(exc)


def prune_graph_memories(
    agent_graph: Any,
    *,
    round_num: Optional[int] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Optional[RoundPruneSummary]:
    """Rundenhook: ersetzt veraltete Feeds im Gedaechtnis aller Agenten.

    Bricht nie einen Lauf ab. Wirft das Pruning fuer einen Agenten, bleibt
    dieser unveraendert, die uebrigen werden weiter bearbeitet; der Fehler
    wird in der Rundenzeile gezaehlt. ``BudgetExceededError`` wird
    durchgereicht (``BaseException``-Signale wie ``CancelledError`` ohnehin).

    Pro Runde hoechstens eine Logzeile, kein Log je Agent und Schritt.
    """
    if agent_graph is None:
        return None
    policy = load_memory_policy()
    if not policy.prune_feeds:
        return None
    emit = log or logger.info

    try:
        agents: Iterable[Tuple[Any, Any]] = list(agent_graph.get_agents())
    except Exception as exc:
        emit(f"[agent_memory] feed pruning skipped, get_agents failed: {exc}")
        return None

    agents_changed = replaced = before = after = failures = 0
    first_error: Optional[str] = None
    for agent_id, agent in agents:
        memory = getattr(agent, "memory", None)
        if memory is None:
            continue
        try:
            result = prune_memory_feeds(
                memory, keep_feeds=policy.keep_feeds, token_cap=policy.token_cap
            )
        except Exception as exc:
            _reraise_if_budget_exceeded(exc)
            failures += 1
            if first_error is None:
                first_error = f"agent {agent_id}: {type(exc).__name__}: {exc}"
            continue
        if result.replaced:
            agents_changed += 1
            replaced += result.replaced
            before += result.tokens_before
            after += result.tokens_after

    summary = RoundPruneSummary(agents_changed, replaced, before, after, failures)
    if replaced or failures:
        label = f"round {round_num}" if round_num is not None else "round"
        line = (
            f"[agent_memory] {label}: replaced {replaced} old feed message(s) in "
            f"{agents_changed} agent(s), ~{before} -> ~{after} tokens"
        )
        if failures:
            line += f"; {failures} agent(s) left unchanged after errors (first: {first_error})"
        emit(line)
    return summary
