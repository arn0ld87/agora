"""Ermittlung und Aggregation von Qualitätsmängeln und Degradationen eines Reportlaufs."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from ...config import Config
from ...utils.logger import get_logger

logger = get_logger("agora.report_agent.run_degradation")

#: Simulationsstatus, bei denen die Simulation nicht regulär endete.
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


#: Ab diesem Anteil fehlgeschlagener LLM-Aufrufe der Simulation (Issue #1766)
#: weist der Bericht eine Warnung aus. Darunter gelten vereinzelte Ausfaelle
#: als Betriebsrauschen.
SIMULATION_LLM_FAILURE_WARNING_RATIO = 0.10

#: Ab diesem Anteil ist die Simulation faktisch ohne Modellantwort geblieben;
#: der Bericht beruht dann auf einer ausgedünnten Grundlage und stuft ab.
SIMULATION_LLM_FAILURE_BLOCKING_RATIO = 0.50


def _simulation_llm_failure_degradations(
    total: Optional[int],
    failed: Optional[int],
) -> List[Dict[str, Any]]:
    """Fehlgeschlagene LLM-Aufrufe der Simulation (Issue #1766)."""
    if total is None or failed is None or total <= 0 or failed <= 0:
        return []

    ratio = failed / total
    if ratio < SIMULATION_LLM_FAILURE_WARNING_RATIO:
        return []

    percent = f"{ratio * 100:.1f}".replace(".", ",")
    return [
        _entry(
            "simulation",
            f"{failed}_of_{total}_simulation_llm_calls_failed",
            (
                f"{failed} von {total} LLM-Aufrufen der zugrunde liegenden "
                f"Simulation sind fehlgeschlagen ({percent} %, Wiederholungs"
                "versuche eingerechnet). Die Beiträge der betroffenen "
                "Agentenschritte fehlen im Simulationsverlauf."
            ),
            severity=(
                "blocking"
                if ratio >= SIMULATION_LLM_FAILURE_BLOCKING_RATIO
                else "warning"
            ),
        )
    ]


def _persona_degradations(
    fallback_count: int,
    total: int,
) -> List[Dict[str, Any]]:
    """Personas, die nicht vom Modell kamen (Issue #1419)."""
    if fallback_count <= 0 or total <= 0:
        return []

    blocking = fallback_count >= total
    detail = (
        f"{fallback_count} von {total} Personas konnten nicht vom Modell "
        "erzeugt werden und sind regelbasierte Platzhalter. Ihre Beitraege "
        "tragen keine belastbaren Aussagen."
    )
    if blocking:
        detail = f"{detail} Keine einzige Persona dieses Laufs kam vom Modell."
    return [
        _entry(
            "persona_generation",
            f"{fallback_count}_of_{total}_personas_rule_based",
            detail,
            severity="blocking" if blocking else "warning",
        )
    ]


def _interview_degradations(
    *, requested: int, succeeded: int, disabled_reason: str = ""
) -> List[Dict[str, Any]]:
    """Angeforderte Interviews ohne Ergebnis sind eine Lücke, kein Nebenaspekt."""
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


def _outline_degradations(fallback_outline_used: bool) -> List[Dict[str, Any]]:
    """Die Gliederung stammt nicht vom Modell, sondern aus dem Ersatzschema."""
    if not fallback_outline_used:
        return []
    return [
        _entry(
            "outline_planning",
            "fallback_outline_used",
            (
                "Die Gliederung stammt nicht vom Modell, sondern aus einem "
                "festen Ersatzschema — die LLM-basierte Outline-Planung ist "
                "fehlgeschlagen."
            ),
        )
    ]


def _cancellation_degradations(missing_section_count: int) -> List[Dict[str, Any]]:
    """Abschnitte, die ein Nutzer-Abbruch nie erreichte, sind kein Nebenaspekt."""
    if missing_section_count <= 0:
        return []
    return [
        _entry(
            "run_cancellation",
            f"{missing_section_count}_sections_missing_after_cancel",
            (
                f"Der Lauf wurde durch einen Nutzer-Abbruch (Cancel) beendet, "
                f"bevor {missing_section_count} Abschnitt(e) erzeugt wurden."
            ),
            severity="blocking",
        )
    ]


ENV_POSITIONING_RATIO_MIN = "AGORA_REPORT_POSITIONING_RATIO_MIN"


def _as_ratio(value: Any) -> Optional[float]:
    """Zahl in ``0..1`` oder ``None`` (ungültig); ``bool``/NaN/Text sind ungültig."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0.0 <= number <= 1.0 else None


def resolve_positioning_ratio_min(
    read: Optional[Callable[[str], Any]] = None,
) -> float:
    """Wirksame Warnschwelle der Positionierungsquote (Standard 0.5)."""
    if read is None:
        from ..settings_layer import get_default_service

        read = get_default_service().effective_value
    raw = read(ENV_POSITIONING_RATIO_MIN)
    ratio = _as_ratio(raw)
    if ratio is None:
        if raw is not None:
            logger.warning(
                "%s=%r ist ungültig (erwartet Zahl 0..1); Standard %s wird verwendet",
                ENV_POSITIONING_RATIO_MIN,
                raw,
                Config.REPORT_POSITIONING_RATIO_MIN,
            )
        return Config.REPORT_POSITIONING_RATIO_MIN
    return ratio


_STANCE_UNAVAILABLE_DETAILS: Dict[str, str] = {
    "read_failed": (
        "Simulationskonfiguration oder Aktionsprotokoll konnten nicht gelesen werden"
    ),
    "action_log_missing": "Zu diesem Lauf liegt kein Aktionsprotokoll vor",
    "action_log_unreadable": "Das Aktionsprotokoll enthält unlesbare Zeilen",
}


def stance_analysis_unavailable(reason: str) -> Dict[str, Any]:
    """Marker für eine Haltungsanalyse, die nicht gerechnet werden konnte."""
    return {"unavailable_reason": reason}


def _stance_unavailable_degradations(reason: Any) -> List[Dict[str, Any]]:
    detail = _STANCE_UNAVAILABLE_DETAILS.get(str(reason), "Die Ursache ist unbekannt")
    return [
        _entry(
            "simulation_positioning",
            f"stance_analysis_unavailable_{reason}",
            (
                f"Die Haltungsanalyse ist ausgefallen: {detail}. Eine "
                "Positionierungsquote liegt für diesen Bericht nicht vor; das "
                "sagt nichts über den Simulationsverlauf aus."
            ),
            severity="warning",
        )
    ]


def _positioning_degradations(
    analysis: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Zu wenige Stimmen beziehen Stellung zur Streitfrage (Issue #1778)."""
    if not isinstance(analysis, Mapping):
        return []
    if analysis.get("unavailable_reason"):
        return _stance_unavailable_degradations(analysis.get("unavailable_reason"))
    if analysis.get("applicable") is not True:
        return []

    positioned = analysis.get("voices_positioned")
    total = analysis.get("voices_total")

    failed = analysis.get("classification_failed")
    if isinstance(failed, int) and not isinstance(failed, bool) and failed > 0:
        classified = analysis.get("classified_total")
        contributions = failed + (classified if isinstance(classified, int) else 0)
        return [
            _entry(
                "simulation_positioning",
                f"stance_classification_failed_{failed}_of_{contributions}",
                (
                    f"Die Haltung von {failed} von {contributions} "
                    "Simulationsbeiträgen konnte nicht bestimmt werden. Die "
                    f"Positionierungsquote ({positioned} von {total} Stimmen) ist "
                    "deshalb nur eine Untergrenze und sagt nichts über den "
                    "Simulationsverlauf aus."
                ),
                severity="warning",
            )
        ]

    ratio = analysis.get("positioning_ratio")
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool):
        return []
    import sys
    mod = sys.modules.get("app.services.report_agent.run_degradation")
    resolver = getattr(mod, "resolve_positioning_ratio_min", resolve_positioning_ratio_min)
    if ratio >= resolver():
        return []

    percent = round(ratio * 100)
    return [
        _entry(
            "simulation_positioning",
            f"positioning_ratio_{positioned}_of_{total}",
            (
                f"Nur {positioned} von {total} Stimmen ({percent} %) beziehen in "
                "der Simulation Stellung zur Streitfrage. Der Simulationsverlauf "
                "trägt deshalb wenig zum Bericht bei."
            ),
            severity="warning",
        )
    ]


