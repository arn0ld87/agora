"""Kommentardeckel im Agenten-Feed (#1772)."""

from __future__ import annotations

import asyncio
import copy
import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
from oasis.social_agent.agent_environment import SocialEnvironment

# backend/scripts auf sys.path, wie zur Laufzeit des OASIS-Subprozesses.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

agent_feed = importlib.import_module("agent_feed")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(agent_feed.ENV_FEED_MAX_COMMENTS, raising=False)


def _comment(number: int, **extra: Any) -> Dict[str, Any]:
    return {
        "comment_id": number,
        "post_id": 7,
        "user_id": number % 3,
        "content": f"Kommentar {number} mit Umlaut ü",
        "created_at": f"2026-10-04 10:{number:02d}:00.000000",
        "num_likes": number,
        "num_dislikes": 0,
        **extra,
    }


def _post(post_id: int, comment_count: int) -> Dict[str, Any]:
    return {
        "post_id": post_id,
        "user_id": 1,
        "content": f"Beitrag {post_id}",
        "created_at": "2026-10-04 09:00:00.000000",
        "num_likes": 2,
        "num_dislikes": 0,
        "num_shares": 0,
        "num_reports": 0,
        "comments": [_comment(n) for n in range(1, comment_count + 1)],
    }


# --- cap_post_comments -----------------------------------------------------------------


def test_twelve_comments_become_the_five_newest_plus_omitted_count() -> None:
    post = _post(1, 12)

    (capped,) = agent_feed.cap_post_comments([post], 5)

    assert [c["comment_id"] for c in capped["comments"]] == [8, 9, 10, 11, 12]
    assert capped["omitted_comments"] == 7
    # Felder der verbleibenden Kommentare und alle uebrigen Postfelder unveraendert.
    assert capped["comments"] == post["comments"][-5:]
    assert {k: v for k, v in capped.items() if k not in ("comments", "omitted_comments")} == {
        k: v for k, v in post.items() if k != "comments"
    }


def test_post_with_three_comments_is_untouched() -> None:
    post = _post(1, 3)
    snapshot = copy.deepcopy(post)

    (capped,) = agent_feed.cap_post_comments([post], 5)

    assert capped is post
    assert capped == snapshot
    assert "omitted_comments" not in capped


def test_post_with_exactly_the_limit_is_untouched() -> None:
    (capped,) = agent_feed.cap_post_comments([_post(1, 5)], 5)
    assert "omitted_comments" not in capped and len(capped["comments"]) == 5


def test_cap_zero_lets_everything_through() -> None:
    posts = [_post(1, 12), _post(2, 40)]
    assert agent_feed.cap_post_comments(posts, 0) is posts


def test_input_is_not_mutated() -> None:
    posts = [_post(1, 12)]
    snapshot = copy.deepcopy(posts)
    agent_feed.cap_post_comments(posts, 5)
    assert posts == snapshot


def test_newest_is_decided_by_time_not_by_list_position_and_order_is_kept() -> None:
    post = _post(1, 8)
    # Liste durchmischt: die Positionen sagen nichts ueber das Alter.
    post["comments"] = [post["comments"][i] for i in (5, 0, 7, 2, 6, 1, 4, 3)]

    (capped,) = agent_feed.cap_post_comments([post], 3)

    # Die drei juengsten (IDs 8, 7, 6) bleiben, in der Reihenfolge der Eingabeliste (6, 8, 7).
    assert [c["comment_id"] for c in capped["comments"]] == [6, 8, 7]
    assert capped["omitted_comments"] == 5


def test_equal_timestamps_fall_back_to_comment_id() -> None:
    post = _post(1, 6)
    for comment in post["comments"]:
        comment["created_at"] = "2026-10-04 10:00:00.000000"

    (capped,) = agent_feed.cap_post_comments([post], 2)

    assert [c["comment_id"] for c in capped["comments"]] == [5, 6]


# --- Env --------------------------------------------------------------------------------------


def test_env_default_override_off_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    assert agent_feed.resolve_feed_max_comments() == 5
    monkeypatch.setenv(agent_feed.ENV_FEED_MAX_COMMENTS, "9")
    assert agent_feed.resolve_feed_max_comments() == 9
    monkeypatch.setenv(agent_feed.ENV_FEED_MAX_COMMENTS, "0")
    assert agent_feed.resolve_feed_max_comments() == 0
    monkeypatch.setenv(agent_feed.ENV_FEED_MAX_COMMENTS, "-3")
    assert agent_feed.resolve_feed_max_comments() == 0
    monkeypatch.setenv(agent_feed.ENV_FEED_MAX_COMMENTS, "viele")
    assert agent_feed.resolve_feed_max_comments() == 5


