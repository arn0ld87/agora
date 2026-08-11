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