def collect_run_degradations(
    *,
    simulation_snapshot: Optional[Mapping[str, Any]] = None,
    persona_fallback_count: int = 0,
    persona_total: int = 0,
    interviews_requested: int = 0,
    interviews_succeeded: int = 0,
    interview_disabled_reason: str = "",
    failed_section_indices: Iterable[int] = (),
    forced_final_section_indices: Iterable[int] = (),
    work_trace_removed_section_indices: Iterable[int] = (),
    metadata_failed_section_indices: Iterable[int] = (),
    contract_validation_errors: Sequence[Any] = (),
    fallback_outline_used: bool = False,
    cancelled_missing_section_count: int = 0,
    simulation_llm_calls_total: Optional[int] = None,
    simulation_llm_calls_failed: Optional[int] = None,
    stance_analysis: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Alle deterministisch feststellbaren Qualitätsmängel eines Laufs."""
    found: List[Dict[str, Any]] = _simulation_degradations(simulation_snapshot)
    found.extend(
        _simulation_llm_failure_degradations(
            simulation_llm_calls_total, simulation_llm_calls_failed
        )
    )
    found.extend(_positioning_degradations(stance_analysis))
    found.extend(_outline_degradations(fallback_outline_used))
    found.extend(_persona_degradations(persona_fallback_count, persona_total))
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

    found.extend(_cancellation_degradations(cancelled_missing_section_count))

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


def apply_run_degradation_downgrade(
    status: "Any",
    run_degradations: Iterable[Mapping[str, Any]],
) -> "Any":
    """Stuft ``COMPLETED`` auf ``INCOMPLETE`` ab — bei blockierenden Mängeln."""
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
    """Deterministische Red-Team-Invarianten über den fertigen Lauf."""
    violations: List[str] = []

    def reported(component: str) -> bool:
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
