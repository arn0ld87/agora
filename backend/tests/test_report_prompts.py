"""Tests für services/report_prompts.py (Issue #48, EPIC-07-ST-04).

Sichern: alle Prompt-Bausteine existieren, sind nicht-leer, enthalten
ihre erwarteten Format-Platzhalter, und der Re-Export in
``services/report_agent`` liefert dieselben Objekte (Wire-Identity).
"""

import pytest

from app.services import report_agent
from app.services import report_prompts


# (Name, erwartete Format-Platzhalter)
PROMPT_SPECS = [
    # Planning
    ("PLAN_SYSTEM_PROMPT_TEMPLATE", ["{language}"]),
    ("PLAN_USER_PROMPT_TEMPLATE", [
        "{simulation_requirement}",
        "{total_nodes}",
        "{total_edges}",
        "{entity_types}",
        "{total_entities}",
        "{related_facts_json}",
        "{required_sections}",
    ]),
    # Sections
    ("SECTION_SYSTEM_PROMPT_TEMPLATE", [
        "{report_title}",
        "{report_summary}",
        "{simulation_requirement}",
        "{section_title}",
        "{language}",
        "{tools_description}",
    ]),
    ("SECTION_USER_PROMPT_TEMPLATE", [
        "{previous_content}",
        "{section_title}",
    ]),
    # Reflection / ReACT
    ("REACT_OBSERVATION_TEMPLATE", [
        "{tool_name}",
        "{result}",
        "{tool_calls_count}",
        "{max_tool_calls}",
        "{used_tools_str}",
        "{unused_hint}",
    ]),
    ("REACT_INSUFFICIENT_TOOLS_MSG", [
        "{tool_calls_count}",
        "{min_tool_calls}",
        "{unused_hint}",
    ]),
    ("REACT_INSUFFICIENT_TOOLS_MSG_ALT", [
        "{tool_calls_count}",
        "{min_tool_calls}",
        "{unused_hint}",
    ]),
    ("REACT_TOOL_LIMIT_MSG", [
        "{tool_calls_count}",
        "{max_tool_calls}",
    ]),
    ("REACT_UNUSED_TOOLS_HINT", ["{unused_list}"]),
    ("REACT_FORCE_FINAL_MSG", []),
    # Chat
    ("CHAT_SYSTEM_PROMPT_TEMPLATE", [
        "{simulation_requirement}",
        "{report_content}",
        "{tools_description}",
        "{language}",
    ]),
    ("CHAT_OBSERVATION_SUFFIX", []),
]


@pytest.mark.parametrize("name", [spec[0] for spec in PROMPT_SPECS])
def test_prompt_constant_exists_and_is_non_empty_string(name):
    value = getattr(report_prompts, name)
    assert isinstance(value, str), f"{name} muss str sein"
    assert value.strip(), f"{name} darf nicht leer sein"


@pytest.mark.parametrize("name,placeholders", PROMPT_SPECS)
def test_prompt_carries_expected_placeholders(name, placeholders):
    value = getattr(report_prompts, name)
    for placeholder in placeholders:
        assert placeholder in value, (
            f"{name} fehlt der erwartete Platzhalter {placeholder!r} — "
            "Format-Aufrufer würden fehlschlagen."
        )


def test_all_prompt_names_in_dunder_all():
    # Template constants from PROMPT_SPECS plus planning helpers (M11.8a)
    expected = {spec[0] for spec in PROMPT_SPECS} | {
        "DEFAULT_REPORT_SECTIONS",
        "format_required_sections",
    }
    assert set(report_prompts.__all__) == expected


@pytest.mark.parametrize("name", [spec[0] for spec in PROMPT_SPECS])
def test_report_agent_re_exports_identity(name):
    """Re-Export liefert DASSELBE Objekt (Wire-Identity zum Schutz aller Caller)."""
    assert getattr(report_agent, name) is getattr(report_prompts, name), (
        f"{name} im report_agent ist nicht identisch mit report_prompts"
    )


