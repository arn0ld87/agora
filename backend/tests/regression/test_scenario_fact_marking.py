"""Szenario-Text wird in der Tool-Ausgabe gekennzeichnet (Issue #1240).

Referenz: ``report_40236c4a59f0``. Der Report zitierte „Die IHK sieht
generierte Übungsaufgaben unkritisch" als seinen überraschendsten Befund — der
Satz stand im Seed-Dokument als Konstruktionsnotiz und kam über
``insight_forge`` unter „Key Facts (Please quote these verbatim …)" ins Modell.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.graph.graph_dtos import InsightForgeResult, PanoramaResult, SearchResult
from app.services.report_agent.scenario_marking import (
    SCENARIO_FACT_MARKER,
    SCENARIO_FACT_NOTICE,
    annotate_scenario_facts,
    mark_scenario_facts,
)
from app.services.tool_execution import execute_tool

EXPECTED = "Die IHK sieht generierte Übungsaufgaben unkritisch."
DOMAIN = "22 festangestellte Dozenten stehen auf der Personalliste des Trägers."
ROLES = {"erwartung": "expected_result"}


def _insight() -> InsightForgeResult:
    return InsightForgeResult(
        query="IHK",
        simulation_requirement="",
        sub_queries=[],
        semantic_facts=[EXPECTED, DOMAIN],
        semantic_facts_provenance=[
            {"document_id": "erwartung", "chunk_id": 3},
            {"document_id": "szenario", "chunk_id": 0},
        ],
    )


def test_erwartungstext_wird_markiert_domaenenfakt_nicht():
    result = _insight()
    marked = annotate_scenario_facts(result, result.to_text(), ROLES)

    assert f'"{SCENARIO_FACT_MARKER} {EXPECTED}"' in marked
    assert f"{SCENARIO_FACT_MARKER} {DOMAIN}" not in marked
    assert marked.endswith(SCENARIO_FACT_NOTICE)


def test_ohne_rollen_bleibt_die_ausgabe_unveraendert():
    """Altprojekte ohne Manifest-Rollen: bisheriges Verhalten."""
    result = _insight()
    rendered = result.to_text()
    assert annotate_scenario_facts(result, rendered, {}) == rendered
    assert annotate_scenario_facts(result, rendered, None) == rendered


def test_panorama_und_quick_search_werden_ebenfalls_markiert():
    panorama = PanoramaResult(
        query="IHK",
        all_nodes=[],
        all_edges=[],
        active_facts=[DOMAIN],
        historical_facts=[EXPECTED],
        active_facts_provenance=[{"document_id": "szenario", "chunk_id": 0}],
        historical_facts_provenance=[{"document_id": "erwartung", "chunk_id": 1}],
    )
    assert f"{SCENARIO_FACT_MARKER} {EXPECTED}" in annotate_scenario_facts(
        panorama, panorama.to_text(), ROLES
    )

    search = SearchResult(
        facts=[EXPECTED], edges=[], nodes=[], query="IHK", total_count=1,
        fact_provenance=[{"document_id": "erwartung", "chunk_id": 1}],
    )
    assert f"{SCENARIO_FACT_MARKER} {EXPECTED}" in annotate_scenario_facts(
        search, search.to_text(), ROLES
    )


def test_markierung_ist_idempotent_und_zerschneidet_keine_laengeren_fakten():
    short = "Die IHK sieht"
    rendered = f'1. "{EXPECTED}"\n2. "{short} das anders."'
    once = mark_scenario_facts(rendered, [EXPECTED, short])
    twice = mark_scenario_facts(once, [EXPECTED, short])

    assert once == twice
    assert once.count(SCENARIO_FACT_MARKER) == 3  # zwei Fakten + ein Hinweis
    assert f"{SCENARIO_FACT_MARKER} {SCENARIO_FACT_MARKER}" not in once


def test_execute_tool_reicht_die_markierung_an_das_modell_durch():
    class _GraphTools:
        def insight_forge(self, **_kwargs: Any) -> InsightForgeResult:
            return _insight()

    def record(*_args: Any) -> Dict[int, str]:
        return {}

    rendered = execute_tool(
        tool_name="insight_forge",
        parameters={"query": "IHK"},
        report_context="",
        graph_tools=_GraphTools(),
        web_tools=None,
        graph_id="g",
        simulation_id="s",
        simulation_requirement="",
        record_evidence=record,
        annotate_rendered=lambda result, text: annotate_scenario_facts(result, text, ROLES),
    )
    assert f"{SCENARIO_FACT_MARKER} {EXPECTED}" in rendered
