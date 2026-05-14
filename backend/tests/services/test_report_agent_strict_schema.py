"""
TDD-Tests für M11.8d — chat_json strict-schema-Mode in report_agent.

Prüft:
1. planning.py::plan_outline() übergibt schema=PlanResponse an chat_json.
2. workflow.py::generate_section_metadata() übergibt schema=<DTO> an chat_json.
3. _section_schema_for() wählt korrekte DTOs nach Section-Titel.
4. Fallback-Pfad (LLM raised) in plan_outline() bleibt stabil.
5. Fallback-Pfad (chat_json raised) in generate_section_metadata() gibt {} zurück.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.report_agent.schemas import (
    PlanResponse,
    PlanSection,
    SectionMetadata,
    _section_schema_for,
)
from app.services.report_prompts import DEFAULT_REPORT_SECTIONS
from app.contracts.report_v3 import (
    ContentIdea,
    DataGap,
    FrictionPoint,
    Multiplier,
    Persona,
    PositioningVariant,
    ProjectImpact,
    Segment,
    TrustSignal,
    ChangeRecommendation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent() -> object:
    """Minimaler ReportAgent-Stub ohne echten LLM-Call."""
    from app.services.report_agent import ReportAgent

    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_m118d"
    agent.simulation_id = "sim_m118d"
    agent.simulation_requirement = "Strict-Schema-Test-Requirement"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.graph_tools.get_simulation_context.return_value = {
        "graph_statistics": {
            "total_nodes": 5,
            "total_edges": 3,
            "entity_types": {"Person": 2},
        },
        "total_entities": 5,
        "related_facts": [],
    }
    agent.tools = {}
    agent.report_logger = None
    agent.console_logger = None
    agent.evidence_map = None
    agent._active_section_evidence = []
    agent._current_section_index = None
    agent._embed_cache = None
    return agent


def _default_response_sections(description: str = "Pflichtabschnitt") -> list[dict[str, str]]:
    return [
        {"title": title, "description": f"{description}: {title}"}
        for title, _ in DEFAULT_REPORT_SECTIONS
    ]

# ---------------------------------------------------------------------------
# 1. PlanResponse DTO — Struktur
# ---------------------------------------------------------------------------

class TestPlanResponse:
    def test_plan_response_happy_path(self):
        """PlanResponse akzeptiert korrekte Struktur."""
        data = {
            "title": "Test Report",
            "summary": "Eine Zusammenfassung",
            "sections": [
                {"title": "Einleitung", "description": "Hintergrund und Kontext"},
                {"title": "Hauptbefunde", "description": "Zentrale Erkenntnisse"},
            ],
        }
        pr = PlanResponse.model_validate(data)
        assert pr.title == "Test Report"
        assert len(pr.sections) == 2
        assert pr.sections[0].title == "Einleitung"

    def test_plan_response_extra_field_forbidden(self):
        """PlanResponse lehnt Extra-Felder ab (extra='forbid')."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PlanResponse.model_validate({
                "title": "T",
                "summary": "S",
                "sections": [],
                "unknown_field": "x",
            })

    def test_plan_section_default_description(self):
        """PlanSection hat Default-description '—'."""
        ps = PlanSection(title="Abschnitt")
        assert ps.description == "—"

    def test_plan_response_model_json_schema_is_dict(self):
        """model_json_schema() liefert ein dict (kein Inline-String)."""
        schema = PlanResponse.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema


# ---------------------------------------------------------------------------
# 2. planning.py — chat_json wird mit schema=PlanResponse aufgerufen
# ---------------------------------------------------------------------------

