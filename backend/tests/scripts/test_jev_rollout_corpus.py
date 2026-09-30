"""Corpus extraction keeps query/fact provenance and excludes obvious PII."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "jev_rollout_corpus.py"
_SPEC = importlib.util.spec_from_file_location("jev_rollout_corpus", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
corpus = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = corpus
_SPEC.loader.exec_module(corpus)


def test_logged_queries_keep_report_graph_pairing(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports" / "report-1"
    report_dir.mkdir(parents=True)
    entries = [
        {"action": "start", "details": {"graph_id": "graph-1"}},
        {
            "action": "tool_call",
            "details": {
                "tool_name": "quick_search",
                "parameters": {"query": "  Bundeskanzleramt  Stellungnahme  "},
            },
        },
        {
            "action": "tool_call",
            "details": {"tool_name": "interview_agents", "parameters": {"query": "ignore"}},
        },
    ]
    (report_dir / "agent_log.jsonl").write_text(
        "\n".join(json.dumps(entry) for entry in entries), encoding="utf-8"
    )

    assert corpus._logged_queries(tmp_path / "reports") == [
        corpus.LoggedQuery("graph-1", "report-1", "Bundeskanzleramt Stellungnahme")
    ]


def test_select_cases_uses_same_edge_and_filters_sensitive_text() -> None:
    queries = [
        corpus.LoggedQuery("graph-1", "report-1", "Bundeskanzleramt"),
        corpus.LoggedQuery("graph-1", "report-1", "Bundeskanzleramt"),
        corpus.LoggedQuery("graph-1", "report-1", "kontakt@example.org"),
    ]
    edges = {
        "graph-1": [
            corpus.Edge("edge-1", "Regierung", "Das Bundeskanzleramt veroeffentlichte eine Stellungnahme."),
            corpus.Edge("edge-2", "Stadtrat", "Der Stadtrat beschloss eine Verkehrsordnung."),
            corpus.Edge("edge-3", "Kontakt", "Kontakt: kontakt@example.org fuer Rueckfragen."),
        ]
    }

    cases, counts = corpus.select_cases(queries, edges, limit=10)

    assert len(cases) == 1
    assert cases[0]["edge_uuid"] == "edge-1"
    assert cases[0]["query"] == "Bundeskanzleramt"
    assert cases[0]["fact"] == edges["graph-1"][0].fact
    assert cases[0]["expected_relevant"] is None
    assert counts == {
        "logged_queries": 3,
        "matched": 2,
        "filtered": 1,
        "eligible": 1,
        "selected": 1,
        "selected_graphs": 1,
    }


def test_selection_is_stable_and_caps_each_graph() -> None:
    queries = [
        corpus.LoggedQuery("graph-1", "report-1", f"Suchwort {number}")
        for number in range(4)
    ] + [corpus.LoggedQuery("graph-2", "report-2", "Anderes Thema")]
    edges = {
        "graph-1": [
            corpus.Edge(str(number), "Thema", f"Ein echter Fakt zu Suchwort {number}.")
            for number in range(4)
        ],
        "graph-2": [corpus.Edge("other", "Thema", "Ein Fakt zu Anderes Thema.")],
    }

    first, counts = corpus.select_cases(queries, edges, limit=5)
    second, _ = corpus.select_cases(queries, edges, limit=5)

    assert first == second
    assert len(first) == 3
    assert sum(case["graph_id"] == "graph-1" for case in first) == 2
    assert counts["selected_graphs"] == 2


def test_equal_scores_keep_the_first_edge_like_local_search() -> None:
    queries = [corpus.LoggedQuery("graph-1", "report-1", "Bundeskanzleramt")]
    edges = {
        "graph-1": [
            corpus.Edge("z-first", "Thema", "Das Bundeskanzleramt reagierte heute."),
            corpus.Edge("a-second", "Thema", "Das Bundeskanzleramt reagierte gestern."),
        ]
    }

    cases, _ = corpus.select_cases(queries, edges, limit=1)

    assert cases[0]["edge_uuid"] == "z-first"
