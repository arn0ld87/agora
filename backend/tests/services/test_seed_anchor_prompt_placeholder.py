"""Regressionstest für Issue #1244.

Der `seed_anchor`-Formathinweis in `SECTION_SYSTEM_PROMPT_TEMPLATE` enthielt
als Beispielwert einen syntaktisch gültigen String
(``seed_doc:interview_transcript_07``). Modelle haben diesen Beispielwert
wörtlich in jedes Zitat kopiert, obwohl das referenzierte Dokument gar nicht
existierte. Dieser Test stellt sicher, dass der Formathinweis keinen
kopierbaren, gültig aussehenden Literalwert mehr enthält.
"""

from app.services import report_prompts

LEAKED_EXAMPLE_ANCHOR = "seed_doc:interview_transcript_07"


def test_section_system_prompt_does_not_contain_literal_example_anchor() -> None:
    rendered = report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        report_title="T",
        report_summary="S",
        simulation_requirement="R",
        section_title="Sec",
        language="German",
        tools_description="tools",
    )

    assert LEAKED_EXAMPLE_ANCHOR not in rendered, (
        "Der gerenderte Section-Prompt enthält weiterhin den kopierbaren "
        "Beispiel-Anker aus Issue #1244 — Modelle übernehmen diesen "
        "wörtlich statt eine echte Dokument-ID einzusetzen."
    )
    # Die Formatbeschreibung selbst muss weiterhin vermittelt werden.
    assert "seed_doc:" in rendered
    assert "document ID" in rendered


def test_platzhalter_enthaelt_keine_spitzen_klammern() -> None:
    """CodeRabbit PR #1254: ``<document_id>`` bricht das Quote-Regex.

    Kopiert ein Modell den Ersatz-Platzhalter wörtlich in das
    ``<simulated_quote …>``-Tag, beendet das ``>`` in ``<document_id>`` das
    Tag vorzeitig. ``_QUOTE_TAG_RE`` findet dann null Zitate — und eine
    Section ohne Zitate gilt als gültig. Der Ersatz wäre damit unsichtbarer
    gewesen als der Beispielwert, den er ablöst.
    """
    rendered = report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        report_title="T",
        report_summary="S",
        simulation_requirement="R",
        section_title="Sec",
        language="German",
        tools_description="tools",
    )

    anchor_line = next(
        line for line in rendered.splitlines() if "seed_doc:DOCUMENT_ID" in line
    )
    assert "<" not in anchor_line and ">" not in anchor_line

    # Die Chunk-Angabe ist nach ADR-0013 Pflichtbestandteil eines echten Ankers.
    assert "#chunk:" in rendered


def test_prompt_nennt_seed_doc_nicht_mehr_als_opake_referenz() -> None:
    """Ein Anker, der laut Prompt nicht nachgeschlagen wird, lädt zum Erfinden ein."""
    rendered = report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        report_title="T",
        report_summary="S",
        simulation_requirement="R",
        section_title="Sec",
        language="German",
        tools_description="tools",
    )

    assert "opaque reference without further lookup" not in rendered
