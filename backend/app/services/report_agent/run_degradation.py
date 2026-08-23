"""Was der Bericht über die Qualität seiner eigenen Grundlage sagen muss.

Der Referenzlauf ``report_cc2ef45da5e9`` ging als ``completed`` hinaus. Dabei
war die Simulation ``failed``, es lagen 45 von 48 Runden vor, beide Plattformen
meldeten ``completed=false``, und von acht ``interview_agents``-Aufrufen kam
kein einziges Interview zustande. Der ``degradation_log`` blieb leer.

Nichts davon war ein Programmfehler im engeren Sinn — jede Komponente tat, was
sie sollte. Der Fehler war, dass niemand die Summe zog. ``degradation_log``
kennt nur Claim-Abstufungen, ``PipelineDegradationReport`` nur Ausfälle der
Vorverarbeitung; für den Zustand des Report*laufs* war keine Stelle zuständig.

Dieses Modul zieht die Summe. Es prüft ausschließlich deterministisch
feststellbare Sachverhalte — ein Red Team braucht es dafür nicht, und ein
LLM-Urteil wäre hier sogar schlechter: es geht um Zählwerte, nicht um
Einschätzung.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

#: Simulationsstatus, bei denen die Simulation nicht regulär endete.
#:
#: ``running`` gehört bewusst **nicht** dazu. Ein Bericht darf über eine
#: laufende Simulation entstehen; das ist ein unterstützter Ablauf und kein
#: Mangel. Der Zwischenstand wird über die Rundenzahl als Warnung ausgewiesen,
#: nicht über den Status als blockierender Ausfall — sonst wäre jeder solche
#: Bericht dauerhaft ``INCOMPLETE``.
_UNHEALTHY_SIMULATION_STATUSES = frozenset({"failed", "error", "stopped", "aborted"})


def _entry(
    component: str,
    reason: str,
    detail: str,
    *,
    severity: str = "warning",
) -> Dict[str, Any]:
    return {
        "component": component,
        "reason": reason,
        "detail": detail,
        "severity": severity,
    }


def _simulation_degradations(
    snapshot: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if not snapshot:
        return []

    found: List[Dict[str, Any]] = []
    status = str(snapshot.get("simulation_status") or "").strip().lower()
    if status in _UNHEALTHY_SIMULATION_STATUSES:
        found.append(
            _entry(
                "simulation",
                f"simulation_{status}",
                f"Die zugrunde liegende Simulation endete mit Status '{status}'.",
                severity="blocking",
            )
        )

    completed = int(snapshot.get("rounds_completed") or 0)
    total = int(snapshot.get("total_rounds") or 0)
    if total and completed < total:
        found.append(
            _entry(
                "simulation",
                f"{completed}_of_{total}_rounds",
                (
                    f"Der Bericht beruht auf {completed} von {total} geplanten "
                    "Simulationsrunden."
                ),
            )
        )
    return found


def _interview_degradations(
    *, requested: int, succeeded: int, disabled_reason: str = ""
) -> List[Dict[str, Any]]:
    """Angeforderte Interviews ohne Ergebnis sind eine Lücke, kein Nebenaspekt.

    Der Bericht sollte Stakeholder zu Wort kommen lassen. Kam keiner zu Wort,
    steht im Bericht etwas anderes als geplant — und der Leser muss das
    erfahren, bevor er "die interviewten Personas" liest.
    """
    if requested <= 0 or succeeded > 0:
        return []
    detail = (
        f"{requested} Interview-Aufruf(e), kein einziges Interview zustande gekommen."
    )
    if disabled_reason:
        detail = f"{detail} Ursache: {disabled_reason}"
    return [
        _entry(
            "interview_agents",
            "0_successful_interviews",
            detail,
            severity="blocking",
        )
    ]


def collect_run_degradations(
    *,
    simulation_snapshot: Optional[Mapping[str, Any]] = None,
    interviews_requested: int = 0,
    interviews_succeeded: int = 0,
    interview_disabled_reason: str = "",
    failed_section_indices: Iterable[int] = (),
    forced_final_section_indices: Iterable[int] = (),
    work_trace_removed_section_indices: Iterable[int] = (),
    metadata_failed_section_indices: Iterable[int] = (),
    contract_validation_errors: Sequence[Any] = (),
) -> List[Dict[str, Any]]:
    """Alle deterministisch feststellbaren Qualitätsmängel eines Laufs.

    Die Reihenfolge folgt der Schwere für den Leser: worauf der Bericht
    inhaltlich beruht, steht vor dem, was beim Erzeugen schiefging.
    """
    found: List[Dict[str, Any]] = _simulation_degradations(simulation_snapshot)
    found.extend(
        _interview_degradations(
            requested=interviews_requested,
            succeeded=interviews_succeeded,
            disabled_reason=interview_disabled_reason,
        )
    )

    failed = sorted(set(failed_section_indices))
    if failed:
        found.append(
            _entry(
                "section_generation",
                f"{len(failed)}_sections_failed",
                "Nicht erzeugte Abschnitte: " + ", ".join(str(i) for i in failed),
                severity="blocking",
            )
        )

    forced = sorted(set(forced_final_section_indices))
    if forced:
        found.append(
            _entry(
                "section_generation",
                f"{len(forced)}_sections_forced_final",
                (
                    "Abschnitte, die erst nach erzwungener Endgenerierung "
                    "entstanden: " + ", ".join(str(i) for i in forced)
                ),
            )
        )

    sanitized = sorted(set(work_trace_removed_section_indices))
    if sanitized:
        found.append(
            _entry(
                "section_generation",
                f"{len(sanitized)}_sections_sanitized",
                (
                    "Abschnitte, aus denen interne Arbeitsspur-Segmente "
                    "entfernt wurden: " + ", ".join(str(i) for i in sanitized)
                ),
            )
        )

    metadata_failed = sorted(set(metadata_failed_section_indices))
    if metadata_failed:
        found.append(
            _entry(
                "section_metadata",
                f"{len(metadata_failed)}_sections_without_metadata",
                (
                    "Abschnitte ohne strukturierte Metadaten: "
                    + ", ".join(str(i) for i in metadata_failed)
                ),
            )
        )

    errors = list(contract_validation_errors)
    if errors:
        found.append(
            _entry(
                "contract_export",
                f"{len(errors)}_contract_validation_errors",
                "ReportV3 validierte nicht vollständig.",
                severity="blocking",
            )
        )
    return found


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
    except AttributeError:  # pragma: no cover — __slots__-Objekte
        pass
    return events


def mark_forced_final(agent: Any, section_index: int) -> None:
    """Der Abschnitt entstand erst, nachdem die Iterationen erschöpft waren."""
    events_for(agent).forced_final_sections.add(int(section_index))


def mark_metadata_failure(agent: Any, section_index: int) -> None:
    """Die strukturierte Metadaten-Extraktion lieferte für den Abschnitt nichts."""
    events_for(agent).metadata_failed_sections.add(int(section_index))


def mark_work_traces_removed(agent: Any, section_index: int) -> None:
    """Aus dem Abschnittsinhalt wurden interne Arbeitsspur-Segmente entfernt.

    Der Inhalt blieb nutzbar — deshalb eine Warnung, kein Statusabstieg. Aber
    der Abschnitt ist nicht das, was das Modell geliefert hat, und der Leser
    soll das nachvollziehen können.
    """
    events_for(agent).work_trace_removed_sections.add(int(section_index))


def apply_run_degradation_downgrade(
    status: "Any",
    run_degradations: Iterable[Mapping[str, Any]],
) -> "Any":
    """Stuft ``COMPLETED`` auf ``INCOMPLETE`` ab — bei blockierenden Mängeln.

    Der Schweregrad entscheidet, und das ist keine Feinheit: ein Bericht darf
    ausdrücklich starten, während die Simulation noch läuft
    (``simulation_running``). Das erzeugt zuverlässig einen ``warning``-Eintrag
    über unvollständige Runden — würde der schon abstufen, wäre jeder Report
    aus diesem unterstützten Ablauf dauerhaft ``INCOMPLETE``, und die
    Abstufung sagte nichts mehr aus.

    Warnungen bleiben trotzdem in ``run_degradations`` sichtbar: der Bericht
    weist den Zwischenstand aus, er nennt sich nur nicht unvollständig.

    Dieselbe Linie wie :func:`apply_degradation_downgrade`: ein bereits
    abgestufter Status wird nie wieder aufgewertet.
    """
    from ...models.report import ReportStatus  # noqa: PLC0415 — zyklischer Import

    blocking = [
        entry
        for entry in run_degradations
        if str(entry.get("severity") or "warning") == "blocking"
    ]
    if not blocking:
        return status
    if status == ReportStatus.COMPLETED:
        return ReportStatus.INCOMPLETE
    return status


def assert_run_invariants(
    *,
    status: str,
    run_degradations: Sequence[Mapping[str, Any]],
    simulation_status: str = "",
    interviews_requested: int = 0,
    interviews_succeeded: int = 0,
) -> List[str]:
    """Deterministische Red-Team-Invarianten über den fertigen Lauf.

    Das LLM-Red-Team des Referenzlaufs übersah genau diese Konstellationen —
    null erfolgreiche Interviews, gescheiterte Simulation, leerer
    Degradation-Log — obwohl sie sich abzählen lassen. Prosa ist dafür das
    falsche Werkzeug.

    Gibt die Namen der verletzten Invarianten zurück; leer heißt sauber.
    """
    violations: List[str] = []

    def reported(component: str) -> bool:
        """Meldet der Lauf einen Mangel *dieser* Komponente?

        Bewusst komponentenscharf und nicht ``bool(run_degradations)``: ein
        unbezogener Eintrag — etwa fehlende Abschnitts-Metadaten — hätte sonst
        die Invariante über nicht zustande gekommene Interviews unterdrückt.
        Das Sicherheitsnetz griffe dann gerade dort nicht, wo der Lauf schon
        andere Mängel meldet.
        """
        return any(
            str(entry.get("component") or "") == component
            for entry in run_degradations
        )

    if (
        interviews_requested > 0
        and interviews_succeeded == 0
        and not reported("interview_agents")
    ):
        violations.append("interviews_requested_but_none_succeeded_and_not_degraded")

    if simulation_status.strip().lower() in _UNHEALTHY_SIMULATION_STATUSES and not reported(
        "simulation"
    ):
        violations.append("simulation_unhealthy_and_degradation_log_empty")

    if status == "completed" and any(
        str(entry.get("severity") or "warning") == "blocking"
        for entry in run_degradations
    ):
        violations.append("degraded_run_reported_as_completed")

    return violations


__all__ = [
    "RunEventLog",
    "apply_run_degradation_downgrade",
    "assert_run_invariants",
    "collect_run_degradations",
    "events_for",
    "mark_forced_final",
    "mark_metadata_failure",
    "mark_work_traces_removed",
]
