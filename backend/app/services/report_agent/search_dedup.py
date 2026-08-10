"""Ergebnislose Suchen werden nicht wiederholt (Issue #1191).

Im Lauf ``report_b76cf7078229`` verbrauchte der Abschnitt „Unsicherheiten und
Datenlücken" fünf statt vier Tool-Calls und lief in den Iterationsanschlag.
Drei dieser Calls waren ergebnislose Suchen nach **derselben** Stakeholdergruppe
— einmal ``panorama_search``, zweimal ``quick_search``. Die Gruppe war nie
interviewt worden und konnte im Datenbestand gar nicht vorkommen. Der Agent
verbrannte sein Iterationsbudget mit der Wiederholung einer Suche, die nicht
fündig werden konnte — ausgerechnet in dem Abschnitt, der Datenlücken benennen
soll.

Ein Leertreffer ist ein Befund, kein Grund zur Wiederholung.

Drei bewusste Festlegungen:

* **Gleichheit über die normalisierte Query, tool-übergreifend.** Kleinschreibung,
  zusammengefasster Whitespace, Satzzeichen entfernt. Eine erfolglose
  ``panorama_search`` nach X macht damit auch eine spätere ``quick_search``
  nach X zur Wiederholung — genau der belegte Fall. Keine semantische
  Ähnlichkeit: die Regel bleibt deterministisch und testbar.
* **Ein unterdrückter Versuch zählt nicht gegen das Tool-Budget.** Sonst spart
  die Änderung keine Iteration ein und der Zweck entfällt.
* **Die Notiz bleibt eine Kontextmitteilung an das Modell.** Sie wird kein
  ``data_gap``-Eintrag im Evidenzmodell; das berührte die Evidence-Verträge und
  ist bewusst nicht Teil dieses Schnitts.

Die Merkliste gilt **pro Abschnitt**. Ein anderer Abschnitt darf dieselbe Suche
erneut versuchen: sein Kontext ist ein anderer, und die Suche ist billig genug,
um sie nicht abschnittsübergreifend zu verbieten.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Set

#: Werkzeuge, deren Leertreffer gemerkt werden. ``interview_agents`` fehlt
#: bewusst: ein Interview ohne Ergebnis ist kein Suchtreffer-Problem, sondern
#: ein Persona-Pool-Problem — und ein zweiter Versuch mit anderem Zuschnitt
#: kann dort sehr wohl etwas liefern.
SEARCH_TOOLS = frozenset({"insight_forge", "panorama_search", "quick_search"})

_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+", re.UNICODE)


def normalize_query(query: str) -> str:
    """Kanonische Form einer Suchanfrage.

    Kleinschreibung, Satzzeichen entfernt, Whitespace zusammengefasst. Damit
    gelten „aufnehmende Betriebe", „Aufnehmende Betriebe!" und
    „aufnehmende   betriebe" als dieselbe Suche.
    """
    if not query:
        return ""
    lowered = str(query).casefold()
    without_punctuation = _PUNCTUATION_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", without_punctuation).strip()


def query_of(parameters: Dict[str, Any]) -> str:
    """Die Suchanfrage aus den Tool-Parametern.

    Alle drei Suchwerkzeuge nutzen ``query``; ``interview_topic`` wird
    mitgelesen, damit ein umbenannter Parameter nicht still zu einer leeren
    Query und damit zu wirkungslosem Dedup führt.
    """
    raw = parameters.get("query") or parameters.get("interview_topic") or ""
    return str(raw)


def is_search_tool(tool_name: str) -> bool:
    return tool_name in SEARCH_TOOLS


def is_empty_result(structured_result: Any) -> bool:
    """Ob ein Suchergebnis keinerlei Treffer enthält.

    Wertet die Zählfelder der Result-DTOs aus (``SearchResult.total_count``,
    ``PanoramaResult.total_facts``/``total_entities``/``total_relationships``)
    statt den gerenderten Text zu parsen — der Text ist für das Modell
    formatiert, nicht als Schnittstelle gedacht.

    Ein unbekanntes Ergebnisobjekt gilt als **nicht** leer. Im Zweifel lieber
    eine Suche zu viel zulassen als eine mögliche Fundstelle unterdrücken.
    """
    if structured_result is None:
        return False

    count_fields = (
        "total_count",
        "total_facts",
        "total_entities",
        "total_relationships",
    )
    seen_any = False
    for field_name in count_fields:
        value = getattr(structured_result, field_name, None)
        if value is None:
            continue
        seen_any = True
        try:
            if int(value) > 0:
                return False
        except (TypeError, ValueError):
            return False

    return seen_any


class EmptySearchRegistry:
    """Merkt sich pro Abschnitt, welche Suchen bereits leer ausgingen."""

    def __init__(self) -> None:
        self._empty: Set[str] = set()

    def reset(self) -> None:
        """Zu Beginn jedes Abschnitts aufzurufen."""
        self._empty.clear()

    def record_empty(self, query: str) -> None:
        normalized = normalize_query(query)
        if normalized:
            self._empty.add(normalized)

    def was_empty(self, query: str) -> bool:
        normalized = normalize_query(query)
        return bool(normalized) and normalized in self._empty

    def __len__(self) -> int:
        return len(self._empty)


def registry_for(owner: Any) -> EmptySearchRegistry:
    """Die Merkliste eines Agenten, bei Bedarf angelegt.

    Bewusst ``getattr``-basiert statt ueber ``__init__``: ``_record_tool_evidence``
    und ``_save_evidence_section`` werden im Bestand auch ungebunden mit
    Test-Doubles aufgerufen, und zahlreiche Tests bauen den Agent ueber
    ``ReportAgent.__new__``. In beiden Faellen darf die Merkliste nicht fehlen.
    """
    registry = getattr(owner, "_empty_searches", None)
    if not isinstance(registry, EmptySearchRegistry):
        registry = EmptySearchRegistry()
        owner._empty_searches = registry
    return registry


#: Hinweis an das Modell, wenn eine bereits erfolglose Suche erneut kommt.
#: Benennt den Leertreffer als Befund und lenkt auf den Abschnittsinhalt —
#: eine blosse Ablehnung würde das Modell zum nächsten Werkzeug greifen lassen.
REPEATED_EMPTY_SEARCH_MSG = (
    "Observation: Die Suche nach \"{query}\" wurde nicht erneut ausgeführt — "
    "sie war in diesem Abschnitt bereits ergebnislos, unabhängig vom "
    "verwendeten Werkzeug. Der Gegenstand kommt im Datenbestand dieser "
    "Simulation nicht vor. Das ist ein verwertbarer Befund: behandle ihn als "
    "Datenlücke und benenne sie im Abschnittsinhalt, statt weiter danach zu "
    "suchen. Dieser Versuch zählt nicht gegen dein Tool-Budget "
    "({tool_calls_count}/{max_tool_calls})."
)


__all__ = [
    "SEARCH_TOOLS",
    "EmptySearchRegistry",
    "REPEATED_EMPTY_SEARCH_MSG",
    "is_empty_result",
    "is_search_tool",
    "normalize_query",
    "query_of",
    "registry_for",
]
