"""Regression: ``_build_context`` haelt ``MAX_CONTEXT_LENGTH`` wirklich ein.

Root Cause: gekuerzt wurde ausschliesslich ``document_text`` gegen das
Restbudget. ``simulation_requirement`` und die Entity-Zusammenfassung gingen
ungekuerzt in den Kontext — zusammen konnten sie das Limit allein schon
ueberschreiten, und die Restbudget-Rechnung wurde dann negativ, sodass das
Dokument stillschweigend ganz entfiel, ohne dass der Ueberlauf verschwand.
"""

from __future__ import annotations

from typing import List

import pytest

from app.services.entity_reader import EntityNode
from app.services.simulation_config_generator import SimulationConfigGenerator

MAX = SimulationConfigGenerator.MAX_CONTEXT_LENGTH


def _generator() -> SimulationConfigGenerator:
    return SimulationConfigGenerator(api_key="test-key", base_url="http://localhost:11434")


def _entities(count: int, summary_length: int, type_count: int = 1) -> List[EntityNode]:
    """``_summarize_entities`` zeigt hoechstens ``ENTITIES_PER_TYPE_DISPLAY``
    Entitaeten *je Typ*. Ein grosser Entity-Block entsteht deshalb nur ueber
    viele verschiedene Typen — genau wie in einem realen Graphen."""
    return [
        EntityNode(
            uuid=f"e-{i}",
            name=f"Entity {i}",
            labels=[f"Type{i % type_count}"],
            summary="S" * summary_length,
            attributes={},
        )
        for i in range(count)
    ]


@pytest.mark.parametrize(
    "requirement_len, entity_count, entity_summary_len, document_len",
    [
        pytest.param(MAX * 2, 3, 50, 100, id="oversized-requirement"),
        pytest.param(100, 4000, 400, 100, id="oversized-entity-summary"),
        pytest.param(100, 3, 50, MAX * 3, id="oversized-document"),
        pytest.param(MAX, 4000, 400, MAX * 2, id="all-three-oversized"),
        pytest.param(MAX - 200, 3, 50, MAX, id="requirement-just-under-limit"),
    ],
)
def test_context_never_exceeds_max_length(
    requirement_len: int, entity_count: int, entity_summary_len: int, document_len: int
) -> None:
    generator = _generator()

    context = generator._build_context(
        simulation_requirement="R" * requirement_len,
        document_text="D" * document_len,
        entities=_entities(entity_count, entity_summary_len, type_count=40),
    )

    assert len(context) <= MAX, f"context is {len(context)} chars, limit is {MAX}"


def test_priority_order_requirement_before_entities_before_document() -> None:
    """Bei Knappheit gewinnt das Simulationsziel, dann die Entitaeten, zuletzt
    das Originaldokument — das Dokument ist der einzige Teil, der sich
    vollstaendig aus den anderen beiden rekonstruieren laesst (er ist Rohstoff,
    nicht Ergebnis)."""
    generator = _generator()

    context = generator._build_context(
        simulation_requirement="R" * (MAX - 100),
        document_text="D" * 5000,
        entities=_entities(3, 50),
    )

    assert len(context) <= MAX
    assert "## Simulation Requirements" in context
    assert "R" in context
    assert "DDDDD" not in context


def test_headers_are_never_cut_in_half() -> None:
    generator = _generator()

    context = generator._build_context(
        simulation_requirement="R" * 200,
        document_text="D" * (MAX * 2),
        entities=_entities(3, 50),
    )

    for header in ("## Simulation Requirements", "## Entity Information", "## Original Document Content"):
        assert context.count(header) == 1, f"header {header!r} missing or duplicated"


def test_short_inputs_are_passed_through_untouched() -> None:
    generator = _generator()

    context = generator._build_context(
        simulation_requirement="Wie reagiert die Elternschaft?",
        document_text="Kurzes Dokument.",
        entities=_entities(2, 20),
    )

    assert "Wie reagiert die Elternschaft?" in context
    assert "Kurzes Dokument." in context
    assert "truncated" not in context


def test_empty_document_adds_no_document_section() -> None:
    generator = _generator()

    context = generator._build_context(
        simulation_requirement="Ziel",
        document_text="",
        entities=_entities(1, 10),
    )

    assert "## Original Document Content" not in context
    assert len(context) <= MAX


def test_entity_summary_is_truncated_at_a_line_boundary() -> None:
    """Der Entity-Block ist zeilenweise strukturiert (``- Name: Summary``).
    Ein Schnitt mitten in einer Zeile erzeugt einen halben Entitaetsnamen, der
    wie eine echte Entitaet aussieht."""
    generator = _generator()

    context = generator._build_context(
        simulation_requirement="Ziel",
        document_text="",
        entities=_entities(4000, 400, type_count=40),
    )

    entity_block = context.split("## Entity Information", 1)[1]
    body = entity_block.split("\n", 1)[1]
    truncated_marker_lines = [line for line in body.splitlines() if "truncated" in line]
    assert truncated_marker_lines, "expected an explicit truncation marker"
    data_lines = [line for line in body.splitlines() if line.startswith("- ")]
    for line in data_lines:
        assert line.startswith("- Entity "), f"line cut mid-record: {line[:60]!r}"