class TestPlanOutlineStrictSchema:
    def test_plan_outline_passes_schema_to_chat_json(self):
        """plan_outline() muss chat_json mit schema=PlanResponse aufrufen."""
        agent = _make_agent()
        agent.llm.chat_json.return_value = {
            "title": "Strikter Report",
            "summary": "Zusammenfassung",
            "sections": _default_response_sections("Hintergrund"),
        }

        agent.plan_outline()

        # chat_json muss aufgerufen worden sein
        assert agent.llm.chat_json.called, "chat_json wurde nicht aufgerufen"

        # schema= und schema_name= Argumente prüfen
        call_kwargs = agent.llm.chat_json.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        # Pydantic-Modell als positional arg möglich — prüfe beides
        all_args = list(call_kwargs.args) + list(kwargs.values())

        assert kwargs.get("schema") is PlanResponse or PlanResponse in all_args, (
            f"schema=PlanResponse nicht in chat_json-Aufruf. "
            f"Kwargs: {kwargs}, Args: {call_kwargs.args}"
        )
        assert kwargs.get("schema_name") == "report_plan", (
            f"schema_name='report_plan' erwartet, got: {kwargs.get('schema_name')!r}"
        )

    def test_plan_outline_strict_schema_with_correct_structure(self):
        """plan_outline() verarbeitet PlanResponse-konforme Antwort korrekt."""
        agent = _make_agent()
        agent.llm.chat_json.return_value = {
            "title": "DACH Marktanalyse",
            "summary": "Einschätzung der Marktdynamik",
            "sections": _default_response_sections("Analyse"),
        }

        outline = agent.plan_outline()

        assert outline.title == "DACH Marktanalyse"
        assert len(outline.sections) == len(DEFAULT_REPORT_SECTIONS)

    def test_plan_outline_fallback_on_llm_error_still_stable(self):
        """Fallback-Outline ist stabil wenn chat_json raised."""
        agent = _make_agent()
        agent.llm.chat_json.side_effect = RuntimeError("Provider nicht erreichbar")

        outline = agent.plan_outline()

        # Fallback-Outline muss mindestens 2 Sections haben
        assert len(outline.sections) >= 2
        for section in outline.sections:
            assert section.description, f"Fallback-Section '{section.title}' hat kein description"


# ---------------------------------------------------------------------------
# 3. _section_schema_for() — DTO-Mapping nach Section-Titel
# ---------------------------------------------------------------------------

class TestSectionSchemaFor:
    @pytest.mark.parametrize("title,expected_cls", [
        ("Persona-Tabelle", Persona),
        ("Segment-Tabelle", Segment),
        ("Multiplikator-Auswertung", Multiplier),
        ("Top 10 Reibungspunkte", FrictionPoint),
        ("Top 10 Vertrauenssignale", TrustSignal),
        ("Top 10 Änderungen", ChangeRecommendation),
        ("Projektwirkung", ProjectImpact),
        ("Positionierung", PositioningVariant),
        ("Content-Ideen", ContentIdea),
        ("Datenlücken", DataGap),
    ])
    def test_schema_mapping(self, title: str, expected_cls: type):
        result = _section_schema_for(title)
        assert result is expected_cls, (
            f"_section_schema_for({title!r}) → {result.__name__!r}, "
            f"erwartet: {expected_cls.__name__!r}"
        )

    def test_unknown_section_falls_back_to_section_metadata(self):
        """Unbekannte Section-Titel → SectionMetadata als Fallback."""
        result = _section_schema_for("Allgemeine Einleitung")
        assert result is SectionMetadata

    def test_case_insensitive_matching(self):
        """Matching ist case-insensitiv."""
        assert _section_schema_for("PERSONA-TABELLE") is Persona
        assert _section_schema_for("top 10 vertrauenssignale") is TrustSignal

    def test_free_persona_analysis_title_uses_generic_metadata(self):
        """Freie 3-Section-Fallback-Titel dürfen kein volles Persona-DTO erzwingen."""
        assert _section_schema_for("Persona Reaction Analysis") is SectionMetadata


# ---------------------------------------------------------------------------
# 4. generate_section_metadata() — chat_json mit DTO-Schema
# ---------------------------------------------------------------------------

