"""Antwortziele und sichtbarer Kontext der Simulationsagenten (#1835).

Offline und deterministisch: Modell-Stubs, temporaere SQLite-Dateien unter
``tmp_path``, kein Provider, kein Runner-Start. OASIS legt beim ersten Import
relativ zum Arbeitsverzeichnis ein Verzeichnis ``log`` an; deshalb laedt die
modulweite Fixture ``oasis_ns`` ``agent_feed`` und die OASIS-Module erst in einem
Temp-Verzeichnis. Auf Modulebene stehen nur Standardbibliothek, pytest,
``_sim_common`` und ``agent_tools``.

Tests mit "Istzustand, kein Sollwert" oder "Messung, kein Sollwert" halten fest,
was der Code heute tut; sie sichern keine Anforderung ab.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import logging
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _sim_common as sc  # type: ignore[import-not-found]  # noqa: E402
import agent_tools  # type: ignore[import-not-found]  # noqa: E402

_PARALLEL_RUNNER = _SCRIPTS_DIR / "run_parallel_simulation.py"

# Gemessene Werte (Messung, kein Sollwert); sie machen eine Verschiebung sichtbar.
FEED_LEN_C3 = 11068
VISIBLE_C3 = 3
ORPHANS_CHAIN = 1
ORPHANS_STAR = 5


def _file_handlers() -> set[logging.FileHandler]:
    loggers = [logging.getLogger()] + [
        lg for lg in logging.Logger.manager.loggerDict.values() if isinstance(lg, logging.Logger)
    ]
    return {h for lg in loggers for h in lg.handlers if isinstance(h, logging.FileHandler)}


@pytest.fixture(scope="module", autouse=True)
def oasis_ns(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """Laedt agent_feed und OASIS in einem Temp-Verzeichnis (Waechter gegen Log-Dateien im Repo)."""
    work = tmp_path_factory.mktemp("oasis_cwd")
    cwd = Path.cwd()
    preloaded = "oasis" in sys.modules
    before = _file_handlers()
    os.chdir(work)
    try:
        import agent_feed  # type: ignore[import-not-found]
        import oasis.social_agent.agent_action as aa
        import oasis.social_platform.database as db
        import oasis.social_platform.platform as plat
        import oasis.social_platform.platform_utils as pu
        from oasis.social_agent.agent_environment import SocialEnvironment
        from oasis.social_platform.channel import Channel
    finally:
        os.chdir(cwd)
    if not preloaded:
        stray = [h.baseFilename for h in _file_handlers() - before if not Path(h.baseFilename).is_relative_to(work)]
        if stray:
            raise RuntimeError(f"OASIS-Log-Dateien ausserhalb des Temp-Verzeichnisses: {stray}")
    return SimpleNamespace(
        agent_feed=agent_feed, aa=aa, db=db, plat=plat, pu=pu, Env=SocialEnvironment, Channel=Channel
    )


@pytest.fixture(autouse=True)
def _in_tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture()
def restore_oasis(oasis_ns: SimpleNamespace):
    """Sichert und restauriert die gepatchten OASIS-Referenzen (wie im Patch-Test)."""
    n = oasis_ns
    saved = (n.db.create_db, n.plat.create_db, n.plat.Platform.create_comment,
             n.aa.SocialAction.create_comment, n.pu.PlatformUtils._add_comments_to_posts)
    yield
    (n.db.create_db, n.plat.create_db, n.plat.Platform.create_comment,
     n.aa.SocialAction.create_comment, n.pu.PlatformUtils._add_comments_to_posts) = saved


# -- Hilfen: Plattform, Bruecke, ReAct-Aufbau ----------------------------------------------------


def _make_platform(n: SimpleNamespace, tmp_path: Path, name: str) -> Any:
    platform = n.plat.Platform(str(tmp_path / name), channel=n.Channel())
    cur = platform.db_cursor
    cur.execute("INSERT INTO user (user_id, agent_id, user_name, name) VALUES (1, 1, 'u1', 'User Eins')")
    cur.execute("INSERT INTO post (post_id, user_id, content) VALUES (1, 1, 'Post A')")
    cur.execute("INSERT INTO post (post_id, user_id, content) VALUES (2, 1, 'Post B')")
    platform.db.commit()
    return platform


def _comment_rows(platform: Any) -> list[tuple[Any, ...]]:
    platform.db_cursor.execute("SELECT comment_id, post_id, parent_comment_id FROM comment ORDER BY comment_id")
    return platform.db_cursor.fetchall()


def _native_create_comment(n: SimpleNamespace, platform: Any) -> Any:
    """create_comment aus der OASIS-Funktionsliste; nur der Channel-Transport ist umgangen."""
    action = n.aa.SocialAction(agent_id=1, channel=n.Channel())

    async def _direct(message: Any, _type: str) -> Any:
        return await platform.create_comment(action.agent_id, message)

    action.perform_action = _direct  # type: ignore[method-assign]
    (tool,) = [t for t in action.get_openai_function_list() if t.func.__name__ == "create_comment"]
    return tool.func


class _FakeToolRegistry:
    tools_description_text = "Available Tools:\n- web_search: ...\n"


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeModel:
    def __init__(self, content: str) -> None:
        self._content = content

    def run(self, messages: Any) -> _FakeResponse:
        return _FakeResponse(self._content)


async def _react_comment_args(parent_id: int) -> dict[str, Any]:
    """Fuehrt decide_action mit Modell-Stub aus; Aufbaufehler sind RuntimeError, nie AssertionError."""
    from oasis import ActionType

    payload = {"action": "CREATE_COMMENT", "post_id": 1, "content": "Antwort", "parent_comment_id": parent_id}
    model = _FakeModel(f"<action>\n{json.dumps(payload)}\n</action>")
    loop = agent_tools.ToolAwareActionLoop(model=model, tools=_FakeToolRegistry(), max_tool_calls=1)
    action = await loop.decide_action(
        agent=object(), observation="Feed", available_actions=["CREATE_COMMENT", "DO_NOTHING"],
        agent_name="Alice", agent_role="Analystin", agent_bio="Bio",
    )
    args = getattr(action, "action_args", None)
    if getattr(action, "action_type", None) != ActionType.CREATE_COMMENT or not isinstance(args, dict):
        raise RuntimeError(f"Aufbau fehlgeschlagen: keine CREATE_COMMENT-Aktion, sondern {action!r}")
    if args.get("post_id") != 1 or args.get("content") != "Antwort":
        raise RuntimeError(f"Aufbau fehlgeschlagen: post_id/content abweichend: {args!r}")
    return args


# -- A: nativer Pfad -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_native_reply_reaches_platform_as_nested_comment(oasis_ns, tmp_path, restore_oasis) -> None:
    sc.install_reddit_nested_comments_patch()
    platform = _make_platform(oasis_ns, tmp_path, "a1.db")
    create_comment = _native_create_comment(oasis_ns, platform)

    parent = await create_comment(post_id=1, content="Elternkommentar")
    reply = await create_comment(post_id=1, content="Antwort", parent_comment_id=parent["comment_id"])

    assert reply["success"] is True
    assert (reply["comment_id"], 1, parent["comment_id"]) in _comment_rows(platform)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["missing", "foreign_post"])
async def test_native_reply_with_bad_target_is_rejected(oasis_ns, tmp_path, restore_oasis, target) -> None:
    sc.install_reddit_nested_comments_patch()
    platform = _make_platform(oasis_ns, tmp_path, f"a2_{target}.db")
    create_comment = _native_create_comment(oasis_ns, platform)
    on_b = await create_comment(post_id=2, content="Kommentar auf B")
    parent_id = 999_999 if target == "missing" else on_b["comment_id"]
    rows_before = _comment_rows(platform)

    result = await create_comment(post_id=1, content="Falsches Ziel", parent_comment_id=parent_id)

    assert result["success"] is False
    assert result.get("error")
    assert _comment_rows(platform) == rows_before


@pytest.mark.asyncio
async def test_feed_shows_comment_id_and_parent_comment_id(oasis_ns, tmp_path, restore_oasis) -> None:
    sc.install_reddit_nested_comments_patch()
    platform = _make_platform(oasis_ns, tmp_path, "a3.db")
    create_comment = _native_create_comment(oasis_ns, platform)
    parent = await create_comment(post_id=1, content="Elternkommentar")
    reply = await create_comment(post_id=1, content="Antwort", parent_comment_id=parent["comment_id"])
    platform.db_cursor.execute(
        "SELECT post_id, user_id, original_post_id, content, quote_content, created_at, "
        "num_likes, num_dislikes, num_shares FROM post WHERE post_id = 1"
    )
    posts = platform.pl_utils._add_comments_to_posts(platform.db_cursor.fetchall())

    class _Action:
        async def refresh(self) -> dict[str, Any]:
            return {"success": True, "posts": posts}

    text = await oasis_ns.agent_feed.CommentCappedEnvironment(_Action(), 5).get_posts_env()

    prefix = oasis_ns.Env.posts_env_template.template.split("$posts")[0]
    comments = {c["comment_id"]: c for c in json.loads(text[len(prefix):])[0]["comments"]}
    assert comments[parent["comment_id"]]["parent_comment_id"] is None
    assert comments[reply["comment_id"]]["parent_comment_id"] == parent["comment_id"]
    assert f'"comment_id":{reply["comment_id"]}' in text
    assert f'"parent_comment_id":{parent["comment_id"]}' in text


# -- B: Laufpfad-Defaults ------------------------------------------------------------------------


def _agent_tools_defaults() -> tuple[bool, bool]:
    from app.services.simulation_config_models import SimulationParameters
    from app.settings import AgoraSettings

    params = {f.name: f.default for f in dataclasses.fields(SimulationParameters)}
    return bool(params["enable_agent_tools"]), bool(AgoraSettings.model_fields["enable_agent_tools"].default)


def _parallel_runner_tool_loop_values() -> list[ast.expr]:
    tree = ast.parse(_PARALLEL_RUNNER.read_text(encoding="utf-8"))
    values: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "tool_loop" for t in node.targets):
                values.append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name) and node.target.id == "tool_loop":
                values.append(node.value)
    return values


def react_loop_active_by_default() -> bool:
    """Ableitung G1(b): ReAct-Loop unter Standardkonfiguration aktiv?"""
    values = _parallel_runner_tool_loop_values()
    if not values:
        raise RuntimeError("Keine Zuweisung an tool_loop im Parallel-Runner gefunden")
    parallel_builds_loop = any(not (isinstance(v, ast.Constant) and v.value is None) for v in values)
    return any(_agent_tools_defaults()) or parallel_builds_loop


def test_default_agent_tools_are_off() -> None:
    """Istzustand, kein Sollwert: enable_agent_tools ist in Modell und Settings aus."""
    assert _agent_tools_defaults() == (False, False)


def test_parallel_runner_assigns_only_none_to_tool_loop() -> None:
    """Istzustand, kein Sollwert: der Parallel-Runner baut keinen ReAct-Loop."""
    values = _parallel_runner_tool_loop_values()
    assert len(values) >= 2
    assert all(isinstance(v, ast.Constant) and v.value is None for v in values)


G1B_REACT_LOOP_ACTIVE_BY_DEFAULT = False


def test_default_react_loop_gate_matches_derivation() -> None:
    """Istzustand, kein Sollwert: G1(b) ist die Ableitung aus Defaults und Parallel-Runner."""
    assert react_loop_active_by_default() == G1B_REACT_LOOP_ACTIVE_BY_DEFAULT


# -- C: ReAct-Loop -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_react_create_comment_setup_keeps_post_id_and_content(oasis_ns, restore_oasis) -> None:
    sc.install_reddit_nested_comments_patch()
    args = await _react_comment_args(7)
    assert args["post_id"] == 1 and args["content"] == "Antwort"


@pytest.mark.xfail(
    reason=(
        "Bekannte Lücke (#1835): ToolAwareActionLoop._create_manual_action übernimmt bei "
        "CREATE_COMMENT nur post_id und content und verwirft parent_comment_id. Der ReAct-Loop "
        "ist im Parallel-Runner unerreichbar (tool_loop = None) und nur im Einzel-Runner mit "
        "aktivierten Agent-Tools (enable_agent_tools, Default aus) aktiv. Bewusst nicht "
        "gepatcht, solange Gate G1 nicht erfüllt ist; fällt weg, sobald der Loop ein aktiver "
        "Laufpfad ist und der Fix existiert."
    ),
    strict=True,
    raises=AssertionError,
)
@pytest.mark.asyncio
async def test_react_create_comment_forwards_parent_comment_id(oasis_ns, restore_oasis) -> None:
    sc.install_reddit_nested_comments_patch()
    args = await _react_comment_args(7)
    assert args.get("parent_comment_id") == 7


def test_oasis_social_agent_has_no_persona_attributes(oasis_ns) -> None:
    """Istzustand, kein Sollwert: echte SocialAgent-Instanz ohne username/profession/bio.

    Bekannte Lücke: Die Persona erreicht den ReAct-Prompt nicht (Ersatzwerte, platform_runner.py:787-789).
    """
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType
    from oasis.social_agent.agent import SocialAgent
    from oasis.social_platform.config import UserInfo

    model = ModelFactory.create(model_platform=ModelPlatformType.OPENAI, model_type=ModelType.STUB)
    info = UserInfo(
        user_name="synth_user", name="Synthetische Person", description="Testprofil", recsys_type="reddit",
        profile={"other_info": {"user_profile": "p", "gender": "x", "age": 30, "mbti": "INTJ", "country": "DE"}},
    )
    agent = SocialAgent(agent_id=3, user_info=info, channel=oasis_ns.Channel(), model=model)
    assert [hasattr(agent, k) for k in ("username", "profession", "bio")] == [False, False, False]


# -- Messungen -----------------------------------------------------------------------------------


def _feed_posts(n_posts: int, n_comments: int, parent_of: Any = lambda i: None) -> list[dict[str, Any]]:
    return [
        {
            "post_id": p, "user_id": 1, "content": "P" * 280, "created_at": "2026-10-10 09:00:00.000000",
            "num_likes": 0, "num_dislikes": 0, "num_shares": 0, "num_reports": 0,
            "comments": [
                {"comment_id": p * 100 + c, "post_id": p, "user_id": 2, "content": "K" * 200,
                 "created_at": f"2026-10-10 10:{c:02d}:00.000000", "num_likes": 0, "num_dislikes": 0,
                 "parent_comment_id": parent_of(c) if parent_of(c) is None else p * 100 + parent_of(c)}
                for c in range(1, n_comments + 1)
            ],
        }
        for p in range(1, n_posts + 1)
    ]


async def _render(oasis_ns: SimpleNamespace, posts: list[dict[str, Any]], cap: int) -> str:
    class _Action:
        async def refresh(self) -> dict[str, Any]:
            return {"success": True, "posts": posts}

    return await oasis_ns.agent_feed.CommentCappedEnvironment(_Action(), cap).get_posts_env()


@pytest.mark.asyncio
async def test_measure_react_timeline_cut(oasis_ns) -> None:
    """Messung, kein Sollwert: Feed 5x5 Kommentare, ReAct-Timeline-Schnitt 1500."""
    feed = await _render(oasis_ns, _feed_posts(5, 5), 5)
    prompt = agent_tools.build_agent_prompt_with_tools(
        "Alice", "Analystin", "Bio", feed, ["CREATE_COMMENT"], _FakeToolRegistry()
    )
    match = re.search(r'<untrusted_data source="timeline">\n(.*?)\n</untrusted_data>', prompt, re.DOTALL)
    assert match is not None
    visible = len(re.findall(r'"comment_id":', match.group(1)))
    assert (len(match.group(1)), len(feed), visible, 25) == (1500, FEED_LEN_C3, VISIBLE_C3, 25)


def _orphans(feed_text: str, prefix: str) -> int:
    count = 0
    for post in json.loads(feed_text[len(prefix):]):
        ids = {c["comment_id"] for c in post["comments"]}
        count += sum(1 for c in post["comments"] if c["parent_comment_id"] is not None and c["parent_comment_id"] not in ids)
    return count


@pytest.mark.asyncio
async def test_measure_native_feed_orphaned_reply_targets(oasis_ns) -> None:
    """Messung, kein Sollwert: sichtbare Kommentare mit unsichtbarem Elternkommentar (Deckel 5, 8 Kommentare).

    Bekannte Lücke: Verwaiste Antwortbezüge im gedeckelten Feed des nativen Pfads, nicht behoben (D-04).
    """
    prefix = oasis_ns.Env.posts_env_template.template.split("$posts")[0]
    chain = await _render(oasis_ns, _feed_posts(1, 8, lambda c: None if c == 1 else c - 1), 5)
    star = await _render(oasis_ns, _feed_posts(1, 8, lambda c: None if c == 1 else 1), 5)
    assert (_orphans(chain, prefix), _orphans(star, prefix)) == (ORPHANS_CHAIN, ORPHANS_STAR)
