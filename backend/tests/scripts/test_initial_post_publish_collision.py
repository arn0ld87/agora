"""Issue #1245 — Twitter verwarf Initial-Posts bei Agenten-Kollision.

Der Twitter-Zweig hielt die Seed-Posts in einem Dict mit dem Agent-**Objekt**
als Schlüssel und wies per ``initial_actions[agent] = ManualAction(...)`` zu.
Trugen mehrere Posts dieselbe ``poster_agent_id``, überschrieben sie sich
gegenseitig — der letzte gewann, alle vorherigen verschwanden ersatzlos, ohne
Fehler und ohne Warnung.

Der Reddit-Zweig derselben Datei behandelte genau diese Kollision korrekt
(prüfen, in Liste wandeln, anhängen). Es war ein Copy-Paste-Divergenzfehler,
kein Designunterschied.

Belegt an ``sim_54c1c2a6a875``, wo alle 9 Seed-Posts derselben ``agent_id``
zugewiesen waren: Twitter veröffentlichte 1 von 9 (Seed-Index 8, den letzten),
Reddit 9 von 9. Ohne Kollision publizieren beide vollständig — deshalb ist
dieser Fix Defense-in-Depth und unabhängig von der Poster-Zuordnung (#1226) zu
bauen: auch nach deren Fix kann eine Entität legitim mehrfach als Sprecher
auftreten.

Zusätzlich geprüft: die Logzeile gab ``len(initial_actions)`` aus — die Zahl
distinkter Poster-Agenten — und nannte sie „initial posts“. Bei neun
kollabierten Posts meldete sie „1“, bei neun verteilten „9“. Sie war damit
die ganze Zeit ein direkter Indikator für den Kollaps, nur als solcher nicht
lesbar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402


class _FakeAgent:
    """Steht für ein OASIS-Agent-Objekt: identitätsgleich pro ``agent_id``."""

    def __init__(self, agent_id: int) -> None:
        self.agent_id = agent_id

    def __repr__(self) -> str:  # pragma: no cover — nur für Testausgaben
        return f"<Agent {self.agent_id}>"


class _FakeAgentGraph:
    def __init__(self) -> None:
        self._agents: dict[int, _FakeAgent] = {}

    def get_agent(self, agent_id: int) -> _FakeAgent:
        if agent_id < 0:
            raise KeyError(agent_id)
        return self._agents.setdefault(agent_id, _FakeAgent(agent_id))


def _posts(*pairs: tuple[int, str]) -> list[dict]:
    return [{"poster_agent_id": aid, "content": text} for aid, text in pairs]


def _flatten(initial_actions) -> list[str]:
    """Alle Post-Texte der Aktionsstruktur, unabhängig von Einzelwert/Liste."""
    contents: list[str] = []
    for value in initial_actions.values():
        actions = value if isinstance(value, list) else [value]
        for action in actions:
            contents.append(action.action_args["content"])
    return contents


def test_mehrere_posts_desselben_agenten_gehen_nicht_verloren():
    """RED ohne den Fix: nur der letzte der drei Posts überlebt."""
    graph = _FakeAgentGraph()
    posts = _posts((1, "Betriebsrat"), (1, "Kostenträger"), (1, "Honorarkraft"))

    actions, published = rps.build_initial_post_actions(posts, graph)

    assert published == 3
    assert sorted(_flatten(actions)) == [
        "Betriebsrat",
        "Honorarkraft",
        "Kostenträger",
    ], "Kollidierende Posts überschreiben sich — nur der letzte überlebt"


def test_der_beobachtete_fall_neun_posts_auf_einem_agenten():
    """Der reale Kollaps aus ``sim_54c1c2a6a875``: 9 Posts, eine agent_id."""
    graph = _FakeAgentGraph()
    posts = _posts(*[(1, f"Seed {i}") for i in range(9)])

    actions, published = rps.build_initial_post_actions(posts, graph)

    assert published == 9
    assert len(actions) == 1, "Ein Agent, ein Dict-Eintrag — das ist korrekt"
    assert len(_flatten(actions)) == 9, (
        "Alle neun Posts müssen unter diesem einen Eintrag stehen"
    )


def test_ohne_kollision_bleibt_das_verhalten_unveraendert():
    """Gegenprobe: verteilte Poster erzeugen weiterhin je einen Einzelwert."""
    graph = _FakeAgentGraph()
    posts = _posts((1, "A"), (2, "B"), (3, "C"))

    actions, published = rps.build_initial_post_actions(posts, graph)

    assert published == 3
    assert len(actions) == 3
    assert all(not isinstance(v, list) for v in actions.values()), (
        "Ohne Kollision darf kein Post unnötig in eine Liste gewickelt werden"
    )
    assert sorted(_flatten(actions)) == ["A", "B", "C"]


def test_beide_plattformen_bauen_dieselbe_struktur():
    """Twitter und Reddit müssen bei identischer Eingabe identisch publizieren.

    Beide Zweige benutzen jetzt denselben Helfer — der Test hält fest, dass die
    Vorlage nicht wieder auseinanderlaufen darf.
    """
    posts = _posts((1, "A"), (1, "B"), (2, "C"))

    twitter, twitter_count = rps.build_initial_post_actions(posts, _FakeAgentGraph())
    reddit, reddit_count = rps.build_initial_post_actions(posts, _FakeAgentGraph())

    assert twitter_count == reddit_count == 3
    assert sorted(_flatten(twitter)) == sorted(_flatten(reddit)) == ["A", "B", "C"]


def test_unbekannter_agent_wird_uebersprungen_ohne_den_lauf_zu_kippen():
    """Ein nicht auflösbarer Agent darf die übrigen Posts nicht mitreißen."""
    graph = _FakeAgentGraph()
    posts = _posts((1, "A"), (-1, "unbekannt"), (2, "B"))

    actions, published = rps.build_initial_post_actions(posts, graph)

    assert published == 2
    assert sorted(_flatten(actions)) == ["A", "B"]


def test_callback_meldet_jeden_veroeffentlichten_post():
    """Das Action-Log muss jeden Post sehen, nicht nur jeden Agenten."""
    graph = _FakeAgentGraph()
    seen: list[tuple[int, str]] = []
    posts = _posts((1, "A"), (1, "B"), (2, "C"))

    rps.build_initial_post_actions(posts, graph, on_published=lambda aid, text: seen.append((aid, text)))

    assert seen == [(1, "A"), (1, "B"), (2, "C")]


@pytest.mark.parametrize(
    ("posts_count", "agents_count", "expected"),
    [
        (9, 1, "Published 9 initial posts from 1 distinct agent"),
        (9, 9, "Published 9 initial posts from 9 distinct agents"),
        (1, 1, "Published 1 initial post from 1 distinct agent"),
    ],
)
def test_logzeile_nennt_posts_und_distinkte_agenten(posts_count, agents_count, expected):
    """`Published 1 initial posts` bei neun Posts war der Kern der Irreführung."""
    assert rps.format_initial_posts_log(posts_count, agents_count) == expected


# --------------------------------------- Review-Finding (CodeRabbit PR #1256)


def test_standalone_runner_verwirft_keine_posts():
    """Der Einzelplattform-Pfad hatte dieselbe Überschreib-Logik.

    ``platform="twitter"`` startet ``run_twitter_simulation.py``, dessen Runner
    von ``SinglePlatformRunner`` erbt. Die Basisimplementierung von
    ``_assign_initial_action`` überschrieb — mehrere Seed-Posts desselben
    Agenten verschwanden also weiterhin still, obwohl der Parallel-Pfad
    korrigiert war. Der erste Test dieser Datei ruft nur den Parallel-Helfer
    zweimal auf und konnte die Divergenz nicht sehen.
    """
    import importlib.util
    from pathlib import Path as _Path

    runtime_dir = _Path(__file__).resolve().parents[2] / "scripts" / "sim_runtime"
    spec = importlib.util.spec_from_file_location(
        "_platform_runner_under_test", runtime_dir / "platform_runner.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    runner = module.SinglePlatformRunner.__new__(module.SinglePlatformRunner)
    agent = _FakeAgent(1)
    actions: dict = {}

    runner._assign_initial_action(actions, agent, "Betriebsrat")
    runner._assign_initial_action(actions, agent, "Kostenträger")
    runner._assign_initial_action(actions, agent, "Honorarkraft")

    assert len(actions) == 1
    assert sorted(_flatten(actions)) == ["Betriebsrat", "Honorarkraft", "Kostenträger"]


def test_standalone_runner_ohne_kollision_unveraendert():
    """Gegenprobe: ein Post pro Agent bleibt ein Einzelwert, keine Liste."""
    import importlib.util
    from pathlib import Path as _Path

    runtime_dir = _Path(__file__).resolve().parents[2] / "scripts" / "sim_runtime"
    spec = importlib.util.spec_from_file_location(
        "_platform_runner_under_test2", runtime_dir / "platform_runner.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    runner = module.SinglePlatformRunner.__new__(module.SinglePlatformRunner)
    actions: dict = {}
    runner._assign_initial_action(actions, _FakeAgent(1), "A")
    runner._assign_initial_action(actions, _FakeAgent(2), "B")

    assert len(actions) == 2
    assert all(not isinstance(v, list) for v in actions.values())
