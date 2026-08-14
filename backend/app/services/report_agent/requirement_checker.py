"""Requirement-Checker: maschinelle Vollständigkeitsprüfung vor Report-Abschluss.

Issue #1302 — bislang setzte der Reporter ``COMPLETED`` ohne jede maschinelle
Prüfung, ob inhaltlich vorgesehene Analyseaspekte tatsächlich abgedeckt sind.

## Entscheidung zur Anwendbarkeit (WICHTIG — vor Änderung lesen)

Das Issue gibt wörtlich eine 7-Punkte-Checkliste vor: Widersprüche zwischen
Stakeholdern identifiziert/adressiert, Frühwarnindikatoren benannt,
Stop-Bedingungen definiert, Expand-Bedingungen definiert, Positionswechsel
dokumentiert, Koalitionen identifiziert, "alle vier Varianten abgedeckt".
Das ist das Vokabular einer Szenario-/Konfliktanalyse mit
Handlungsschwellen ("wann eskalieren/deeskalieren wir") — ein Report-Typ,
der in Agora aktuell nicht existiert.

Verifiziert vor der Implementierung:

- ``rg -ni "Stop-Bedingung|Expand-Bedingung|Frühwarnindikator|Koalition|
  Positionswechsel" backend/app`` → 0 Treffer. Diese Begriffe kommen an
  keiner Stelle im Backend vor (auch nicht in ``report_prompts/``).
- ``ReportMode`` (``strict``/``balanced``/``explorative``,
  ``contracts/report_v3.py``) hat drei, nicht vier Ausprägungen und keinen
  Bezug zu Stop-/Expand-Bedingungen (bestätigt durch die Playwright-Smoke
  ``frontend/tests/e2e/report-modes.spec.ts``, P4.4).
- ``ReportIntent`` (``opinion``/``risk``/``comparison``/``explorative``/
  ``full``, ``report_intent.py``) hat fünf Ausprägungen. Der einzige Treffer
  für "Variante" ist die COMPARISON-Section "Bewertung je Variante" — das
  bezieht sich auf verglichene *Produkt-/Optionsvarianten*, nicht auf
  Report-Varianten, und ist nicht auf exakt vier begrenzt.

Die Checkliste passt damit auf keinen der fünf existierenden Report-Typen.
Sie hart für jeden Report zu erzwingen würde jeden bestehenden
Opinion-/Risk-/Comparison-/Explorative-/Full-Report unbegründet auf
``INCOMPLETE`` abstufen, sobald er (z. B.) keine "Stop-Bedingungen" nennt —
ein Konzept, das für diese Reports nie vorgesehen war. Das widerspräche der
Abstufungs-Leitlinie der Schwesterfunktionen in ``output_contract.py``:
downgraden nur bei einem tatsächlichen Contract-Verstoß, nie bei einer
Anforderung, die für den jeweiligen Report gar nicht gilt.

**Entscheidung:** ``RequirementChecker`` ist als generischer, konfigurierbarer
Mechanismus gebaut — die Checkliste ist ein Parameter, keine Kopplung an
einen Report-Typ (Abnahmekriterium aus #1302: "Checkliste ist konfigurierbar,
nicht hartkodiert für einen Report-Typ"). Die wörtlichen 7 Punkte aus dem
Issue stehen als :data:`ISSUE_1302_DEFAULT_CHECKLIST` zur Verfügung. In
``workflow.py`` ist die dort verdrahtete Checkliste bewusst leer (siehe
Kommentar an der Wiring-Stelle) — kein bestehender Report wird also von
Prüfpunkten betroffen, die nie für ihn gedacht waren. Sollte ein künftiger
Report-Typ/-Modus diese Konzepte einführen, kann die Checkliste an der
Wiring-Stelle gezielt für diesen Typ aktiviert werden, ohne den Checker
selbst zu ändern.
"""

from __future__ import annotations

import re
from typing import Callable, List, NamedTuple, Sequence

#: Eine Prüfregel bekommt den zusammengesetzten Report-Text und liefert
#: ``True``, wenn der Aspekt abgedeckt ist.
RequirementPredicate = Callable[[str], bool]


class RequirementCheck(NamedTuple):
    """Eine benannte, pure Prüfregel gegen den Report-Text."""

    key: str
    description: str
    predicate: RequirementPredicate


def _contains_any(content: str, needles: Sequence[str]) -> bool:
    lowered = content.lower()
    return any(needle in lowered for needle in needles)


