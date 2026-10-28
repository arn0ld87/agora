"""Event-Logging und Marker für den Verlauf der Berichtserzeugung."""

from __future__ import annotations

from typing import Any, Optional


class RunEventLog:
    """Was während des Laufs auffiel, aber erst am Ende zählbar wird.

    Alle drei Ereignisse hier waren im Referenzlauf ``report_cc2ef45da5e9``
    vorhanden und nur geloggt: mehrere Abschnitte entstanden erst nach
    erzwungener Endgenerierung, bei anderen scheiterte die Metadaten-
    Extraktion, und aus wieder anderen waren Arbeitsspur-Segmente still
    herausgeschnitten worden. Eine Logzeile erreicht den Bericht nicht — der
    Leser sah einen Abschnitt, dem er nicht ansehen konnte, dass er unter
    Abbruchbedingungen entstanden ist.

    Bewusst nur Mengen und keine Ereignisliste: gefragt ist am Ende
    "welche Abschnitte", nicht "was ist wann passiert". Letzteres steht im Log.
    """

    def __init__(self) -> None:
        self.forced_final_sections: set[int] = set()
        self.work_trace_removed_sections: set[int] = set()
        self.metadata_failed_sections: set[int] = set()
        self.fallback_outline_used: bool = False
        # (Fehlerklasse, gekürzte Providermeldung) des ersten nicht-transienten
        # Provider-400 (#1738). Gesetzt → die restlichen Abschnitte setzen
        # keinen LLM-Call mehr ab, sondern enden als sichtbarer Fallback.
        self.persistent_provider_error: Optional[tuple[str, str]] = None


def events_for(agent: Any) -> RunEventLog:
    """Das Ereignisregister dieses Laufs, bei Bedarf angelegt.

    Freie Funktion aus demselben Grund wie bei Ledger und Breaker: mehrere
    Aufrufer reichen ein fremdes Objekt als ``self`` in die Agent-Funktionen.
    """
    events = getattr(agent, "_run_event_log", None)
    if isinstance(events, RunEventLog):
        return events
    events = RunEventLog()
    try:
        agent._run_event_log = events
    except AttributeError:
        pass
    return events


def mark_forced_final(agent: Any, section_index: int) -> None:
    """Der Abschnitt entstand erst, nachdem die Iterationen erschöpft waren."""
    events_for(agent).forced_final_sections.add(int(section_index))


def mark_metadata_failure(agent: Any, section_index: int) -> None:
    """Die strukturierte Metadaten-Extraktion lieferte für den Abschnitt nichts."""
    events_for(agent).metadata_failed_sections.add(int(section_index))


def mark_fallback_outline_used(agent: Any) -> None:
    """Die Outline-Planung scheiterte; ``plan_outline`` griff auf das feste
    Ersatzschema zurueck (Issue #1479)."""
    events_for(agent).fallback_outline_used = True


def clear_fallback_outline_used(agent: Any) -> None:
    """Den geerbten Fallback-Marker vor einem neuen Planungsversuch loeschen.

    Issue #1479 (Codex-Review Runde 6): ``_restore_work_trace_markers`` setzt
    das Flag beim Resume aus dem persistierten Zustand des VORIGEN Laufs.
    Gelingt der neue ``plan_outline``-Versuch, stammt der ausgelieferte
    Outline aber nicht mehr aus dem Fallback — ohne dieses Zuruecksetzen
    schriebe ``_persist_fallback_outline_marker`` den geerbten Wert
    unveraendert zurueck, der Report truege eine falsche
    ``outline_planning/fallback_outline_used``-Warnung, und der naechste
    Cancel/Resume verwuerfe den gueltigen Outline erneut.
    """
    events_for(agent).fallback_outline_used = False


def mark_work_traces_removed(agent: Any, section_index: int) -> None:
    """Aus dem Abschnittsinhalt wurden interne Arbeitsspur-Segmente entfernt.

    Der Inhalt blieb nutzbar — deshalb eine Warnung, kein Statusabstieg. Aber
    der Abschnitt ist nicht das, was das Modell geliefert hat, und der Leser
    soll das nachvollziehen können.
    """
    events_for(agent).work_trace_removed_sections.add(int(section_index))