# --- Environment -------------------------------------------------------------------------------


class _Action:
    def __init__(self, result: Dict[str, Any]) -> None:
        self._result = result

    async def refresh(self) -> Dict[str, Any]:
        return self._result


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_capped_environment_keeps_oasis_template_and_posts_structure() -> None:
    posts = [_post(1, 12), _post(2, 3)]
    result = {"success": True, "posts": posts}
    reference = _run(SocialEnvironment(_Action(result)).get_posts_env())

    text = _run(agent_feed.CommentCappedEnvironment(_Action(result), 5).get_posts_env())

    prefix = SocialEnvironment.posts_env_template.template.split("$posts")[0]
    assert text.startswith(prefix) and reference.startswith(prefix)
    capped = json.loads(text[len(prefix):])
    assert [len(p["comments"]) for p in capped] == [5, 3]
    assert capped[0]["omitted_comments"] == 7 and "omitted_comments" not in capped[1]
    # Kompakt: kein Einrueckungs-Whitespace, deutlich kuerzer als die OASIS-Ausgabe.
    assert "\n" not in text and "    " not in text
    assert len(text) < len(reference) / 2


def test_capped_environment_without_cap_matches_oasis_content() -> None:
    posts = [_post(1, 12)]
    result = {"success": True, "posts": posts}
    reference = _run(SocialEnvironment(_Action(result)).get_posts_env())
    text = _run(agent_feed.CommentCappedEnvironment(_Action(result), 0).get_posts_env())
    prefix = SocialEnvironment.posts_env_template.template.split("$posts")[0]
    assert json.loads(text[len(prefix):]) == json.loads(reference[len(prefix):])


def test_capped_environment_reports_empty_feed_like_oasis() -> None:
    result = {"success": False}
    assert _run(agent_feed.CommentCappedEnvironment(_Action(result), 5).get_posts_env()) == _run(
        SocialEnvironment(_Action(result)).get_posts_env()
    )


def test_oasis_get_posts_env_still_has_the_shape_the_override_relies_on() -> None:
    """Drift-Schutz: die Subklasse ersetzt get_posts_env und verlaesst sich auf diese Form."""
    source = inspect.getsource(SocialEnvironment.get_posts_env)
    assert "self.action.refresh()" in source
    assert 'posts["success"]' in source and 'posts["posts"]' in source
    assert "posts_env_template.substitute(posts=posts_env)" in source


# --- Einhaengen ----------------------------------------------------------------------------------


class _Agent:
    def __init__(self, env: Any) -> None:
        self.env = env


class _Graph:
    def __init__(self, agents: List[Any]) -> None:
        self._agents = list(enumerate(agents))

    def get_agents(self) -> List[Any]:
        return self._agents


def test_install_swaps_plain_social_environments_only(monkeypatch: pytest.MonkeyPatch) -> None:
    action = _Action({"success": True, "posts": []})

    class _Foreign(SocialEnvironment):
        pass

    plain, foreign = _Agent(SocialEnvironment(action)), _Agent(_Foreign(action))
    already = _Agent(agent_feed.CommentCappedEnvironment(action, 5))
    original_foreign, original_already = foreign.env, already.env
    logged: List[str] = []

    assert agent_feed.install_feed_comment_cap(_Graph([plain, foreign, already]), log=logged.append) == 1

    assert isinstance(plain.env, agent_feed.CommentCappedEnvironment)
    assert plain.env.action is action and plain.env.max_comments == 5
    assert foreign.env is original_foreign and already.env is original_already
    assert logged == ["Feed comment cap: newest 5 comments per post in 1 agent feed(s)"]


def test_install_is_a_no_op_when_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(agent_feed.ENV_FEED_MAX_COMMENTS, "0")
    agent = _Agent(SocialEnvironment(_Action({"success": True, "posts": []})))
    original = agent.env
    logged: List[str] = []

    assert agent_feed.install_feed_comment_cap(_Graph([agent]), log=logged.append) == 0

    assert agent.env is original
    assert logged == ["Feed comment cap: off (all comments per post are shown)"]