def check_stakeholder_contradictions_addressed(content: str) -> bool:
    """Widersprüche zwischen Stakeholdern identifiziert und adressiert?"""
    return _contains_any(
        content,
        ("widerspruch", "widersprüche", "widersprüchlich", "contradiction"),
    )


def check_early_warning_indicators_named(content: str) -> bool:
    """Frühwarnindikatoren benannt?"""
    return _contains_any(
        content,
        ("frühwarnindikator", "frühwarnsignal", "warnindikator", "early warning", "frühindikator"),
    )


def check_stop_conditions_defined(content: str) -> bool:
    """Stop-Bedingungen definiert?"""
    return _contains_any(
        content,
        ("stop-bedingung", "stopbedingung", "abbruchbedingung", "stop condition"),
    )


def check_expand_conditions_defined(content: str) -> bool:
    """Expand-Bedingungen definiert?"""
    return _contains_any(
        content,
        ("expand-bedingung", "expansionsbedingung", "eskalationsbedingung", "expand condition"),
    )


def check_position_changes_documented(content: str) -> bool:
    """Positionswechsel dokumentiert?"""
    return _contains_any(
        content,
        ("positionswechsel", "meinungswechsel", "positionsänderung", "position change"),
    )


def check_coalitions_identified(content: str) -> bool:
    """Koalitionen identifiziert?"""
    return _contains_any(content, ("koalition", "allianz", "bündnis", "coalition"))


_VARIANT_RE = re.compile(r"\b(?:variante|option)\s*([1-4])\b", re.IGNORECASE)


def check_all_four_variants_covered(content: str) -> bool:
    """Alle vier Varianten abgedeckt? (Heuristik: vier unterscheidbare Nennungen.)"""
    matches = _VARIANT_RE.findall(content)
    return len(set(matches)) >= 4


#: Issue #1302, wörtlich übernommene 7-Punkte-Checkliste. Nicht standardmäßig
#: scharf geschaltet — siehe Moduldocstring. Für Report-Typen mit
#: Stop-/Expand-Logik gezielt als Checkliste an :meth:`RequirementChecker.check`
#: übergeben.
ISSUE_1302_DEFAULT_CHECKLIST: tuple[RequirementCheck, ...] = (
    RequirementCheck(
        "stakeholder_contradictions_addressed",
        "Widersprüche zwischen Stakeholdern identifiziert und adressiert",
        check_stakeholder_contradictions_addressed,
    ),
    RequirementCheck(
        "early_warning_indicators_named",
        "Frühwarnindikatoren benannt",
        check_early_warning_indicators_named,
    ),
    RequirementCheck(
        "stop_conditions_defined",
        "Stop-Bedingungen definiert",
        check_stop_conditions_defined,
    ),
    RequirementCheck(
        "expand_conditions_defined",
        "Expand-Bedingungen definiert",
        check_expand_conditions_defined,
    ),
    RequirementCheck(
        "position_changes_documented",
        "Positionswechsel dokumentiert",
        check_position_changes_documented,
    ),
    RequirementCheck(
        "coalitions_identified",
        "Koalitionen identifiziert",
        check_coalitions_identified,
    ),
    RequirementCheck(
        "all_four_variants_covered",
        "Alle vier Varianten abgedeckt",
        check_all_four_variants_covered,
    ),
)


class RequirementChecker:
    """Führt eine konfigurierbare Checkliste gegen den Report-Text aus."""

    @staticmethod
    def check(content: str, checklist: Sequence[RequirementCheck]) -> List[RequirementCheck]:
        """Liefert die Checks, deren Bedingung NICHT erfüllt ist.

        ``content`` wird nicht validiert oder auf einen Report-Typ
        eingeschränkt — das ist bewusst Aufgabe des Aufrufers (siehe
        Moduldocstring): welche Checkliste für welchen Report gilt,
        entscheidet die Wiring-Stelle, nicht dieser Checker.
        """
        text = content or ""
        return [item for item in checklist if not item.predicate(text)]


__all__ = [
    "ISSUE_1302_DEFAULT_CHECKLIST",
    "RequirementCheck",
    "RequirementChecker",
    "RequirementPredicate",
    "check_all_four_variants_covered",
    "check_coalitions_identified",
    "check_early_warning_indicators_named",
    "check_expand_conditions_defined",
    "check_position_changes_documented",
    "check_stakeholder_contradictions_addressed",
    "check_stop_conditions_defined",
]
