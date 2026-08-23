"""Issue #1303 — Panel-Rotation statt Wiederverwendung bei Abschnitts-Interviews.

Empirischer Befund des Referenzlaufs: Abschnitt 1, 3 und 5 interviewten
praktisch dasselbe Fuenferpanel — mehr Interviews machten den bestehenden
Konsens nur lauter, statt neue Perspektiven zu bringen. Ursache: die
LLM-Auswahl (``_select_agents_for_interview``) hat kein Run-Gedaechtnis.

Der Scheduler hier trackt pro Report-Lauf, welche Personas bereits befragt
wurden, und setzt drei Prioritaetsklassen durch:

1. frisch (noch nie befragt),
2. wiederverwendbar (unter dem Limit UND signifikant anderer Aspekt),
3. Ausschoepfungs-Fallback (nur wenn nichts anderes uebrig ist).

Metrik: ``panel_overlap_ratio`` (Jaccard ueber die Persona-Namen zweier
Abschnits-Panels) macht sinkende Panel-Ueberlappung assertierbar.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Config
from app.services.graph_tools import GraphToolsService
from app.services.interview_panel import (
    DEFAULT_MAX_INTERVIEWS_PER_PERSONA,
    InterviewPanelTracker,
    aspects_differ,
    panel_overlap_ratio,
)

FIVE_PROFILES = [
    {
        "realname": f"Persona {i}",
        "username": f"persona_{i}",
        "profession": f"Rolle {i}",
        "bio": f"Bio von Persona {i}",
    }
    for i in range(5)
]


# ---------------------------------------------------------------------------
# Unit: InterviewPanelTracker
# ---------------------------------------------------------------------------


def test_default_limit_is_two():
    """Issue #1303: Default-Limit N=2, konfigurierbar."""
    assert DEFAULT_MAX_INTERVIEWS_PER_PERSONA == 2
    assert InterviewPanelTracker().max_interviews_per_persona == 2
    assert InterviewPanelTracker(max_interviews_per_persona=3).max_interviews_per_persona == 3


def test_five_personas_five_sections_each_persona_max_twice():
    """Testplan #1303: Scheduler mit 5 Personas, 5 Abschnitten (je 2 Slots,
    wechselnde Anforderungen, das LLM beharrt auf [0, 1]) — keine Persona
    darf ueber 2 Interviews hinauskommen."""
    tracker = InterviewPanelTracker()
    requirements = [
        "Preiswirkung auf Verbraucher",
        "Lieferketten und Handel",
        "Arbeitsbedingungen in der Produktion",
        "Umweltfolgen der Entsorgung",
        "Datenschutz der neuen App",
    ]

    for requirement in requirements:
        final_indices, _note = tracker.apply_selection(
            profiles=FIVE_PROFILES,
            selected_indices=[0, 1],
            requirement=requirement,
        )
        assert len(final_indices) == 2, (
            f"Abschnitt '{requirement}' erhaelt kein volles Panel: {final_indices}"
        )
        tracker.record(FIVE_PROFILES, final_indices, requirement)

    usages = [
        tracker.usage(tracker.persona_key(profile)) for profile in FIVE_PROFILES
    ]
    assert all(u <= 2 for u in usages), f"Limit verletzt: {usages}"
    assert sum(usages) == 10, (
        f"Erwartet 10 Interview-Slots (5 Abschnitte x 2), erhalten {sum(usages)}"
    )


TWO_PROFILES = FIVE_PROFILES[:2]


def test_exhaustion_fallback_reuses_with_different_context():
    """Testplan #1303: Sind ALLE Personas ausgeschoepft, faellt der Scheduler
    auf Wiederverwendung zurueck — mit anderem Kontext zuerst."""
    tracker = InterviewPanelTracker(max_interviews_per_persona=2)
    tracker.record(TWO_PROFILES, [0, 1], "Preisbewertung durch Konsumenten")
    tracker.record(TWO_PROFILES, [0, 1], "Kaufentscheidung im Einzelhandel")

    indices, note = tracker.apply_selection(
        profiles=TWO_PROFILES,
        selected_indices=[0, 1],
        requirement="Umweltbilanz der Verpackung",
    )

    assert sorted(indices) == [0, 1], "Ausschoepfung darf nicht zu einem leeren Panel fuehren"
    assert "ausschoepfung" in note.lower(), (
        f"Fallback muss im Reasoning sichtbar sein, war: {note!r}"
    )


