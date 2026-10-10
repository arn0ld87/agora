"""Stabile Abschnitts-Semantik (#1832): Kind-Aufloesung und Legacy-Titel-Mapping.

Seit #1832 plant das Modell freie Abschnittstitel; die semantische Rolle eines
Abschnitts steht im Contract-Feld ``section_kind``. Dieses Modul kapselt die
Aufloesung und den Uebergang fuer Bestandsdaten, deren persistierte Outlines
noch keinen Kind tragen: dort wird die Rolle weiterhin deterministisch aus den
historischen Preset-Titeln bzw. der historischen Keyword-Heuristik abgeleitet
(exakt das Verhalten vor #1832). Consumer duerfen Titel NIE mehr direkt matchen
-- sie lesen den Kind und fallen nur hierueber auf Altdaten zurueck.
"""
from __future__ import annotations

from ...contracts.report_contract import ReportSectionKind

# Historische Preset-Titel (DEFAULT_REPORT_SECTIONS) -> Kind. Bestandsverhalten
# der DTO-Auswahl vor #1832 (schemas.py::_SECTION_TITLE_MAP).
_LEGACY_TITLE_KINDS: dict[str, ReportSectionKind] = {
    "segment-tabelle": ReportSectionKind.segment_table,
    "persona-tabelle": ReportSectionKind.persona_table,
    "multiplikator-auswertung": ReportSectionKind.multiplier_analysis,
    "top 10 reibungspunkte": ReportSectionKind.friction_points,
    "top 10 vertrauenssignale": ReportSectionKind.trust_signals,
    "top 10 änderungen": ReportSectionKind.change_recommendations,
    "projektwirkung": ReportSectionKind.project_impact,
    "positionierung": ReportSectionKind.positioning,
    "content-ideen": ReportSectionKind.content_ideas,
    "datenlücken": ReportSectionKind.data_gaps,
}

# Historische Keyword-Heuristik (M11.8e, section_pipeline) fuer Abschnitte, die
# Persona-Zitate erwarten. Praezedenz: spezifische Kinds vor stakeholder_voices.
_LEGACY_KEYWORD_KINDS: tuple[tuple[str, ReportSectionKind], ...] = (
    ("persona", ReportSectionKind.persona_table),
    ("zielgrupp", ReportSectionKind.stakeholder_voices),
    ("segment", ReportSectionKind.segment_table),
    ("multipli", ReportSectionKind.multiplier_analysis),
    ("friction", ReportSectionKind.friction_points),
    ("reibung", ReportSectionKind.friction_points),
    ("trust", ReportSectionKind.trust_signals),
    ("vertrauen", ReportSectionKind.trust_signals),
    ("interview", ReportSectionKind.stakeholder_voices),
    ("reaktion", ReportSectionKind.stakeholder_voices),
    ("reaction", ReportSectionKind.stakeholder_voices),
)

# Kinds, fuer die Persona-Zitate erwartet und validiert werden.
_QUOTE_RELEVANT_KINDS = frozenset({
    ReportSectionKind.stakeholder_voices,
    ReportSectionKind.persona_table,
    ReportSectionKind.segment_table,
    ReportSectionKind.multiplier_analysis,
    ReportSectionKind.friction_points,
    ReportSectionKind.trust_signals,
})


def coerce_section_kind(value: object) -> ReportSectionKind:
    """Normalisiert einen beliebigen Kind-Wert; Unbekanntes wird ``generic``."""
    if isinstance(value, ReportSectionKind):
        return value
    if value is None:
        return ReportSectionKind.generic
    try:
        return ReportSectionKind(str(value).strip().lower())
    except ValueError:
        return ReportSectionKind.generic


def legacy_kind_for_schema(title: str) -> ReportSectionKind:
    """Bestandsverhalten der DTO-Auswahl: nur exakte historische Preset-Titel."""
    normalized = str(title or "").strip().lower()
    return _LEGACY_TITLE_KINDS.get(normalized, ReportSectionKind.generic)


def legacy_kind_for_quotes(title: str) -> ReportSectionKind:
    """Bestandsverhalten der Zitat-Erkennung (M11.8e): exakte Titel, dann Keywords."""
    exact = legacy_kind_for_schema(title)
    if exact is not ReportSectionKind.generic:
        return exact
    lowered = str(title or "").lower()
    for keyword, kind in _LEGACY_KEYWORD_KINDS:
        if keyword in lowered:
            return kind
    return ReportSectionKind.generic


def section_kind_expects_quotes(kind: ReportSectionKind) -> bool:
    """True, wenn fuer diesen Kind Persona-Zitate erwartet und validiert werden."""
    return kind in _QUOTE_RELEVANT_KINDS


__all__ = [
    "coerce_section_kind",
    "legacy_kind_for_quotes",
    "legacy_kind_for_schema",
    "section_kind_expects_quotes",
]
