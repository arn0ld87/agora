"""Intent-Erkennung und Section-Presets für Reports.

"Was denken die Leute?" verlangt keinen elfteiligen Marketingreport mit
Content-Ideen und Positionierungsvarianten. Dieses Modul leitet aus der
Fragestellung ein Preset ab und bestimmt damit, welche Abschnitte überhaupt
erzeugt werden.

Der ``FULL``-Report bleibt unverändert erhalten und ist der Default für alles,
was sich nicht eindeutig zuordnen lässt.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, List, Sequence, Tuple

from .report_prompts import (
    DEFAULT_REPORT_SECTIONS,
    RECOMMENDATION_SECTION_DESCRIPTION,
    RECOMMENDATION_SECTION_TITLE,
)

SectionSpec = Tuple[str, str]


class ReportIntent(str, Enum):
    OPINION = "opinion"
    RISK = "risk"
    COMPARISON = "comparison"
    EXPLORATIVE = "explorative"
    FULL = "full"


#: Der vollständige Report bleibt unverändert und bezieht seine Abschnitte
#: direkt aus der bestehenden Vertragskonstante — kein zweiter Ort, der
#: driften kann.
FULL_SECTIONS: tuple[SectionSpec, ...] = tuple(DEFAULT_REPORT_SECTIONS)

OPINION_SECTIONS: tuple[SectionSpec, ...] = (
    ("Kurzfazit", "Maximal 8 Sätze: Was denken die simulierten Gruppen, und wie eindeutig ist das Bild."),
    ("Stakeholder- und Meinungsgruppen", "Welche Gruppen äußern sich, mit welcher Grundhaltung."),
    ("Zentrale Zustimmungspunkte", "Worauf sich Zustimmung stützt, mit Quellenbezug."),
    ("Zentrale Kritikpunkte", "Worauf sich Kritik stützt, mit Quellenbezug."),
    ("Konfliktlinien", "Wo die Gruppen auseinandergehen und woran das liegt."),
    ("Unsicherheiten und Datenlücken", "Was die Simulation nicht beantworten kann."),
    (RECOMMENDATION_SECTION_TITLE, RECOMMENDATION_SECTION_DESCRIPTION),
)

RISK_SECTIONS: tuple[SectionSpec, ...] = (
    ("Kurzfazit", "Maximal 8 Sätze: Welche Risiken die Simulation sichtbar macht."),
    ("Betroffene Gruppen", "Wer von den Risiken wie betroffen ist."),
    ("Zentrale Risiken", "Risiken mit Schwere, Auslöser und Quellenbezug."),
    ("Reibungspunkte und Eskalationspfade", "Wie sich Risiken in der Simulation zuspitzen."),
    ("Gegenmaßnahmen", "Konkrete Maßnahmen, priorisiert."),
    ("Unsicherheiten und Datenlücken", "Was die Simulation nicht beantworten kann."),
    (RECOMMENDATION_SECTION_TITLE, RECOMMENDATION_SECTION_DESCRIPTION),
)

COMPARISON_SECTIONS: tuple[SectionSpec, ...] = (
    ("Kurzfazit", "Maximal 8 Sätze: Welche Variante in der Simulation wie abschneidet."),
    ("Vergleichsdimensionen", "Nach welchen Kriterien verglichen wird."),
    ("Bewertung je Variante", "Pro Variante: Reaktionen, Stärken, Schwächen."),
    ("Unterschiede in den Reaktionsmustern", "Wo sich die Varianten in den Reaktionen unterscheiden."),
    ("Abwägung", "Trade-offs zwischen den Varianten."),
    ("Unsicherheiten und Datenlücken", "Was die Simulation nicht beantworten kann."),
    (RECOMMENDATION_SECTION_TITLE, RECOMMENDATION_SECTION_DESCRIPTION),
)

#: Bewusst OHNE Handlungsempfehlung (#1322): ein Explorationsbericht soll
#: beschreiben, was auffällt, und offene Fragen offen lassen. Ein
#: Beschlussvorschlag würde eine Entscheidungsreife behaupten, die die
#: Fragestellung gar nicht verlangt hat.
EXPLORATIVE_SECTIONS: tuple[SectionSpec, ...] = (
    ("Kurzfazit", "Maximal 8 Sätze: Was in der Simulation auffällt."),
    ("Beobachtete Reaktionsmuster", "Wiederkehrende Muster in den Agentenreaktionen."),
    ("Auffälligkeiten", "Unerwartete Beobachtungen mit Quellenbezug."),
    ("Offene Fragen", "Was die Beobachtungen aufwerfen."),
    ("Hypothesen", "Plausible, aber unbelegte Erklärungen — explizit als solche markiert."),
    ("Datenlücken", "Was die Simulation nicht beantworten kann."),
)

INTENT_SECTION_PRESETS: Dict[ReportIntent, tuple[SectionSpec, ...]] = {
    ReportIntent.OPINION: OPINION_SECTIONS,
    ReportIntent.RISK: RISK_SECTIONS,
    ReportIntent.COMPARISON: COMPARISON_SECTIONS,
    ReportIntent.EXPLORATIVE: EXPLORATIVE_SECTIONS,
    ReportIntent.FULL: FULL_SECTIONS,
}


#: Reihenfolge ist Priorität: Vergleich schlägt Risiko schlägt Meinung.
_INTENT_PATTERNS: Sequence[tuple[ReportIntent, tuple[str, ...]]] = (
    (
        ReportIntent.COMPARISON,
        (
            r"\bvergleich",
            r"\bgegenüberstell",
            r"\bversus\b",
            r"\bvs\.?\b",
            r"\bwelche\s+variante",
            r"\bbesser\s+als\b",
            r"\bunterschied\w*\s+zwischen\b",
            r"\bcompare\b",
        ),
    ),
    (
        ReportIntent.RISK,
        (
            r"\brisik",
            r"\bgefahr",
            r"\bdroh",
            r"\bwas\s+kann\s+schiefgehen",
            r"\bschwachstell",
            r"\bbedenken\s+drohen",
            r"\bworst[\s-]?case",
            r"\brisks?\b",
        ),
    ),
    (
        ReportIntent.OPINION,
        (
            r"\bwas\s+denken\b",
            r"\bwas\s+halten\b",
            r"\bwie\s+reagieren\b",
            r"\bwie\s+ist\s+die\s+stimmung",
            r"\bstimmung\b",
            r"\bmeinung",
            r"\bwahrnehmung",
            r"\bakzeptanz\b",
            r"\bsentiment\b",
            r"\bwhat\s+do\s+people\s+think\b",
        ),
    ),
    (
        ReportIntent.EXPLORATIVE,
        (
            r"\bexplorativ",
            r"\bwas\s+fällt\s+auf",
            r"\berkunde\b",
            r"\boffene\s+fragen\b",
        ),
    ),
)


def detect_report_intent(question: str) -> ReportIntent:
    """Leitet aus der Fragestellung das Report-Preset ab.

    Ohne eindeutigen Treffer bleibt es beim vollständigen Report — im Zweifel
    lieber zu viel Struktur als eine stillschweigend beschnittene Analyse.
    """
    text = (question or "").strip().lower()
    if not text:
        return ReportIntent.FULL

    for intent, patterns in _INTENT_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return intent
    return ReportIntent.FULL


def section_specs_for_intent(intent: ReportIntent) -> List[SectionSpec]:
    """(Titel, Beschreibung)-Paare für ein Intent-Preset.

    Direkt als ``required_sections`` an ``plan_outline`` übergebbar.
    """
    return list(INTENT_SECTION_PRESETS.get(intent, FULL_SECTIONS))


def sections_for_intent(intent: ReportIntent) -> List[str]:
    """Nur die Abschnittstitel eines Intent-Presets."""
    return [title for title, _description in section_specs_for_intent(intent)]


def sections_for_question(question: str) -> List[str]:
    return sections_for_intent(detect_report_intent(question))


def section_specs_for_question(question: str) -> List[SectionSpec]:
    return section_specs_for_intent(detect_report_intent(question))


__all__ = [
    "COMPARISON_SECTIONS",
    "EXPLORATIVE_SECTIONS",
    "FULL_SECTIONS",
    "INTENT_SECTION_PRESETS",
    "OPINION_SECTIONS",
    "RISK_SECTIONS",
    "ReportIntent",
    "SectionSpec",
    "detect_report_intent",
    "section_specs_for_intent",
    "section_specs_for_question",
    "sections_for_intent",
    "sections_for_question",
]