def test_exhaustion_last_resort_allows_same_context_rather_than_empty_panel():
    """Auch bei identischem Aspekt darf der absolute Notfall wiederverwenden —
    ein leeres Panel kostet den Bericht seine Stakeholder-Stimmen (#1303)."""
    tracker = InterviewPanelTracker(max_interviews_per_persona=2)
    tracker.record(TWO_PROFILES, [0, 1], "Preisbewertung durch Konsumenten")
    tracker.record(TWO_PROFILES, [0, 1], "Preisbewertung durch Konsumenten")

    indices, note = tracker.apply_selection(
        profiles=TWO_PROFILES,
        selected_indices=[0, 1],
        requirement="Preisbewertung durch Konsumenten",
    )

    assert sorted(indices) == [0, 1]
    assert note


def test_same_context_reuse_blocked_while_fresh_alternatives_exist():
    """Wiederverwendung mit gleichem Aspekt wird blockiert, solange frische
    Personas verfuegbar sind ('muss signifikant anders sein')."""
    tracker = InterviewPanelTracker()
    tracker.record(FIVE_PROFILES, [0], "Preisbewertung durch Konsumenten")

    indices, note = tracker.apply_selection(
        profiles=FIVE_PROFILES,
        selected_indices=[0],
        requirement="Preisbewertung durch Konsumenten",
    )

    assert 0 not in indices, (
        f"Gleicher Aspekt + frische Alternativen: Persona 0 durfte nicht "
        f"wiederverwendet werden, Panel war {indices}"
    )
    assert 1 in indices, "Backfill soll eine frische Persona nachziehen"
    assert note


def test_fresh_personas_preferred_over_under_cap_reuse():
    """'Neue Abschnitte ziehen bevorzugt noch nicht befragte Personas' —
    Frische schlagen Wiederholung, auch wenn die Wiederholung regelkonform waere."""
    tracker = InterviewPanelTracker()
    tracker.record(FIVE_PROFILES, [0, 1], "Thema A")

    indices, _note = tracker.apply_selection(
        profiles=FIVE_PROFILES,
        selected_indices=[0, 1],
        requirement="Thema B",
    )

    assert set(indices) <= {2, 3, 4}, (
        f"Frische Personas haetten Vorrang, Panel war {indices}"
    )


def test_at_cap_persona_excluded_while_supply_remains():
    tracker = InterviewPanelTracker(max_interviews_per_persona=2)
    tracker.record(FIVE_PROFILES, [0, 0], "Thema A")
    tracker.record(FIVE_PROFILES, [0], "Thema B")

    indices, _note = tracker.apply_selection(
        profiles=FIVE_PROFILES,
        selected_indices=[0, 1],
        requirement="Thema C",
    )

    assert 0 not in indices
    assert indices


def test_llm_order_preserved_within_classes():
    """Die Relevanz-Rangfolge des LLM gilt innerhalb jeder Klasse weiter."""
    tracker = InterviewPanelTracker()
    tracker.record(FIVE_PROFILES, [0], "Thema A")

    indices, _note = tracker.apply_selection(
        profiles=FIVE_PROFILES,
        selected_indices=[3, 2],
        requirement="Thema B",
    )

    assert indices == [3, 2]


def test_invalid_indices_ignored():
    tracker = InterviewPanelTracker()

    indices, _note = tracker.apply_selection(
        profiles=FIVE_PROFILES,
        selected_indices=[99, -1, 1],
        requirement="Thema A",
    )

    assert indices == [1]


