"""Tests fuer _section_dedup_check (Sub-Slice 13)."""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

from app.services.report_agent import ReportAgent


def _make_agent(embed_fn=None) -> ReportAgent:
    """Minimaler ReportAgent ohne lebenden Storage."""
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_test"
    agent.simulation_id = "sim_test"
    agent.simulation_requirement = "Testreq"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = None
    agent._active_section_evidence = []
    agent._current_section_index = None
    # _embed_cache steuert, was _try_get_embedder zurueckliefert
    agent._embed_cache = embed_fn
    return agent


def _section(idx: int, summary: str) -> Dict[str, Any]:
    return {"section_index": idx, "section_summary": summary, "section_title": summary}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_none_for_empty_existing():
    agent = _make_agent(embed_fn=None)
    result = agent._section_dedup_check("Irgendein Inhalt hier", [])
    assert result is None


def test_returns_none_for_empty_summary():
    agent = _make_agent(embed_fn=None)
    existing = [_section(0, "Ein vorhandener Abschnitt mit Text")]
    result = agent._section_dedup_check("", existing)
    assert result is None


def test_jaccard_marks_duplicate_when_no_embedder():
    """Zwei fast identische Summaries -> Jaccard-Marker."""
    agent = _make_agent(embed_fn=None)
    base_text = (
        "Die Simulation zeigt eine starke Echo-Kammer-Bildung unter den Agenten "
        "mit hohem Polarisationsindex und niedrigem Brückenagenten-Anteil."
    )
    # zweite Summary: minimale Variation, aber >85% Jaccard-Overlap
    near_duplicate = (
        "Die Simulation zeigt eine starke Echo-Kammer-Bildung unter den Agenten "
        "mit hohem Polarisationsindex und sehr niedrigem Brückenagenten-Anteil."
    )
    existing = [_section(0, base_text)]
    result = agent._section_dedup_check(near_duplicate, existing)
    assert result is not None
    assert result["source"] == "section_dedup"
    assert result["raw"]["method"] == "jaccard"
    assert result["raw"]["matched_section_index"] == 0


def test_jaccard_returns_none_for_distinct_summaries():
    """Zwei komplett verschiedene Summaries -> None."""
    agent = _make_agent(embed_fn=None)
    existing = [_section(0, "Katzen schlafen sehr gerne und sind nachtaktive Tiere.")]
    result = agent._section_dedup_check(
        "Die wirtschaftliche Lage in der Region hat sich deutlich verbessert.", existing
    )
    assert result is None


def test_cosine_path_with_mock_embedder():
    """Mock-Embedder liefert identische Vektoren -> cosine=1.0 -> Marker mit method=cosine."""
    vec = [1.0, 0.0, 0.0]
    mock_embed = MagicMock(return_value=vec)
    agent = _make_agent(embed_fn=mock_embed)

    existing = [_section(2, "Ein Abschnitt ueber Simulation und Agenten")]
    result = agent._section_dedup_check("Ein Abschnitt ueber Simulation und Agenten", existing)
    assert result is not None
    assert result["source"] == "section_dedup"
    assert result["raw"]["method"] == "cosine"
    assert result["raw"]["similarity"] == 1.0
    assert result["raw"]["matched_section_index"] == 2
