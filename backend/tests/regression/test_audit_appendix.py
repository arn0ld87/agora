"""Der Prüfapparat steht hinter dem Bericht, nicht mittendrin.

Die sieben Abschnitte des Referenzlaufs ``report_cc2ef45da5e9`` umfassten
zusammen rund 48.000 Zeichen. Der exportierte Markdown hatte rund 111.000 —
mit etwa 158 Hypothesenmarkern und 50 ``[Beleg fehlt]``-Marken. Der
Audit-Layer überwuchs den Bericht, den er prüfen sollte.

Gelöscht wird deshalb nichts. Dieselben Tabellen stehen weiterhin vollständig
im Export, nur gesammelt am Ende: ein Prüfer liest sie am Stück, ein Leser
überspringt sie. Die Marken *im* Fließtext bleiben, wo sie sind — "[Beleg
fehlt]" gilt für genau einen Satz, und diese Zuordnung ist ihr ganzer Zweck.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

from app.models.report import ReportOutline, ReportSection
from app.services.report_agent.manager import ReportManager

SECTIONS: List[Dict[str, Any]] = [
    {
        "section_index": 1,
        "title": "Ausgangslage",
        "content": "## Ausgangslage\n\nDie Schulungsquote liegt bei 31 Prozent.",
    },
    {
        "section_index": 2,
        "title": "Risiken",
        "content": "## Risiken\n\nDer ungestaffelte Vollstart ist riskant.",
    },
]

EVIDENCE_MAP: Dict[str, Any] = {
    "sections": [
        {
            "section_index": 1,
            "hypotheses": [
                {
                    "hypothesis_id": "hypothesis_01",
                    "hypothesis_text": "Die Nachtschicht bleibt unterversorgt.",
                    "rationale": "Kein Beleg gebunden.",
                    "suggested_evidence": ["Dienstplan prüfen"],
                }
            ],
            "data_gaps": [],
            "claims": [],
        },
        {
            "section_index": 2,
            "hypotheses": [
                {
                    "hypothesis_id": "hypothesis_02",
                    "hypothesis_text": "Der Rollout verzögert sich.",
                    "rationale": "Kein Beleg gebunden.",
                    "suggested_evidence": ["Projektplan prüfen"],
                }
            ],
            "data_gaps": [],
            "claims": [],
        },
    ]
}

OUTLINE = ReportOutline(
    title="Testbericht",
    summary="Zusammenfassung",
    sections=[
        ReportSection(title="Ausgangslage"),
        ReportSection(title="Risiken"),
    ],
)


def _assemble() -> str:
    with (
        patch.object(ReportManager, "get_generated_sections", return_value=SECTIONS),
        patch.object(ReportManager, "get_evidence_map", return_value=EVIDENCE_MAP),
    ):
        return ReportManager.assemble_full_report("report_test", OUTLINE)


def test_the_audit_material_moves_into_one_appendix():
    markdown = _assemble()

    assert markdown.count("## Anhang: Belegprüfung") == 1


def test_the_appendix_stands_behind_the_last_section():
    markdown = _assemble()

    assert markdown.index("Der ungestaffelte Vollstart") < markdown.index(
        "Anhang: Belegprüfung"
    )


def test_no_audit_table_interrupts_the_reading_text():
    """Zwischen den beiden Abschnitten darf nichts Geprüftes stehen."""
    markdown = _assemble()
    between = markdown[
        markdown.index("Die Schulungsquote") : markdown.index("Der ungestaffelte")
    ]

    assert "hypothesis_01" not in between


def test_every_hypothesis_survives_the_move():
    """Getrennt heißt nicht gelöscht."""
    markdown = _assemble()

    assert "Die Nachtschicht bleibt unterversorgt." in markdown
    assert "Der Rollout verzögert sich." in markdown


def test_each_appendix_block_names_its_section():
    markdown = _assemble()
    appendix = markdown[markdown.index("Anhang: Belegprüfung") :]

    assert "**Ausgangslage**" in appendix
    assert "**Risiken**" in appendix


def test_a_report_without_findings_gets_no_appendix():
    with (
        patch.object(ReportManager, "get_generated_sections", return_value=SECTIONS),
        patch.object(
            ReportManager,
            "get_evidence_map",
            return_value={"sections": [{"section_index": 1, "claims": []}]},
        ),
    ):
        markdown = ReportManager.assemble_full_report("report_test", OUTLINE)

    assert "Anhang: Belegprüfung" not in markdown


def test_the_reading_text_itself_is_unchanged():
    markdown = _assemble()

    assert "Die Schulungsquote liegt bei 31 Prozent." in markdown
    assert "Der ungestaffelte Vollstart ist riskant." in markdown