# ---------------------------------------------------------------------------
# Metrik: panel_overlap_ratio
# ---------------------------------------------------------------------------


def test_panel_overlap_ratio_identical_panels_is_one():
    assert panel_overlap_ratio(["A", "B"], ["B", "A"]) == 1.0


def test_panel_overlap_ratio_disjoint_panels_is_zero():
    assert panel_overlap_ratio(["A", "B"], ["C", "D"]) == 0.0


def test_panel_overlap_ratio_partial_overlap():
    # |A ∩ B| = 1, |A ∪ B| = 3 → Jaccard 1/3
    assert panel_overlap_ratio(["A", "B"], ["B", "C"]) == pytest.approx(1 / 3)


def test_panel_overlap_ratio_empty_panel_is_zero_not_error():
    assert panel_overlap_ratio([], ["A"]) == 0.0
    assert panel_overlap_ratio([], []) == 0.0


def test_aspects_differ_distinguishes_topics():
    assert aspects_differ(
        "Wie wirkt sich der Preis auf Verbraucher aus?",
        "Welche Risiken sieht der Handel in der Lieferkette?",
    )
    assert not aspects_differ(
        "Wie wirkt sich der Preis auf Verbraucher aus?",
        "Wirkt sich der Preis auf Verbraucher aus?",
    )


# ---------------------------------------------------------------------------
# Integration: Verdrahtung ueber GraphToolsService.interview_agents
# ---------------------------------------------------------------------------

SIX_PROFILES = [
    {
        "realname": f"Persona {i}",
        "username": f"persona_{i}",
        "profession": f"Rolle {i}",
        "bio": f"Bio von Persona {i}",
    }
    for i in range(6)
]


def _api(results: dict) -> dict:
    return {
        "success": True,
        "interviews_count": len(results),
        "result": {"results": results},
        "timestamp": "2026-08-23T00:00:00Z",
    }


def _make_service(max_per_persona: int | None) -> GraphToolsService:
    svc = GraphToolsService(
        storage=MagicMock(),
        llm_client=MagicMock(),
        max_interviews_per_persona=max_per_persona,
    )
    svc.llm.chat_json.return_value = {
        "selected_indices": [0, 1, 2],
        "reasoning": "Testauswahl",
        "questions": ["Wie bewerten Sie das?"],
    }
    svc.llm.chat.return_value = "Zusammenfassung."
    svc._load_agent_profiles = MagicMock(return_value=SIX_PROFILES)
    return svc


def _run(svc: GraphToolsService, requirement: str, *, success: bool = True):
    api_result = (
        _api({f"reddit_{i}": {"response": f"Antwort {i}."} for i in range(len(SIX_PROFILES))})
        if success
        else {"success": False, "error": "simulation not running"}
    )
    store = MagicMock()
    store.read_json.side_effect = lambda simulation_id, name, default=None: (
        SIX_PROFILES if name == "reddit_profiles" else default
    )
    from app.services.sim import interview_direct

    with patch(
        "app.services.simulation_runner.SimulationRunner.check_env_alive",
        return_value=False,
    ), patch(
        "app.services.sim.interview_client.check_env_alive",
        return_value=False,
    ), patch.object(
        interview_direct, "_store", return_value=store
    ), patch(
        "app.services.simulation_runner.SimulationRunner.interview_agents_batch",
        return_value=api_result,
    ):
        return svc.interview_agents(
            simulation_id="sim_1303",
            interview_requirement=requirement,
            simulation_requirement="Kontext",
            max_agents=3,
        )


