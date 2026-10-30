"""Maschinelle Vollständigkeitsprüfung vor dem Report-Abschluss (Issue #1302).

Der Reporter setzte ``completed``, ohne zu prüfen, ob die geforderten
Analyseaspekte überhaupt im Bericht stehen — der Referenzlauf dokumentiert
unter ``docs/reference-runs/2026-08-14-aurora-report`` als Regressionserwartung
Nr. 5 ausdrücklich, dass Frühwarnindikatoren und Stop-/Expand-Kriterien im
finalen Report sichtbar bleiben.

Dieses Modul zieht dieselbe Summe wie ``run_degradation`` — nur über den
*Inhalt* statt die Laufumstände. Bewusst deterministisch: es geht um das
Vorhandensein benannter Aspekte, nicht um eine Einschätzung; ein LLM-Urteil
wäre hier schlechter und teurer.

Die Checkliste ist Daten, kein Code-Pfad: pro Requirement ein ID, ein Titel
und Erkennungsmuster gegen den fertigen Berichtstext. Damit ist sie nicht an
einen Report-Typ gebunden — die vier entscheidungsorientierten Presets
(FULL/OPINION/RISK/COMPARISON, siehe #1322) teilen sich die Default-Checkliste,
der explorative Report prüft bewusst nichts: Er soll laut #1322 offene Fragen
offen lassen und keinen Entscheidungsreifegrad behaupten; ihn auf
Empfehlungsaspekte zu prüfen, machte jeden Explorativ-Report dauerhaft
INCOMPLETE.

Fehlende Aspekte werden als Degradation-Einträge geliefert — dieselbe
Dict-Form wie :func:`collect_run_degradations` — und fließen am Aufrufort in
``report.run_degradations`` ein. Die Statusabstufung übernimmt die bestehende
:func:`apply_run_degradation_downgrade`-Mechanik; dieses Modul erfindet keine
zweite Statuslogik.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from ...config import Config
from .run_degradation import _entry

if TYPE_CHECKING:  # pragma: no cover — nur für Typprüfung
    from ..report_intent import ReportIntent


#: Komponentenname der Degradation-Einträge. Ein eigener Name statt eines
#: bestehenden, damit ein fehlender Aspekt im Artefakt von einem
#: Generierungs-Mangel unterscheidbar bleibt.
COMPONENT = "requirement_checker"

#: Sprachschluessel der Musterauswahl. ``REPORT_LANGUAGE`` ist eine
#: persistierte Nutzereinstellung (``settings_schema.py``,
#: ``settings.py``) und steuert bereits die Generierung. Ein englisch
#: erzeugter Report gegen deutsche Muster zu pruefen, meldet alle Aspekte
#: gleichzeitig als fehlend und macht den Bericht dauerhaft ``incomplete`` —
#: fuer ein Feature, das Vertrauen in den Abschlussstatus schaffen soll, die
#: schlechteste Ausfallrichtung.
LANG_DE = "de"
LANG_EN = "en"

#: Unbekannte Sprachwerte fallen konservativ auf Deutsch: das ist der
#: Projekt-Default (``Config.REPORT_LANGUAGE = 'German'``) und die Sprache
#: der Referenzlaeufe.
_DEFAULT_LANG = LANG_DE


def resolve_language(raw: Optional[str] = None) -> str:
    """Sprachschluessel aus ``REPORT_LANGUAGE`` — Deutsch als Rueckfallebene.

    Bewusst tolerant gegen Schreibweisen (``English``/``english``/``en``),
    weil der Wert aus einer freien Nutzereinstellung stammt und ein Tippfehler
    keinen Report unpruefbar machen darf.
    """
    value = str(raw if raw is not None else Config.REPORT_LANGUAGE or "").strip().lower()
    if value.startswith("en"):
        return LANG_EN
    if value.startswith("de") or value.startswith("ger"):
        return LANG_DE
    return _DEFAULT_LANG


@dataclass(frozen=True)
class Requirement:
    """Ein geforderter Analyseaspekt mit Erkennungsmustern.

    ``patterns`` sind reguläre Ausdrücke (case-insensitive angewandt). Ein
    Aspekt gilt als behandelt, sobald *ein* Muster im Berichtstext trifft —
    die Checkliste stellt Vollständigkeit fest, keine Formulierungstreue.

    ``patterns`` sind die Muster der Berichtssprache Deutsch;
    ``patterns_en`` die englischen Entsprechungen. Die Auswahl **ersetzt**
    die Musterliste, sie ergaenzt sie nicht: sonst wuerde ein deutscher
    Bericht durch englische Treffer als vollstaendig gelten und die
    Checkliste verlaere ihre Aussage.
    """

    id: str
    title: str
    description: str
    patterns: tuple[str, ...]
    patterns_en: tuple[str, ...] = ()

    def patterns_for(self, language: str) -> tuple[str, ...]:
        """Muster der gewaehlten Sprache; ohne englische Muster bleibt Deutsch."""
        if language == LANG_EN and self.patterns_en:
            return self.patterns_en
        return self.patterns

    def satisfied_by(self, text: str, language: Optional[str] = None) -> bool:
        lowered = text or ""
        active = language or resolve_language()
        return any(
            re.search(pattern, lowered, re.IGNORECASE)
            for pattern in self.patterns_for(active)
        )


#: Default-Checkliste für entscheidungsorientierte Reports (#1302).
#:
#: Die ersten vier Posten stehen wörtlich in der Beschreibung der Pflicht-
#: Section „Handlungsempfehlung" (``report_prompts/planning.py::
#: RECOMMENDATION_SECTION_DESCRIPTION``): Positionswechsel, Frühwarn-
#: indikatoren, zustimmende/widerständige Akteure samt Konfliktlinien.
#: Stop-/Expand-Bedingungen kommen aus der Regressionserwartung des
#: Aurora-Referenzlaufs („Stop-/Expand-Kriterien bleiben sichtbar").
DEFAULT_REQUIREMENT_CHECKLIST: tuple[Requirement, ...] = (
    Requirement(
        id="stakeholder_widersprueche",
        title="Widersprüche zwischen Stakeholdern",
        description=(
            "Dem Bericht ist zu entnehmen, wo Stakeholder auseinanderliegen "
            "und wie dem begegnet wird."
        ),
        patterns=(
            r"widerspr[üu]ch",
            r"konfliktlinien?",
            r"kontroversen?",
            r"uneinig",
        ),
        patterns_en=(
            r"contradict",
            r"conflict(ing|\s+lines?)",
            r"controvers",
            r"disagree",
        ),
    ),
    Requirement(
        id="fruehwarnindikatoren",
        title="Frühwarnindikatoren benannt",
        description="Der Bericht nennt Signale, die früh auf Kursabweichungen hinweisen.",
        patterns=(
            r"fr[üu]hwarn",
            r"fr[üu]hindikator",
            r"warnsignale?\b",
        ),
        patterns_en=(
            r"early[- ]warning",
            r"leading indicator",
            r"warning signals?\b",
        ),
    ),
    Requirement(
        id="stop_bedingungen",
        title="Stop-Bedingungen definiert",
        description=(
            "Der Bericht legt fest, wann abgebrochen oder nicht weiter "
            "ausgeweitet wird."
        ),
        patterns=(
            # Codex-P1 auf PR #1387: Die frueheren Muster akzeptierten nur den
            # Singular direkt hinter dem Praefix. Damit fiel ausgerechnet
            # "Stop-/Expand-Kriterien" durch — die Schreibweise, die der
            # Modul-Docstring oben als Regressionserwartung Nr. 5 zitiert.
            # ``[-/ ]*`` deckt die Schraegstrich-Kombiform ab, in der
            # "Expand-" zwischen Praefix und Nomen steht.
            r"stopp?[-/ ]*(?:expand[-/ ]*)?(bedingung|kriteri)",
            r"abbruch(?:s)?[-/ ]*(bedingung|kriteri)",
            r"nicht ausgeweitet wird",
        ),
        patterns_en=(
            r"stop[- ]*(?:/[- ]*expand[- ]*)?criteri",
            r"stop conditions?\b",
            r"abort criteri",
            r"when to abort",
        ),
    ),
    Requirement(
        id="expand_bedingungen",
        title="Expand-Bedingungen definiert",
        description="Der Bericht legt fest, unter welcher Voraussetzung ausgeweitet wird.",
        patterns=(
            r"expand(ier|ations?|[-/ ])",
            r"expansions?[-/ ]*(bedingung|kriteri)",
            r"ausweitungs?[-/ ]*(bedingung|kriteri)",
            r"vor einer ausweitung",
            r"nach erfolgreichem pilot",
        ),
        patterns_en=(
            r"expand[- ]*criteri",
            r"expansion (criteri|conditions?)",
            r"scale[- ]up (criteri|conditions?)",
            r"when to (expand|scale up)",
        ),
    ),
    Requirement(
        id="positionswechsel",
        title="Positionswechsel dokumentiert",
        description=(
            "Mögliche oder beobachtete Positionswechsel von Akteuren sind "
            "benannt."
        ),
        patterns=(
            r"positionswechsel",
            r"positionsänderung",
            r"position(en)?\s+(ge)?ändert",
            r"kein(e(n)?)?\s+positionswechsel\s+beobachtet",
        ),
        patterns_en=(
            r"position shift",
            r"change[ds]? (its|their|his|her) position",
            r"shifted position",
            r"no position shift (was )?observed",
        ),
    ),
    Requirement(
        id="koalitionen",
        title="Koalitionen identifiziert",
        description="Akteursbündnisse und gemeinsame Fronten sind erkennbar.",
        patterns=(
            r"koalition(en)?\b",
            r"b[üu]ndnis(s(es)?|se)?\b",
            r"allianzen?\b",
            r"keine?\s+koalition(en)?\s+gebildet",
        ),
        patterns_en=(
            r"coalitions?\b",
            r"alliances?\b",
            r"blocs?\b",
            r"no coalition(s)? (was |were )?formed",
        ),
    ),
)

#: Signalwörter in der Fragestellung, die Stop-/Expand-Bedingungen verlangen.
_EXPAND_STOP_TRIGGERS: tuple[str, ...] = (
    "pilot",
    "stufenweise",
    "schrittweise",
    "einführung",
    "einfuehrung",
    "rollout",
    "ausweit",
    "skalier",
    "testphase",
    "phased",
    "roll-out",
    "scale up",
)


def checklist_for_intent(
    intent: "Optional[ReportIntent]",
    has_contested_question: Optional[bool] = None,
    simulation_requirement: Optional[str] = None,
) -> tuple[Requirement, ...]:
    """Checkliste für einen Report-Intent — „alle vier Varianten abgedeckt".

    Die vier entscheidungsorientierten Presets (FULL/OPINION/RISK/COMPARISON)
    tragen laut #1322 dieselbe Handlungsempfehlung. Der explorative Report prüft
    nichts (siehe Modul-Docstring).

    Pflichtaspekte nach Issue #1778 (Etappe 3), sofern Kontext übergeben wird:
    - stakeholder_widersprueche und fruehwarnindikatoren: immer.
    - stop_bedingungen und expand_bedingungen: nur wenn simulation_requirement
      stufenweise Einführung, Pilotierung oder Skalierung andeutet (oder None).
    - positionswechsel und koalitionen: nur wenn eine Streitfrage vorliegt
      (has_contested_question=True oder None).
    """
    from ..report_intent import ReportIntent  # noqa: PLC0415 — zyklischer Import

    if intent == ReportIntent.EXPLORATIVE:
        return ()

    if has_contested_question is None and simulation_requirement is None:
        return DEFAULT_REQUIREMENT_CHECKLIST

    by_id = {req.id: req for req in DEFAULT_REQUIREMENT_CHECKLIST}
    selected: list[Requirement] = []

    if "stakeholder_widersprueche" in by_id:
        selected.append(by_id["stakeholder_widersprueche"])
    if "fruehwarnindikatoren" in by_id:
        selected.append(by_id["fruehwarnindikatoren"])

    req_lower = (simulation_requirement or "").lower()
    if simulation_requirement is None or any(
        trigger in req_lower for trigger in _EXPAND_STOP_TRIGGERS
    ):
        if "stop_bedingungen" in by_id:
            selected.append(by_id["stop_bedingungen"])
        if "expand_bedingungen" in by_id:
            selected.append(by_id["expand_bedingungen"])

    if has_contested_question is None or has_contested_question:
        if "positionswechsel" in by_id:
            selected.append(by_id["positionswechsel"])
        if "koalitionen" in by_id:
            selected.append(by_id["koalitionen"])

    return tuple(selected)


def find_missing_requirements(
    texts: Sequence[Optional[str]],
    checklist: Sequence[Requirement] = DEFAULT_REQUIREMENT_CHECKLIST,
    language: Optional[str] = None,
) -> List[Requirement]:
    """Alle Requirements, die in keinem der Texte erfüllt sind.

    Die Texte werden vor der Prüfung vereinigt — ein Aspekt gilt als
    behandelt, egal in welchem Abschnitt er steht.

    ``language`` ueberschreibt die Berichtssprache; ohne Angabe entscheidet
    ``Config.REPORT_LANGUAGE``. Die Sprache wird einmal aufgeloest und an
    alle Requirements durchgereicht, damit eine Konfigurationsaenderung
    waehrend der Pruefung nicht zu einer halb deutschen, halb englischen
    Bewertung fuehrt.
    """
    combined = "\n".join(text for text in texts if text)
    active = resolve_language(language)
    return [req for req in checklist if not req.satisfied_by(combined, active)]


def collect_requirement_degradations(
    missing: Sequence[Requirement],
) -> List[Dict[str, Any]]:
    """Fehlende Aspekte als Degradation-Einträge (Form wie #1277).

    Pro fehlendem Requirement ein eigener Eintrag mit ``severity=blocking``,
    damit :func:`apply_run_degradation_downgrade` den Status abstuft und die
    Fehlerliste im persistierten Artefakt einzeln lesbar bleibt.
    """
    return [
        _entry(
            COMPONENT,
            f"{req.id}_missing",
            f"{req.title}: {req.description}",
            severity="blocking",
        )
        for req in missing
    ]


__all__ = [
    "COMPONENT",
    "DEFAULT_REQUIREMENT_CHECKLIST",
    "LANG_DE",
    "LANG_EN",
    "Requirement",
    "checklist_for_intent",
    "collect_requirement_degradations",
    "find_missing_requirements",
    "resolve_language",
]
