"""Regressionstests fuer die stabile Abschnitts-Semantik (#1832, PR-#1838-Review).

Deckt die zwei offenen Review-Findings ab:
- P1: Freie Titel duerfen die semantische Rolle nicht verlieren. Consumer lesen
  ``section_kind``; die historische Titel-Heuristik greift nur fuer Bestandsdaten.
- P2: Der Outline-Titelvertrag spiegelt die Drei-Zeichen-Untergrenze der
  Evidenz-Persistenz (kein Contract-Drift).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ReportOutlineModel,
    ReportOutlineSectionModel,
    ReportSectionKind,
)
from app.services.report_agent.schemas import (
    Persona,
    SectionMetadata,
    _make_table_metadata,
    _section_schema_for,
)
from app.services.report_agent.section_pipeline import _section_expects_quotes
from app.services.report_prompts.planning import SECTION_KIND_PROMPT_LINES


def test_prompt_list_covers_every_section_kind():
    """Prompt-Liste und Contract-Enum duerfen nicht auseinanderlaufen."""
    prompt_kinds = {name for name, _ in SECTION_KIND_PROMPT_LINES}
    assert prompt_kinds == {kind.value for kind in ReportSectionKind}


def test_free_title_with_kind_keeps_quote_validation():
    """P1: Ein freier Titel darf die Zitat-Validierung nicht umgehen."""
    title = "Stimmen aus dem Kreißsaal"
    assert _section_schema_for(title, ReportSectionKind.stakeholder_voices) is SectionMetadata
    assert _section_expects_quotes(title, ReportSectionKind.stakeholder_voices) is True


def test_specific_kind_selects_table_dto_regardless_of_title():
    """P1: Die DTO-Auswahl haengt am Kind, nicht am Titel."""
    assert _section_schema_for("Wer spricht?", "persona_table") is _make_table_metadata(Persona)


@pytest.mark.parametrize(
    "kind",
    [
        ReportSectionKind.persona_table,
        ReportSectionKind.segment_table,
        ReportSectionKind.friction_points,
        ReportSectionKind.trust_signals,
        ReportSectionKind.multiplier_analysis,
    ],
)
def test_quotes_are_validated_for_kind_based_sections(kind):
    assert _section_expects_quotes("Irgendein freier Titel", kind) is True


def test_generic_kind_keeps_historical_behaviour():
    """Bestandsdaten ohne Kind: exakte Preset-Titel und Keyword-Heuristik wie vor #1832."""
    assert _section_schema_for("Persona-Tabelle") is _make_table_metadata(Persona)
    assert _section_schema_for("Persona Reaction Analysis") is SectionMetadata
    assert _section_expects_quotes("Persona-Reaktionen auf die Kampagne") is True
    assert _section_expects_quotes("Allgemeine Einleitung") is False


def test_outline_section_title_requires_three_characters():
    """P2: kein Contract-Drift zur Evidenz-Persistenz (ReportSectionModel.section_title)."""
    with pytest.raises(ValidationError):
        ReportOutlineSectionModel(title="KI", description="Zu kurzer Titel")


def test_outline_model_accepts_free_title_with_kind():
    outline = ReportOutlineModel(
        title="Bericht",
        summary="—",
        sections=[
            ReportOutlineSectionModel(
                title="Stimmen aus dem Kreißsaal",
                description="Persona-Stimmen zur Kampagne",
                section_kind=ReportSectionKind.stakeholder_voices,
            )
        ],
    )
    assert outline.sections[0].section_kind is ReportSectionKind.stakeholder_voices


def test_unknown_kind_defaults_to_generic():
    """Ein fehlendes oder unbekanntes Kind kippt die Planung nicht."""
    section = ReportOutlineSectionModel(title="Beliebiger Titel", description="—")
    assert section.section_kind is ReportSectionKind.generic