class TestGenerateSectionMetadata:
    def test_passes_correct_schema_to_chat_json(self):
        """generate_section_metadata() ruft chat_json mit korrektem schema= auf."""
        from app.services.report_agent.workflow import generate_section_metadata

        agent = _make_agent()
        # SectionMetadata-konformes Return-Dict
        agent.llm.chat_json.return_value = {
            "section_title": "Allgemeine Einleitung",
            "key_takeaways": [{"statement": "Wichtige Erkenntnis", "confidence": "high"}],
            "data_gaps": [],
        }

        generate_section_metadata(
            agent,
            section_title="Allgemeine Einleitung",
            section_content="# Einleitung\n\nHier steht der Abschnittsinhalt.",
            section_index=1,
        )

        assert agent.llm.chat_json.called
        call_kwargs = agent.llm.chat_json.call_args.kwargs
        # Fallback: SectionMetadata für unbekannten Titel
        assert call_kwargs.get("schema") is SectionMetadata
        assert "section_metadata" in call_kwargs.get("schema_name", "")

    def test_passes_persona_schema_for_required_persona_table(self):
        """generate_section_metadata() wählt Persona-DTO für den Pflichtabschnitt."""
        from app.services.report_agent.workflow import generate_section_metadata

        agent = _make_agent()
        # Persona ist ein komplexes Modell — chat_json wird es validieren.
        # Hier testen wir nur, dass das richtige schema= übergeben wird.
        # Bei Validierungsfehler gibt die Funktion {} zurück (Fehler-Pfad).
        agent.llm.chat_json.side_effect = Exception("Schema-Mismatch-simuliert")

        result = generate_section_metadata(
            agent,
            section_title="Persona-Tabelle",
            section_content="Persona Alpha ist 35-50 Jahre alt.",
            section_index=2,
        )

        assert result == {}, "Bei chat_json-Fehler muss {} zurückgegeben werden"
        call_kwargs = agent.llm.chat_json.call_args.kwargs
        assert call_kwargs.get("schema") is Persona

    def test_metadata_prompt_uses_generic_field_name_examples(self):
        """Schema-Regeln dürfen keine SectionMetadata-spezifischen Felder suggerieren."""
        from app.services.report_agent.workflow import generate_section_metadata

        agent = _make_agent()
        agent.llm.chat_json.side_effect = Exception("Schema-Mismatch-simuliert")

        generate_section_metadata(
            agent,
            section_title="Persona-Tabelle",
            section_content="Persona Alpha ist 35-50 Jahre alt.",
            section_index=2,
        )

        call_kwargs = agent.llm.chat_json.call_args.kwargs
        system_msg = call_kwargs["messages"][0]["content"]
        assert "`field_name` statt `fieldName`" in system_msg
        assert "`section_title`, NICHT `sectionTitle`" not in system_msg
        assert "`key_takeaways`, NICHT `keyFindings`" not in system_msg

    def test_returns_empty_dict_on_exception(self):
        """Fehler in chat_json geben {} zurück — Hauptgenerierung unblockiert."""
        from app.services.report_agent.workflow import generate_section_metadata

        agent = _make_agent()
        agent.llm.chat_json.side_effect = RuntimeError("Provider-Fehler")

        result = generate_section_metadata(
            agent,
            section_title="Irgendein Abschnitt",
            section_content="Irgendein Inhalt",
            section_index=3,
        )

        assert result == {}

    def test_context_is_report(self):
        """generate_section_metadata() setzt context='report' am chat_json-Aufruf."""
        from app.services.report_agent.workflow import generate_section_metadata

        agent = _make_agent()
        agent.llm.chat_json.return_value = {
            "section_title": "Test",
            "key_takeaways": [],
            "data_gaps": [],
        }

        generate_section_metadata(
            agent,
            section_title="Test",
            section_content="Inhalt.",
            section_index=1,
        )

        call_kwargs = agent.llm.chat_json.call_args.kwargs
        assert call_kwargs.get("context") == "report", (
            f"context='report' erwartet, got: {call_kwargs.get('context')!r}"
        )


# ---------------------------------------------------------------------------
# 5. Akzeptanz-Check: kein "json_object" im report_agent (außer Kommentare)
# ---------------------------------------------------------------------------

class TestNoJsonObjectInReportAgent:
    def test_no_json_object_literal_in_planning(self):
        """planning.py darf 'json_object' nicht als Literal enthalten."""
        import pathlib

        planning_path = pathlib.Path(__file__).parent.parent.parent / "app/services/report_agent/planning.py"
        source = planning_path.read_text()
        # json_object darf nur in Kommentaren stehen (# ...)
        lines_with_json_object = [
            line for line in source.splitlines()
            if '"json_object"' in line and not line.strip().startswith("#")
        ]
        assert not lines_with_json_object, (
            f"Unerwartetes 'json_object' in planning.py: {lines_with_json_object}"
        )

    def test_no_json_object_literal_in_workflow(self):
        """workflow.py darf 'json_object' nicht als Literal enthalten."""
        import pathlib

        workflow_path = pathlib.Path(__file__).parent.parent.parent / "app/services/report_agent/workflow.py"
        source = workflow_path.read_text()
        lines_with_json_object = [
            line for line in source.splitlines()
            if '"json_object"' in line and not line.strip().startswith("#")
        ]
        assert not lines_with_json_object, (
            f"Unerwartetes 'json_object' in workflow.py: {lines_with_json_object}"
        )