class TestPromptSemantics:
    """Pinnt invariante Semantik der Prompts gegen versehentliche Verkürzung."""

    def test_prompts_no_forecast_marketing_language(self):
        """Sub-Slice 09: Entfernt Forecast-Autoritätsclaims aus LLM-Prompts.

        Alte Phrasen (Forecast-Marketing):
        - "future prediction"
        - "rehearsal of the future"
        - "god's eye view"

        Diese dürfen nicht mehr im Prod-Code vorkommen.
        """
        all_prompts = [
            report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE,
            report_prompts.PLAN_USER_PROMPT_TEMPLATE,
            report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE,
            report_prompts.SECTION_USER_PROMPT_TEMPLATE,
            report_prompts.CHAT_SYSTEM_PROMPT_TEMPLATE,
        ]
        forbidden_phrases = [
            "future prediction",
            "rehearsal of the future",
            "god's eye view",
        ]
        for phrase in forbidden_phrases:
            for prompt in all_prompts:
                assert phrase.lower() not in prompt.lower(), (
                    f"Forbidden phrase '{phrase}' found in prompt. "
                    "Use 'scenario' vocabulary instead (Sub-Slice 09)."
                )

    def test_default_outline_in_report_agent_has_no_forecast_marketing(self):
        """Sub-Slice 09 Erweiterung: Default Fallback-Outline (report_agent.py Z. 775–782).

        Source-Scan-Test: Prüft den echten Code, nicht ein Mock-Objekt.
        Der Fallback wird bei Planning-Fehler genutzt.
        """
        from pathlib import Path
        from app.services import report_agent
        src = Path(report_agent.__file__).read_text(encoding="utf-8")

        forbidden_phrases = [
            "Future Prediction Report",
            "Future trends and risk analysis based on simulation predictions",
            "Prediction Scenario and Core Findings",
            "Crowd Behavior Prediction Analysis",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in src, (
                f"Forbidden phrase {phrase!r} still in report_agent.py "
                "(Sub-Slice 09 Erweiterung — scenario-Vokabular Pflicht)."
            )

        # Positive: neuer Wortlaut muss vorhanden sein (Wording-Glossar v1, Slice C)
        assert "Scenario Evaluation Report" in src
        assert "Evaluation Scenario and Core Findings" in src

    def test_graph_tools_to_text_has_no_forecast_marketing(self):
        """Sub-Slice 09 Erweiterung: InsightForgeResult.to_text() Heading-Block (Z. 168–177).

        Source-Scan-Test: Prüft den echten Code aus graph_tools.py UND
        graph/graph_dtos.py (M11 Phase 5b PR 1 — DTOs wurden ausgegliedert).
        Die to_text()-Methode wird im LLM-Context für Scenario-Analyse genutzt.
        """
        from pathlib import Path
        from app.services import graph_tools
        from app.services.graph import graph_dtos as _graph_dtos
        src_graph_tools = Path(graph_tools.__file__).read_text(encoding="utf-8")
        src_graph_dtos = Path(_graph_dtos.__file__).read_text(encoding="utf-8")
        src = src_graph_tools + "\n" + src_graph_dtos

        forbidden_phrases = [
            "Future Prediction Deep Analysis",
            "Prediction Scenario:",
            "Prediction Data Statistics",
            "Related Prediction Facts",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in src, (
                f"Forbidden phrase {phrase!r} still in graph_tools.py or graph_dtos.py "
                "(Sub-Slice 09 Erweiterung — scenario-Vokabular Pflicht)."
            )

        # Positive: neuer Wortlaut muss vorhanden sein (Wording-Glossar v1, Slice B)
        # Nach M11 Phase 5b PR 1 leben diese Strings in graph_dtos.py
        assert "Scenario Evaluation Deep Analysis" in src
        assert "Evaluation Scenario:" in src
        assert "Evaluation Data Statistics" in src

    def test_prompts_include_scenario_vocabulary(self):
        """Sub-Slice 09: Neue Scenario-Vokabular muss präsent sein."""
        # Mindestens einige der neuen Marker sollten präsent sein
        all_prompts_str = " ".join([
            report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE,
            report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE,
        ])
        # Scenario muss erwähnt werden
        assert "scenario" in all_prompts_str.lower()
        # Assumptions sollten erwähnt werden
        assert "assumption" in all_prompts_str.lower()

    def test_plan_system_demands_json_outline(self):
        assert "JSON" in report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE
        assert "sections" in report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE
        # M11.8a: Section-Cap (Min 2 / Max 5) entfernt; Pflichtabschnitte kommen
        # über required_sections-Variable aus dem User-Prompt.
        assert "required_sections" in report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "minimum 2" not in report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "maximum 5 sections" not in report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE.lower()

    def test_section_system_forbids_markdown_headers(self):
        # Kern-Constraint: keine ## innerhalb der Section
        assert "Forbidden to use any Markdown titles" in report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE
        assert "Final Answer" in report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE

    def test_react_observation_announces_tool_call_progress(self):
        # Observation-Template muss tool_calls_count/max anzeigen
        tmpl = report_prompts.REACT_OBSERVATION_TEMPLATE
        assert "Final Answer" in tmpl
        assert "Observation" in tmpl

    def test_chat_system_prefers_report_content_over_tools(self):
        tmpl = report_prompts.CHAT_SYSTEM_PROMPT_TEMPLATE
        assert "Prioritize answering questions based on the above report" in tmpl
        # Tool-Einsatz nur falls Report unzureichend
        assert "Only call tools" in tmpl

    def test_chat_observation_suffix_is_terse_instruction(self):
        # Sehr kurzer Suffix; sollte nicht versehentlich aufgeblasen werden
        assert len(report_prompts.CHAT_OBSERVATION_SUFFIX) < 60
        assert "concis" in report_prompts.CHAT_OBSERVATION_SUFFIX.lower()


class TestFormatCallability:
    """Stellt sicher, dass die Templates mit ihren Platzhaltern formatierbar sind.

    Schützt vor unbalancierten ``{{`` / ``}}``-Sequenzen, die ``str.format``
    zur Laufzeit zum Crashen bringen würden.
    """

    def test_plan_user_template_formats(self):
        out = report_prompts.PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement="x",
            total_nodes=1,
            total_edges=2,
            entity_types=["a"],
            total_entities=3,
            related_facts_json="[]",
            required_sections="1. **Test** — desc",
        )
        assert "x" in out

    def test_section_system_template_formats(self):
        out = report_prompts.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title="T",
            report_summary="S",
            simulation_requirement="R",
            section_title="Sec",
            language="German",
            tools_description="tools",
        )
        # Doppel-Brace im Tool-Call-Beispiel muss als Single-Brace rauskommen
        assert '{"name": "Tool Name"' in out
        assert "T" in out and "Sec" in out

    def test_section_user_template_formats(self):
        out = report_prompts.SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content="prev",
            section_title="Sec",
        )
        assert "prev" in out and "Sec" in out

    def test_react_observation_template_formats(self):
        out = report_prompts.REACT_OBSERVATION_TEMPLATE.format(
            tool_name="quick_search",
            result="r",
            tool_calls_count=2,
            max_tool_calls=5,
            used_tools_str="quick_search",
            unused_hint="",
        )
        assert "quick_search" in out
        assert "2/5" in out

    def test_chat_system_template_formats(self):
        out = report_prompts.CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement="r",
            report_content="rc",
            tools_description="td",
            language="German",
        )
        assert '{"name": "Tool Name"' in out
        assert "rc" in out


def test_default_report_sections_has_eleven_entries():
    """M11.8a: Default-Pflichtabschnitt-Liste muss 11 DACH-Report-Standardabschnitte enthalten."""
    sections = report_prompts.DEFAULT_REPORT_SECTIONS
    assert len(sections) == 11
    titles = [t for t, _ in sections]
    assert "Executive Summary" in titles
    assert "Persona-Tabelle" in titles
    assert "Datenlücken" in titles
    # Jede Entry muss Tuple[str, str] mit non-empty desc sein
    for title, desc in sections:
        assert isinstance(title, str) and len(title) > 0
        assert isinstance(desc, str) and len(desc) > 0


def test_format_required_sections_renders_numbered_markdown():
    """M11.8a: format_required_sections() muss nummerierte Markdown-Liste produzieren."""
    sections = [("A", "alpha"), ("B", "beta")]
    out = report_prompts.format_required_sections(sections)
    assert "1. **A** — alpha" in out
    assert "2. **B** — beta" in out
