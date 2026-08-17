"""Issue #1304 (S2) — das Aktions-Sampling ist nicht mehr inhaltsblind.

`sample_actions_timeseries` nahm aus jedem Zeit-Bin das erste Element, rein
positional. Ein `like_post` an der Bin-Grenze schlug damit einen ausformulierten
Beitrag desselben Zeitraums — und die daraus gebaute Evidence konnte gar keine
Aussage stützen, weil sie keinen Text trug.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.report_agent.sections import (
    action_content,
    sample_actions_timeseries,
)


def _action(
    round_num: int, action_type: str, content: str | None = None
) -> Dict[str, Any]:
    action: Dict[str, Any] = {
        "action_id": f"a{round_num:03d}",
        "round_num": round_num,
        "action_type": action_type,
    }
    if content is not None:
        action["action_args"] = {"content": content}
    return action


def test_beitrag_schlaegt_like_im_selben_bin():
    """Der Kernfall: das Like steht vorne, der Beitrag dahinter."""
    actions = [
        _action(1, "like_post"),
        _action(2, "create_post", "Die Schulungspflicht ist der eigentliche Engpass."),
    ]

    sampled = sample_actions_timeseries(actions, k=1)

    assert len(sampled) == 1
    assert sampled[0]["action_type"] == "create_post"


def test_laengster_beitrag_gewinnt_im_bin():
    actions = [
        _action(1, "create_comment", "Sehe ich auch so."),
        _action(2, "create_post", "Die Schulungspflicht ist der eigentliche Engpass, "
                                 "solange die Freistellung ungeklaert bleibt."),
        _action(3, "like_post"),
    ]

    sampled = sample_actions_timeseries(actions, k=1)

    assert sampled[0]["action_type"] == "create_post"


def test_bin_ohne_textbeitrag_behaelt_seinen_platz():
    """Sonst bekaeme die Zeitreihe Luecken, wo nur gelikt wurde."""
    actions = [_action(1, "like_post"), _action(2, "repost")]

    sampled = sample_actions_timeseries(actions, k=1)

    assert len(sampled) == 1
    assert sampled[0]["action_type"] == "like_post"


def test_sampling_bleibt_ueber_die_zeit_verteilt():
    """Die Bin-Struktur ist der Sinn der Funktion — sie darf nicht kippen."""
    actions = [
        _action(round_num, "create_post", f"Beitrag aus Runde {round_num}.")
        for round_num in range(1, 21)
    ]

    sampled = sample_actions_timeseries(actions, k=4)

    assert len(sampled) == 4
    rounds = [action["round_num"] for action in sampled]
    assert rounds == sorted(rounds)
    assert rounds[0] <= 5 and rounds[-1] >= 16
    assert all(action["_sampling"]["bin_total"] == 4 for action in sampled)


def test_kleine_mengen_werden_unveraendert_durchgereicht():
    actions = [_action(1, "like_post"), _action(2, "create_post", "Text.")]
    assert sample_actions_timeseries(actions, k=8) == actions


def test_action_content_liest_nur_echten_text():
    assert action_content(_action(1, "create_post", "  Text.  ")) == "Text."
    assert action_content(_action(1, "like_post")) == ""
    assert action_content({"action_args": {"content": 42}}) == ""
    assert action_content({"action_args": "kein dict"}) == ""


def test_evidence_snippet_traegt_den_beitragstext(monkeypatch):
    """Ohne Text im Snippet kann kein Entailment die Aktion je als Beleg werten."""
    from app.services.report_agent import agent as agent_module  # noqa: PLC0415

    text = "Die Schulungspflicht ist der eigentliche Engpass."
    agent = agent_module.ReportAgent.__new__(agent_module.ReportAgent)
    agent.simulation_id = "sim_1304"
    agent.evidence_map = {}

    class _Action:
        def to_dict(self) -> Dict[str, Any]:
            return {
                "action_id": "a001",
                "round_num": 3,
                "action_type": "create_post",
                "platform": "reddit",
                "agent_id": 1,
                "agent_name": "Anna",
                "action_args": {"content": text},
            }

    from app.services.simulation_runner import SimulationRunner  # noqa: PLC0415

    monkeypatch.setattr(
        SimulationRunner, "get_all_actions", staticmethod(lambda *_a, **_k: [_Action()])
    )

    items = agent._collect_simulation_evidence_items()

    action_items = [item for item in items if item.get("type") == "agent_action"]
    assert action_items, "Die Aktion muss als Evidence-Item auftauchen"
    assert text in action_items[0]["snippet"], (
        f"Der Beitragstext fehlt im Snippet: {action_items[0]['snippet']!r}"
    )