def test_wiring_second_section_rotates_to_uninterviewed_personas():
    """Integration: zwei Abschnitte, dasselbe LLM beharrt auf [0, 1, 2] —
    der zweite Abschnitt bekommt die frischen Personas 3–5, und die
    Panel-Ueberlappung sinkt messbar auf 0."""
    svc = _make_service(max_per_persona=None)
    with patch.object(Config, "REPORT_INTERVIEW_MAX_PER_PERSONA", 1):
        section_one = _run(svc, "Abschnitt Eins: Preisbewertung")
        section_two = _run(svc, "Abschnitt Zwei: Lieferkettenrisiken")

    names_one = {i.agent_name for i in section_one.interviews}
    names_two = {i.agent_name for i in section_two.interviews}
    assert names_one == {"Persona 0", "Persona 1", "Persona 2"}
    assert names_two == {"Persona 3", "Persona 4", "Persona 5"}

    rotated = panel_overlap_ratio(names_one, names_two)
    naive = panel_overlap_ratio(names_one, {"Persona 0", "Persona 1", "Persona 2"})
    assert rotated == 0.0
    assert rotated < naive, (
        f"Panel-Ueberlappung soll gegenueber Wiederverwendung sinken: "
        f"{rotated} !< {naive}"
    )


def test_wiring_failed_batch_does_not_count_towards_limit():
    """Ein gescheitertes Interview hat keine Stimme geliefert und darf das
    Diversitaetskonto nicht belasten."""
    svc = _make_service(max_per_persona=None)
    with patch.object(Config, "REPORT_INTERVIEW_MAX_PER_PERSONA", 1):
        failed = _run(svc, "Abschnitt Eins", success=False)
        assert failed.terminal_failure
        second = _run(svc, "Abschnitt Zwei")

    names_second = {i.agent_name for i in second.interviews}
    assert names_second == {"Persona 0", "Persona 1", "Persona 2"}, (
        "Nach gescheiterter Batch sind die Personas weiterhin ungenutzt"
    )


def test_wiring_rotation_note_visible_in_selection_reasoning():
    svc = _make_service(max_per_persona=None)
    with patch.object(Config, "REPORT_INTERVIEW_MAX_PER_PERSONA", 1):
        _run(svc, "Abschnitt Eins")
        section_two = _run(svc, "Abschnitt Zwei")

    assert "rotation" in section_two.selection_reasoning.lower(), (
        f"Der Grund fuer die Ersetzung soll im Reasoning sichtbar sein, "
        f"war: {section_two.selection_reasoning!r}"
    )


def test_config_default_is_read_and_zero_disables_rotation():
    with patch.object(Config, "REPORT_INTERVIEW_MAX_PER_PERSONA", 3):
        svc = GraphToolsService(storage=MagicMock())
        assert svc.panel_tracker.max_interviews_per_persona == 3

    with patch.object(Config, "REPORT_INTERVIEW_MAX_PER_PERSONA", 0):
        svc_disabled = GraphToolsService(storage=MagicMock())
        assert svc_disabled.panel_tracker is None, (
            "REPORT_INTERVIEW_MAX_PER_PERSONA=0 schaltet die Rotation ab"
        )


def test_wiring_prompt_carries_usage_hints(monkeypatch: pytest.MonkeyPatch):
    """Das LLM soll die Nutzungszahlen sehen und frische Personas bevorzugen —
    harter Filter bleibt die Garantie, der Hinweis verbessert das Ranking."""
    captured: dict = {}

    def fake_chat_json(**kwargs):
        # Der erste Call ist die Agent-Auswahl, der zweite die Fragegenerierung.
        if "messages" not in captured:
            captured["messages"] = kwargs["messages"]
        return {
            "selected_indices": [0],
            "reasoning": "r",
            "questions": ["q"],
        }

    svc = _make_service(max_per_persona=None)
    monkeypatch.setattr(Config, "REPORT_INTERVIEW_MAX_PER_PERSONA", 2)
    svc.llm.chat_json.side_effect = fake_chat_json
    tracker = svc.panel_tracker
    tracker.record(SIX_PROFILES, [0], "Frueheres Thema")

    _run(svc, "Neues Thema")

    user_prompt = captured["messages"][-1]["content"]
    system_prompt = captured["messages"][0]["content"]
    assert '"times_interviewed": 1' in user_prompt
    assert "times_interviewed" in system_prompt
    assert "clearly different aspect" in system_prompt
