"""Kommentardeckel im Feed der Simulationsagenten (#1772).

OASIS' ``SocialEnvironment.get_posts_env`` serialisiert jeden Post des Feeds
mit **allen** Kommentaren als eingerueckten JSON-Text
(``json.dumps(posts, indent=4)``, ``oasis/social_agent/agent_environment.py``).
Die Kommentare stammen aus ``PlatformUtils._add_comments_to_posts``
(``oasis/social_platform/platform_utils.py``) ohne Obergrenze. Bei lang
laufenden Diskussionen macht das den Feed -- und damit jede Agenten-Nachricht
im Gedaechtnis -- immer groesser.

Eingriff ohne Patch an OASIS: ``CommentCappedEnvironment`` ist eine Subklasse
von ``SocialEnvironment`` und ersetzt nur ``get_posts_env``. Sie benutzt
ausschliesslich oeffentliche Mittel der Basisklasse (``self.action.refresh()``
mit dem dokumentierten Rueckgabeformat ``{"success", "posts"}`` und
``posts_env_template``). ``install_feed_comment_cap`` tauscht ``agent.env`` je
Agent gegen diese Subklasse; das Attribut ist die Stelle, an der OASIS selbst
die Umgebung ablegt. Ein Drift-Test haelt die Ausgabe gegen die installierte
OASIS-Version fest.

Je Post bleiben die neuesten ``N`` Kommentare (Zeitfeld ``created_at``, bei
Gleichstand ``comment_id``) in ihrer urspruenglichen Reihenfolge; die Zahl der
weggelassenen steht als ``omitted_comments`` am Post. Der Feed wird zusaetzlich
kompakt serialisiert (``separators=(",", ":")`` statt ``indent=4``);
``ensure_ascii`` bleibt bewusst unveraendert, damit fehlerhafte Surrogate in
Modelltexten die spaetere UTF-8-Kodierung nicht brechen.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, List, Optional

from oasis.social_agent.agent_environment import SocialEnvironment

logger = logging.getLogger(__name__)

ENV_FEED_MAX_COMMENTS = "AGORA_SIM_FEED_MAX_COMMENTS"
DEFAULT_FEED_MAX_COMMENTS = 5

OMITTED_COMMENTS_KEY = "omitted_comments"


def resolve_feed_max_comments() -> int:
    """Hoechstzahl Kommentare je Post im Feed; ``0`` heisst "aus"."""
    raw = os.environ.get(ENV_FEED_MAX_COMMENTS)
    if raw is None or not raw.strip():
        return DEFAULT_FEED_MAX_COMMENTS
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        logger.warning(
            "[agent_feed] invalid %s=%r ignored, using %s",
            ENV_FEED_MAX_COMMENTS,
            raw,
            DEFAULT_FEED_MAX_COMMENTS,
        )
        return DEFAULT_FEED_MAX_COMMENTS


def _comment_sort_key(comment: Any) -> tuple:
    if not isinstance(comment, dict):
        return ("", 0)
    comment_id = comment.get("comment_id")
    return (
        str(comment.get("created_at") or ""),
        comment_id if isinstance(comment_id, int) else 0,
    )


def cap_post_comments(posts: List[Any], max_comments: int) -> List[Any]:
    """Begrenzt die Kommentare je Post auf die neuesten ``max_comments``.

    ``max_comments <= 0`` laesst alles durch. Die Eingabe wird nicht
    veraendert; Posts mit hoechstens ``max_comments`` Kommentaren werden
    unveraendert (dasselbe Objekt) zurueckgegeben.
    """
    if max_comments <= 0:
        return posts
    capped: List[Any] = []
    for post in posts:
        comments = post.get("comments") if isinstance(post, dict) else None
        if not isinstance(comments, list) or len(comments) <= max_comments:
            capped.append(post)
            continue
        newest = sorted(range(len(comments)), key=lambda i: _comment_sort_key(comments[i]))[-max_comments:]
        keep = set(newest)
        kept = [c for i, c in enumerate(comments) if i in keep]
        capped.append({**post, "comments": kept, OMITTED_COMMENTS_KEY: len(comments) - len(kept)})
    return capped


class CommentCappedEnvironment(SocialEnvironment):
    """``SocialEnvironment`` mit Kommentardeckel und kompaktem Feed-JSON."""

    def __init__(self, action: Any, max_comments: int) -> None:
        super().__init__(action)
        self.max_comments = max_comments

    async def get_posts_env(self) -> str:
        posts = await self.action.refresh()
        if posts["success"]:
            capped = cap_post_comments(posts["posts"], self.max_comments)
            posts_env = json.dumps(capped, separators=(",", ":"))
            return self.posts_env_template.substitute(posts=posts_env)
        return "After refreshing, there are no existing posts."


def install_feed_comment_cap(
    agent_graph: Any,
    *,
    max_comments: Optional[int] = None,
    log: Optional[Callable[[str], None]] = None,
) -> int:
    """Tauscht ``agent.env`` jedes Agenten gegen ``CommentCappedEnvironment``.

    Gibt die Zahl der umgestellten Agenten zurueck. Bei ``0`` (aus) bleibt
    alles beim OASIS-Stand, auch das JSON-Format. Nur eine unveraenderte
    ``SocialEnvironment`` (exakter Typ) wird ersetzt; eine bereits
    ersetzte oder fremde Subklasse bleibt unberuehrt. Fehler bei einem Agenten
    lassen diesen unveraendert und brechen den Lauf nicht ab.
    """
    emit = log or logger.info
    limit = resolve_feed_max_comments() if max_comments is None else max_comments
    if agent_graph is None or limit <= 0:
        emit("Feed comment cap: off (all comments per post are shown)")
        return 0
    swapped = failures = 0
    try:
        agents = list(agent_graph.get_agents())
    except Exception as exc:
        emit(f"Feed comment cap skipped, get_agents failed: {exc}")
        return 0
    for _agent_id, agent in agents:
        env = getattr(agent, "env", None)
        if type(env) is not SocialEnvironment:
            continue
        try:
            agent.env = CommentCappedEnvironment(env.action, limit)
            swapped += 1
        except Exception:
            failures += 1
    line = f"Feed comment cap: newest {limit} comments per post in {swapped} agent feed(s)"
    if failures:
        line += f"; {failures} agent(s) left unchanged after errors"
    emit(line)
    return swapped
