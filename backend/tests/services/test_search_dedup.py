"""Ergebnislose Suchen werden nicht wiederholt (Issue #1191).

Im Lauf ``report_b76cf7078229`` verbrauchte der Abschnitt „Unsicherheiten und
Datenlücken" fünf statt vier Tool-Calls und lief in den Iterationsanschlag.
Drei davon waren ergebnislose Suchen nach derselben Stakeholdergruppe
(„aufnehmende Betriebe") — einmal ``panorama_search``, zweimal
``quick_search``. Die Gruppe konnte im Datenbestand gar nicht vorkommen.

Die Tests decken die drei getroffenen Festlegungen ab: normalisierte Query,
tool-übergreifend; unterdrückte Versuche zählen nicht gegen das Tool-Budget;
die Notiz bleibt Kontextmitteilung ohne Eingriff ins Evidenzmodell.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.services.report_agent import ReportAgent
from app.services.report_agent.search_dedup import (
    REPEATED_EMPTY_SEARCH_MSG,
    EmptySearchRegistry,
    is_empty_result,
    is_search_tool,
    normalize_query,
    query_of,
    registry_for,
)


# ---------------------------------------------------------------------------
# 1. Normalisierung — was als "dieselbe Suche" gilt
# ---------------------------------------------------------------------------


def test_normalisierung_eint_schreibweisen():
    kanonisch = normalize_query("aufnehmende Betriebe")

    assert normalize_query("Aufnehmende Betriebe") == kanonisch
    assert normalize_query("aufnehmende   betriebe") == kanonisch
    assert normalize_query("  Aufnehmende Betriebe!  ") == kanonisch
    assert normalize_query("AUFNEHMENDE, BETRIEBE") == kanonisch


def test_normalisierung_trennt_verschiedene_suchen():
    assert normalize_query("aufnehmende Betriebe") != normalize_query("Betriebe")


def test_leere_query_bleibt_leer():
    assert normalize_query("") == ""
    assert normalize_query("   ") == ""


def test_query_wird_aus_beiden_parameternamen_gelesen():
    assert query_of({"query": "Betriebe"}) == "Betriebe"
    assert query_of({"interview_topic": "Betriebe"}) == "Betriebe"
    assert query_of({}) == ""


def test_nur_suchwerkzeuge_werden_dedupliziert():
    assert is_search_tool("quick_search")
    assert is_search_tool("panorama_search")
    assert is_search_tool("insight_forge")
    # Ein Interview ohne Ergebnis ist ein Persona-Pool-Problem, kein
    # Suchtreffer-Problem — ein zweiter Versuch kann dort liefern.
    assert not is_search_tool("interview_agents")


# ---------------------------------------------------------------------------
# 2. Leer-Erkennung am strukturierten Ergebnis
# ---------------------------------------------------------------------------


@dataclass
class _FakeSearchResult:
    total_count: int
    facts: List[str] = field(default_factory=list)


@dataclass
class _FakePanoramaResult:
    total_facts: int
    total_entities: int
    total_relationships: int


def test_leeres_suchergebnis_wird_erkannt():
    assert is_empty_result(_FakeSearchResult(total_count=0)) is True


def test_treffer_gilt_nicht_als_leer():
    assert is_empty_result(_FakeSearchResult(total_count=3, facts=["a"])) is False


def test_leeres_panorama_ergebnis_wird_erkannt():
    leer = _FakePanoramaResult(total_facts=0, total_entities=0, total_relationships=0)
    assert is_empty_result(leer) is True


def test_panorama_mit_einer_entitaet_ist_nicht_leer():
    treffer = _FakePanoramaResult(
        total_facts=0, total_entities=1, total_relationships=0
    )
    assert is_empty_result(treffer) is False


def test_unbekanntes_ergebnisobjekt_gilt_nicht_als_leer():
    """Im Zweifel eine Suche zu viel, statt eine Fundstelle zu unterdruecken."""

    class _Fremd:
        pass

    assert is_empty_result(_Fremd()) is False
    assert is_empty_result(None) is False


# ---------------------------------------------------------------------------
# 3. Merkliste
# ---------------------------------------------------------------------------


def test_merkliste_erkennt_wiederholung_ueber_schreibweisen_hinweg():
    registry = EmptySearchRegistry()
    registry.record_empty("aufnehmende Betriebe")

    assert registry.was_empty("Aufnehmende  Betriebe!") is True
    assert registry.was_empty("Kammern") is False


def test_merkliste_wird_pro_abschnitt_zurueckgesetzt():
    registry = EmptySearchRegistry()
    registry.record_empty("aufnehmende Betriebe")
    registry.reset()

    assert registry.was_empty("aufnehmende Betriebe") is False


def test_leere_query_wird_nicht_gemerkt():
    registry = EmptySearchRegistry()
    registry.record_empty("")

    assert len(registry) == 0
    assert registry.was_empty("") is False


# ---------------------------------------------------------------------------
# 4. Der Kern: der Agent merkt sich Leertreffer tool-uebergreifend
# ---------------------------------------------------------------------------


class _AgentStub:
    """Minimaler Stub fuer den ungebundenen Aufruf von _record_tool_evidence."""

    def __init__(self) -> None:
        self.evidence_map: Dict[str, Any] = {
            "schema_version": 3,
            "report_id": "report_test",
            "simulation_id": "sim_test",
            "evidence_index": {},
            "global_evidence_refs": [],
            "sections": [],
        }
        self._active_section_evidence: list = []
        self._active_section_unresolved_evidence: list = []
        self._truncate = lambda text, length=200: (
            text[:length] if isinstance(text, str) else text
        )
        self.recorded_items: List[Dict[str, Any]] = []
        self._record_evidence_item = self.recorded_items.append


def test_leertreffer_wird_gemerkt_und_gilt_fuer_anderes_werkzeug():
    """Der belegte Fall: panorama_search leer, danach quick_search dieselbe Query.

    Vor dem Fix hatte der Agent keinerlei Gedaechtnis fuer erfolglose Suchen —
    dieselbe Suche lief mit dem naechsten Werkzeug erneut.
    """
    agent = _AgentStub()

    ReportAgent._record_tool_evidence(
        agent,
        "panorama_search",
        {"query": "aufnehmende Betriebe"},
        _FakePanoramaResult(total_facts=0, total_entities=0, total_relationships=0),
        "Analysis Query: aufnehmende Betriebe",
        6,
    )

    # Tool-uebergreifend und schreibweisen-unabhaengig.
    assert registry_for(agent).was_empty("Aufnehmende Betriebe") is True


def test_treffer_wird_nicht_als_leertreffer_gemerkt():
    agent = _AgentStub()

    ReportAgent._record_tool_evidence(
        agent,
        "quick_search",
        {"query": "Kammern"},
        _FakeSearchResult(total_count=0, facts=[]),
        "Search Query: Kammern\nFound 0 related results",
        6,
    )
    ReportAgent._record_tool_evidence(
        agent,
        "quick_search",
        {"query": "Umschulende"},
        _FakeSearchResult(total_count=2, facts=["Fakt A", "Fakt B"]),
        "Search Query: Umschulende\nFound 2 related results",
        6,
    )

    assert registry_for(agent).was_empty("Kammern") is True
    assert registry_for(agent).was_empty("Umschulende") is False


def test_interview_leertreffer_wird_nicht_gemerkt():
    agent = _AgentStub()

    ReportAgent._record_tool_evidence(
        agent,
        "interview_agents",
        {"interview_topic": "aufnehmende Betriebe"},
        _FakeSearchResult(total_count=0),
        "",
        6,
    )

    assert registry_for(agent).was_empty("aufnehmende Betriebe") is False


def test_registry_existiert_auch_ohne_konstruktor():
    """Viele Tests bauen den Agent ueber __new__ — die Merkliste darf nie fehlen."""
    agent = ReportAgent.__new__(ReportAgent)

    assert isinstance(agent.empty_searches, EmptySearchRegistry)
    assert registry_for(agent).was_empty("irgendwas") is False


# ---------------------------------------------------------------------------
# 5. Der Hinweis an das Modell
# ---------------------------------------------------------------------------


def test_hinweis_benennt_datenluecke_und_budgetfreiheit():
    text = REPEATED_EMPTY_SEARCH_MSG.format(
        query="aufnehmende Betriebe", tool_calls_count=3, max_tool_calls=5
    )

    assert "aufnehmende Betriebe" in text
    # Ein Leertreffer ist ein Befund — das Modell soll ihn als Datenluecke
    # benennen, nicht zum naechsten Werkzeug greifen.
    assert "Datenlücke" in text
    assert "nicht gegen dein Tool-Budget" in text
    assert "3/5" in text
