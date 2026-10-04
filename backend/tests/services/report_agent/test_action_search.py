"""Der Report-Agent sucht gezielt in Simulationsbeiträgen (Issue #1778, Schritt 1.7).

Im Referenzlauf beruhten 3 von 164 stützenden Belegen auf Simulationsaktionen,
weil der Agent nur eine feste Acht-Aktionen-Stichprobe sah. Das Werkzeug
``search_simulation_actions`` macht die Beiträge durchsuchbar; jeder Treffer
wird ein Beleg vom Typ ``agent_action`` mit derselben Identität wie in der
Stichprobe.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.services.report_agent.action_search import (
    ActionSearchResult,
    build_action_evidence_item,
    search_simulation_actions,
)
from app.services.simulation_runner import SimulationRunner


def _action(
    agent_id: int,
    agent_name: str,
    round_num: int,
    content: str | None,
    *,
    action_type: str = "CREATE_POST",
    platform: str = "reddit",
    role_conflict: str | None = None,
) -> Dict[str, Any]:
    action: Dict[str, Any] = {
        "round_num": round_num,
        "timestamp": f"2026-01-01T{round_num:02d}:00:00",
        "platform": platform,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "action_type": action_type,
        "action_args": {"content": content} if content is not None else {},
        "result": None,
        "success": True,
    }
    if role_conflict is not None:
        action["role_conflict"] = role_conflict
    return action


class _Stored:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> Dict[str, Any]:
        return self._payload


@pytest.fixture
def actions(monkeypatch) -> List[Dict[str, Any]]:
    stored = [
        _action(0, "Hebamme Lena", 1, "Die Schließung der Geburtshilfe gefährdet die Versorgung."),
        _action(1, "Klinikleitung", 2, "Wir prüfen die Zahlen und berichten im Ausschuss."),
        _action(2, "Stadtrat Weber", 3, "Die Schließung ist wirtschaftlich nötig, die Versorgung bleibt gesichert."),
        _action(0, "Hebamme Lena", 4, "Ohne Kreißsaal fahren Familien vierzig Minuten weiter."),
        _action(3, "Dozentin", 2, "Als Klinikleitung sage ich: Schließung jetzt.", role_conflict="foreign_role"),
        _action(1, "Klinikleitung", 3, None, action_type="LIKE_POST"),
    ]
    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        staticmethod(lambda *_a, **_k: [_Stored(action) for action in stored]),
    )
    return stored


def test_textfilter_findet_den_passenden_beitrag_und_sortiert_ihn_nach_vorn(actions):
    result = search_simulation_actions("sim-1", query="Schließung Versorgung gesichert")

    assert isinstance(result, ActionSearchResult)
    # Stadtrat Weber trifft drei Suchwörter, Hebamme Lena (Runde 1) zwei.
    assert [hit["agent_name"] for hit in result.hits] == ["Stadtrat Weber", "Hebamme Lena"]
    assert result.total_matching == 2
    assert result.total_actions == 4


def test_gleiche_punktzahl_wird_nach_runde_aufsteigend_sortiert(actions):
    result = search_simulation_actions("sim-1", query="Versorgung")

    assert [hit["round_num"] for hit in result.hits] == [1, 3]


def test_leere_suche_liefert_alle_beitraege_mit_text_nach_runde(actions):
    result = search_simulation_actions("sim-1")

    assert [hit["round_num"] for hit in result.hits] == [1, 2, 3, 4]


def test_agent_name_filter_wirkt_ohne_gross_und_kleinschreibung(actions):
    result = search_simulation_actions("sim-1", agent_name="hebamme")

    assert [hit["round_num"] for hit in result.hits] == [1, 4]


def test_rundenfilter_schliesst_beide_grenzen_ein(actions):
    result = search_simulation_actions("sim-1", round_from=2, round_to=3)

    assert [hit["agent_name"] for hit in result.hits] == ["Klinikleitung", "Stadtrat Weber"]


def test_aktionen_mit_hartem_rollenkonflikt_kommen_nicht_vor(actions):
    result = search_simulation_actions("sim-1", query="Schließung")

    assert "Dozentin" not in [hit["agent_name"] for hit in result.hits]
    assert all(hit.get("role_conflict") is None for hit in result.hits)


def test_aktionen_ohne_text_kommen_nicht_vor(actions):
    result = search_simulation_actions("sim-1")

    assert "LIKE_POST" not in [hit["action_type"] for hit in result.hits]


def test_limit_wird_auf_zwanzig_begrenzt(monkeypatch):
    many = [_action(i, f"Agent {i}", i, f"Beitrag Nummer {i} zur Schließung") for i in range(1, 31)]
    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        staticmethod(lambda *_a, **_k: [_Stored(action) for action in many]),
    )

    result = search_simulation_actions("sim-1", limit=50)

    assert len(result.hits) == 20
    assert result.total_matching == 30


def test_limit_unter_eins_liefert_mindestens_einen_treffer(actions):
    assert len(search_simulation_actions("sim-1", limit=0).hits) == 1


def test_der_gerenderte_text_nennt_stimme_plattform_runde_und_wortlaut(actions):
    text = search_simulation_actions("sim-1", agent_name="Stadtrat").to_text()

    assert "Stadtrat Weber" in text
    assert "reddit" in text
    assert "round 3" in text
    assert "Die Schließung ist wirtschaftlich nötig" in text


def test_beleg_traegt_dieselbe_identitaet_wie_die_stichprobe():
    """Sammeln und Suchen müssen für dieselbe Aktion dieselbe Evidence-ID ergeben."""
    action = _action(1, "Betriebsratsvorsitzende", 2, "Wir fordern eine bessere Ausbildung.")
    action["timestamp"] = "2026-01-01T01:00:00"

    item = build_action_evidence_item(action)

    assert item["producer_key"] == "simulation-action:reddit:2:1:CREATE_POST:2026-01-01T01:00:00"
    assert item["type"] == "agent_action"
    assert item["source"] == "simulation_actions"
    assert item["value"] == "CREATE_POST"
    assert item["voice_key"] == "agent:1"
    assert item["raw"] is action
    assert item["snippet"] == (
        "Betriebsratsvorsitzende CREATE_POST on reddit in round 2: "
        "Wir fordern eine bessere Ausbildung."
    )


def test_beleg_kuerzt_den_wortlaut_auf_sechshundert_zeichen():
    item = build_action_evidence_item(_action(0, "Anna", 1, "x" * 700))

    assert item["snippet"].endswith("x" * 600 + "...")


def test_stichprobe_und_suche_bauen_denselben_beleg(monkeypatch):
    from app.services.report_agent.agent import ReportAgent

    action = _action(1, "Betriebsratsvorsitzende", 2, "Wir fordern eine bessere Ausbildung.")
    monkeypatch.setattr(
        SimulationRunner, "get_all_actions", staticmethod(lambda *_a, **_k: [_Stored(action)])
    )
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim-1"
    agent.evidence_map = {}

    sampled = [
        item
        for item in agent._collect_simulation_evidence_items()
        if item.get("type") == "agent_action"
    ]

    assert sampled == [build_action_evidence_item(action)]


def test_suchtreffer_werden_als_agent_action_belege_registriert(monkeypatch):
    from app.services.report_agent.agent import ReportAgent

    action = _action(1, "Betriebsratsvorsitzende", 2, "Wir fordern eine bessere Ausbildung.")
    recorded: List[Dict[str, Any]] = []
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim-1"
    monkeypatch.setattr(
        agent, "_record_evidence_item", lambda item: recorded.append(item) or "ev_1", raising=False
    )

    agent._record_tool_evidence(
        "search_simulation_actions",
        {"query": "Ausbildung"},
        ActionSearchResult(query="Ausbildung", hits=[action], total_matching=1, total_actions=1),
        "gerendert",
        3,
    )

    assert len(recorded) == 1
    expected = build_action_evidence_item(action)
    assert {key: recorded[0][key] for key in expected} == expected
    assert recorded[0]["tool_name"] == "search_simulation_actions"


def test_kurze_abkuerzungen_sind_suchwoerter(monkeypatch):
    """Review PR #1780: „AfD" fiel unter die Vier-Zeichen-Grenze und fand nichts."""
    stored = [
        _action(0, "Stadtrat Weber", 1, "Die AfD stimmt der Schließung zu."),
        _action(1, "Hebamme Lena", 2, "Niemand hat mit uns geredet."),
        _action(2, "Klinikleitung", 3, "Die EU-Vorgaben lassen keine Wahl."),
    ]
    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        staticmethod(lambda *_a, **_k: [_Stored(action) for action in stored]),
    )

    assert [hit["agent_name"] for hit in search_simulation_actions("sim-1", query="AfD").hits] == [
        "Stadtrat Weber"
    ]
    assert [hit["agent_name"] for hit in search_simulation_actions("sim-1", query="EU").hits] == [
        "Klinikleitung"
    ]


def test_kurze_fuellwoerter_bleiben_ohne_wirkung(actions):
    """„die" ist kein Suchwort: sonst träfe fast jeder Beitrag."""
    assert search_simulation_actions("sim-1", query="die").hits == []


def test_kurze_abkuerzung_trifft_nur_als_ganzes_wort(monkeypatch):
    stored = [_action(0, "Anna", 1, "Die Neubauten kosten viel.")]
    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        staticmethod(lambda *_a, **_k: [_Stored(action) for action in stored]),
    )

    assert search_simulation_actions("sim-1", query="EU").hits == []
