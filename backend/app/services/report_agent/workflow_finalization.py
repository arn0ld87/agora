from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from pydantic import ValidationError

from ...contracts.report_v3 import (
    RED_TEAM_FINDINGS_LIMIT,
    ModelAttribution,
    ReportV3,
)
from ...llm.tokens import PROMPT_HEADROOM_TOKENS
from ...models.report import Report, ReportStatus
from ...utils.logger import get_logger
from ..report_intent import ReportIntent, detect_report_intent
from .output_contract import (
    apply_degradation_downgrade,
    apply_quote_validation_downgrade,
    apply_report_v3_validation_downgrade,
    resolve_report_status,
)
from .requirement_checker import (
    checklist_for_intent,
    collect_requirement_degradations,
    find_missing_requirements,
)
from .run_degradation import (
    apply_run_degradation_downgrade,
    assert_run_invariants,
    collect_run_degradations,
    events_for,
    mark_fallback_outline_used,
    mark_forced_final,
    mark_metadata_failure,
    mark_work_traces_removed,
)
from .schemas import _section_schema_for
from .threshold_deviation import prior_threshold_lines, threshold_conflict_findings
from . import workflow as _wf

logger = get_logger("agora.report_agent")

_INTERVIEW_EVIDENCE_TYPE = "agent_interview"


def _count_interview_evidence(agent: Any) -> int:
    """Wie viele Interviews tatsächlich Evidence hinterlassen haben."""
    index = (getattr(agent, "evidence_map", None) or {}).get("evidence_index") or {}
    return sum(
        1
        for record in index.values()
        if isinstance(record, dict)
        and record.get("type") == _INTERVIEW_EVIDENCE_TYPE
    )


def _persist_evidence_density(agent: Any, report_id: str) -> None:
    """Schreibt ``evidence_density.json`` zur fertigen Evidence-Map (Issue #1779)."""
    evidence_map = getattr(agent, "evidence_map", None)
    if not isinstance(evidence_map, dict):
        return
    try:
        density = _wf.compute_evidence_density(evidence_map)
    except Exception as exc:  # noqa: BLE001 — logged; the report must not fail on a metric
        _wf.reraise_if_budget_exceeded(exc)
        _wf.logger.warning(
            "report %s: Belegdichte konnte nicht gezählt werden, evidence_density.json fehlt: %r",
            report_id,
            exc,
        )
        return
    _wf.ReportManager.save_evidence_density(report_id, density)
    _wf.logger.info(
        "report %s: Belegdichte claims=%d single_support=%s action_support=%s "
        "single_source_cap=%s multi_independent=%s",
        report_id,
        density.claims_total,
        density.single_support_ratio,
        density.action_support_ratio,
        density.single_source_cap_ratio,
        density.multi_independent_ratio,
    )


def _get_echo_index(agent: Any) -> float:
    """Liest den aktuellen echo_chamber_index aus den Simulations-Metriken."""
    try:
        from ..network_analytics import NetworkAnalyticsService
        from ..simulation_runner import SimulationRunner

        actions = SimulationRunner.get_all_actions(agent.simulation_id)
        action_dicts = [a.to_dict() for a in actions]
        if not action_dicts:
            return 0.0
        metrics = NetworkAnalyticsService().compute_metrics(
            action_dicts,
            simulation_id=agent.simulation_id,
        ).to_dict()
        return float(metrics.get("echo_chamber_index") or 0.0)
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning("_get_echo_index: %r", exc)
        return 0.0


_RED_TEAM_ECHO_THRESHOLD = 0.6

_RED_TEAM_MANDATORY_INTENTS = frozenset(
    {ReportIntent.RISK, ReportIntent.COMPARISON, ReportIntent.FULL}
)


def _red_team_required(intent: ReportIntent, echo_index: float) -> bool:
    """Entscheidet, ob die Red-Team-Stage einen LLM-Call machen darf."""
    if intent in _RED_TEAM_MANDATORY_INTENTS:
        return True
    return echo_index > _RED_TEAM_ECHO_THRESHOLD


_RED_TEAM_SYSTEM_PROMPT = (
    "Du bist ein kritischer Qualitätsprüfer für Szenarienanalysen. "
    "Du prüfst einen Berichtsentwurf auf Schwachstellen im Wording-Glossar v1 "
    "(VERBOTEN: 'Vorhersage', 'Prognose', 'wird eintreten'; ERLAUBT: Simulation, "
    "Szenarienanalyse, Reaktionsmuster, Einschätzung). "
    "Antworte ausschliesslich auf Deutsch."
)

_RED_TEAM_USER_TEMPLATE = (
    "Berichtsentwurf:\n\n{report_excerpt}\n\n"
    "Die Kennung vor jedem Eintrag nennt den Abschnitt: C3_02 ist der zweite "
    "Claim aus Abschnitt 3, T7_01 der erste Schwellenwert aus Abschnitt 7. "
    "Widersprüche zwischen weit auseinanderliegenden "
    "Abschnitten sind besonders zu prüfen — dort fallen sie beim Lesen am "
    "wenigsten auf.\n\n"
    "Identifiziere:\n"
    "(a) Widersprüche zwischen den Claims\n"
    "(b) Widersprüchliche operative Zahlen (zwei Schwellen für dieselbe Größe "
    "mit unterschiedlichen Werten, ohne vermerkte begründete Abweichung)\n"
    "(c) Verfrühten Konsens (Claims, die ohne ausreichende Cross-Segment-Reaktionen "
    "als hoch-konfident markiert sind)\n"
    "(d) Fehlende Cross-Segment-Reaktionen\n\n"
    "Liefere maximal 10 Befunde als JSON-Objekt mit Feld 'findings' (Liste von Strings). "
    "Kein Markdown, reines JSON."
)

_RED_TEAM_MAX_TOKENS = 1_500
_RED_TEAM_EXCERPT_BUDGET = PROMPT_HEADROOM_TOKENS * 3 - 4_000


def _build_red_team_excerpt(report_v3: ReportV3) -> str:
    """Baut den Berichtsentwurf für die Red-Team-Review (Issue #1359 B)."""
    lines: List[str] = []
    for threshold in report_v3.thresholds or []:
        deviation = (
            f"; weicht begründet ab von [{threshold.deviates_from}]: "
            f"{threshold.deviation_rationale}"
            if threshold.deviates_from
            else ""
        )
        lines.append(
            f"- [{threshold.id}] [schwelle: {threshold.purpose}] {threshold.label}: "
            f"{threshold.display_value} "
            f"(Herkunft: {threshold.origin}, Beleglage: {threshold.evidence_status}"
            f"{deviation})"
        )
    for claim in report_v3.claims or []:
        lines.append(f"- [{claim.id}] [{claim.confidence}] {claim.statement}")
    for hypothesis in report_v3.hypotheses or []:
        lines.append(f"- [{hypothesis.id}] [hypothese] {hypothesis.hypothesis_text}")

    if not lines:
        return "(kein Inhalt)"

    kept: List[str] = []
    used = 0
    for index, line in enumerate(lines):
        if used + len(line) + 1 > _RED_TEAM_EXCERPT_BUDGET and kept:
            kept.append(
                f"[gekürzt: {len(lines) - index} weitere Einträge ausgelassen — "
                "der Bericht ist vollständig, dieser Auszug nicht]"
            )
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept)


def _merge_findings(first: Sequence[str], second: Sequence[str]) -> List[str]:
    """Führt zwei Befundlisten ohne Dubletten zusammen und hält das Limit ein."""
    merged = list(dict.fromkeys([*first, *second]))
    return merged[:RED_TEAM_FINDINGS_LIMIT]


_INVARIANT_FINDINGS = {
    "interviews_requested_but_none_succeeded_and_not_degraded": (
        "Interviews waren Teil des Plans, es kam keines zustande — der Bericht "
        "weist das nicht als Einschränkung aus."
    ),
    "simulation_unhealthy_and_degradation_log_empty": (
        "Die Simulation endete nicht regulär, der Bericht führt dazu keine "
        "Einschränkung."
    ),
    "degraded_run_reported_as_completed": (
        "Der Lauf trägt Qualitätsmängel und gilt trotzdem als vollständig."
    ),
}


def _deterministic_red_team_findings(agent: Any, report: Any) -> List[str]:
    """Abzählbare Befunde über den Lauf — ohne LLM."""
    snapshot = getattr(report, "simulation_snapshot", None) or {}
    violations = assert_run_invariants(
        status=str(getattr(getattr(report, "status", None), "value", "")),
        run_degradations=list(getattr(report, "run_degradations", []) or []),
        simulation_status=str(snapshot.get("simulation_status") or ""),
        interviews_requested=_wf.breaker_for(agent).request_count("interview_agents"),
        interviews_succeeded=_wf._count_interview_evidence(agent),
    )
    return [
        _INVARIANT_FINDINGS.get(violation, violation) for violation in violations
    ]


def _run_red_team_review(
    agent: Any,
    report_v3: ReportV3,
    echo_index: float,
    *,
    intent: ReportIntent,
    deterministic_findings: Sequence[str] = (),
) -> ReportV3:
    """Führt die Red-Team-Review-Stage aus und schreibt Findings in report_v3."""
    deterministic_findings = [
        *deterministic_findings,
        *threshold_conflict_findings(report_v3.thresholds),
    ]
    if not _red_team_required(intent, echo_index):
        logger.info(
            "_run_red_team_review: intent=%s, echo_index=%.3f <= %.1f — kein LLM-Call "
            "(balanced Personas, kein entscheidungstragender Report)",
            intent.value,
            echo_index,
            _RED_TEAM_ECHO_THRESHOLD,
        )
        if deterministic_findings:
            return report_v3.model_copy(
                update={
                    "red_team_findings": _merge_findings(
                        deterministic_findings, report_v3.red_team_findings
                    )
                }
            )
        return report_v3

    user_msg = _RED_TEAM_USER_TEMPLATE.format(
        report_excerpt=_build_red_team_excerpt(report_v3)
    )

    started_at = datetime.now(timezone.utc)
    try:
        raw = agent.llm.chat_json(
            messages=[
                {"role": "system", "content": _RED_TEAM_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            context="report",
            max_tokens=_RED_TEAM_MAX_TOKENS,
        )
        findings_raw = raw.get("findings") if isinstance(raw, dict) else None
        if isinstance(findings_raw, list):
            findings = [str(f) for f in findings_raw if str(f).strip()][:10]
        else:
            findings = []
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.warning("_run_red_team_review: LLM-Call fehlgeschlagen: %r", exc)
        findings = []

    latency_ms = (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
    provider = getattr(getattr(agent, "llm", None), "provider", "unknown") or "unknown"
    model_id = getattr(getattr(agent, "llm", None), "model", "unknown") or "unknown"

    attribution = ModelAttribution(
        stage="red_team",
        provider=str(provider),
        model_id=str(model_id),
        latency_ms=round(latency_ms, 1),
        started_at=started_at,
    )
    updated_attribution = list(report_v3.model_attribution) + [attribution]

    report_v3 = report_v3.model_copy(
        update={
            "red_team_findings": _merge_findings(deterministic_findings, findings),
            "model_attribution": updated_attribution,
        }
    )
    logger.info(
        "_run_red_team_review: %d Befunde, intent=%s, echo_index=%.3f",
        len(findings),
        intent.value,
        echo_index,
    )
    return report_v3


METADATA_MAX_CONTENT_CHARS = 24000
METADATA_MAX_OUTPUT_TOKENS = 32768


def _record_metadata_truncation_degradation(
    agent: Any,
    *,
    section_index: int,
    schema_name: str,
    exc: Exception,
) -> None:
    """Haengt einen Truncation-Eintrag an ``agent.evidence_map['degradation_log']``."""
    evidence_map = getattr(agent, "evidence_map", None)
    if not isinstance(evidence_map, dict):
        logger.warning(
            "generate_section_metadata: section=%d LLMOutputTruncatedError, aber "
            "agent.evidence_map ist kein dict (%r) — degradation_log-Eintrag "
            "übersprungen.",
            section_index,
            type(evidence_map),
        )
        return
    entry = {
        "section_index": section_index,
        "claim_id": "",
        "violation": "metadata_extraction_truncated",
        "action": "dropped",
        "detail": (
            f"generate_section_metadata: LLM-Output für schema={schema_name} "
            f"wurde am Token-Limit abgeschnitten ({exc}) — strukturierte "
            f"Metadaten für Section {section_index} fehlen, Report-Status "
            "kann dadurch auf 'incomplete' abgestuft werden."
        ),
    }
    evidence_map["degradation_log"] = (
        list(evidence_map.get("degradation_log") or []) + [entry]
    )


def _prior_thresholds_prompt(
    agent: Any, schema_cls: type, section_index: int
) -> str:
    """Issue #1359: Zahlen früherer Abschnitte, auf die ein Wert verweisen kann."""
    if "thresholds" not in getattr(schema_cls, "model_fields", {}):
        return ""
    evidence_map = getattr(agent, "evidence_map", None)
    sections = evidence_map.get("sections") if isinstance(evidence_map, dict) else None
    lines = prior_threshold_lines(sections, section_index)
    if not lines:
        return ""
    return (
        "\n\n## Bereits erfasste operative Zahlen früherer Abschnitte\n"
        + "\n".join(lines)
        + "\n\nNur als Bezug für deviates_from: nicht in die eigene Liste "
        "übernehmen. Nennt dieser Abschnitt für dieselbe Größe einen anderen "
        "Wert und begründet ihn, setze deviates_from auf die Kennung in "
        "eckigen Klammern und übernimm die Begründung in deviation_rationale."
    )


def generate_section_metadata(
    agent: Any,
    section_title: str,
    section_content: str,
    section_index: int,
    section_kind: str | None = None,
) -> Dict[str, Any]:
    """Extrahiert strukturierte Metadaten aus einem fertig generierten Abschnitt."""
    schema_cls = _section_schema_for(section_title, section_kind)
    schema_name = f"section_metadata_{schema_cls.__name__.lower()}"

    schema_json = json.dumps(
        schema_cls.model_json_schema(), ensure_ascii=False, indent=2
    )
    system_msg = (
        "Du bist ein Analyse-Assistent. Extrahiere strukturierte Metadaten "
        "aus dem folgenden Report-Abschnitt.\n\n"
        f"## Pflicht-Schema ({schema_cls.__name__})\n"
        f"```json\n{schema_json}\n```\n\n"
        "## Harte Regeln\n"
        "1. Verwende AUSSCHLIESSLICH die im Schema definierten Feldnamen "
        "in snake_case (z. B. `field_name` statt `fieldName`).\n"
        "2. KEINE zusätzlichen Felder. Das Schema ist strict "
        "(`additionalProperties=false`); jedes unbekannte Feld lässt die "
        "Validierung fehlschlagen.\n"
        "3. Verwende nur Informationen, die explizit im Abschnittstext stehen. "
        "Erfinde keine Daten.\n"
        "4. Bei fehlenden Informationen: leere Liste oder Default-Wert. "
        "Nicht halluzinieren, nicht auffüllen."
    )
    if len(section_content) > METADATA_MAX_CONTENT_CHARS:
        logger.warning(
            "generate_section_metadata: section=%d Inhalt %d Zeichen > %d — "
            "Metadaten sehen einen gekürzten Text.",
            section_index,
            len(section_content),
            METADATA_MAX_CONTENT_CHARS,
        )
    user_msg = (
        f"## Abschnittstitel\n{section_title}\n\n"
        f"## Inhalt\n{section_content[:METADATA_MAX_CONTENT_CHARS]}"
    ) + _prior_thresholds_prompt(agent, schema_cls, section_index)

    try:
        result = agent.llm.chat_json(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=METADATA_MAX_OUTPUT_TOKENS,
            enforce_token_floor=False,
            schema=schema_cls,
            schema_name=schema_name,
            context="report",
        )
        logger.info(
            "generate_section_metadata: section=%d title=%r schema=%s",
            section_index,
            section_title,
            schema_cls.__name__,
        )
        return result
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.warning(
            "generate_section_metadata: section=%d schema=%s extraction failed: %r",
            section_index,
            schema_cls.__name__,
            exc,
        )
        from ...llm.errors import LLMOutputTruncatedError

        if isinstance(exc, LLMOutputTruncatedError):
            _record_metadata_truncation_degradation(
                agent,
                section_index=section_index,
                schema_name=schema_cls.__name__,
                exc=exc,
            )
        mark_metadata_failure(agent, section_index)
        return {}


def _is_cancel_requested(run_id: Optional[str]) -> bool:
    """Prüft das Cancel-Flag für ``run_id``; kein Fehler wenn run_id None."""
    if not run_id:
        return False
    try:
        from ..sim.cancel_flag import is_cancel_requested

        return is_cancel_requested(run_id)
    except Exception:  # noqa: BLE001 — cancel check fallback; returns False on failure
        return False


def _restore_work_trace_markers(agent: Any, report_id: str) -> None:
    """Stellt persistierte Run-Event-Marker bei einem Resume wieder her."""
    for index in sorted(_wf.ReportManager.load_work_trace_removed_sections(report_id)):
        mark_work_traces_removed(agent, index)
    for index in sorted(_wf.ReportManager.load_forced_final_sections(report_id)):
        mark_forced_final(agent, index)
    for index in sorted(_wf.ReportManager.load_metadata_failed_sections(report_id)):
        mark_metadata_failure(agent, index)
    if _wf.ReportManager.load_fallback_outline_used(report_id) is True:
        mark_fallback_outline_used(agent)


def _persist_work_trace_markers(agent: Any, report_id: str) -> None:
    """Schreibt Run-Event-Marker pro Section fort."""
    markers = events_for(agent).work_trace_removed_sections
    if markers:
        _wf.ReportManager.save_work_trace_removed_sections(report_id, markers)
    forced = events_for(agent).forced_final_sections
    if forced:
        _wf.ReportManager.save_forced_final_sections(report_id, forced)
    meta_failed = events_for(agent).metadata_failed_sections
    if meta_failed:
        _wf.ReportManager.save_metadata_failed_sections(report_id, meta_failed)


def _persist_fallback_outline_marker(agent: Any, report_id: str) -> None:
    """Persistiert das ``fallback_outline_used``-Flag für spätere Resumes."""
    used = bool(events_for(agent).fallback_outline_used)
    _wf.ReportManager.save_fallback_outline_used(report_id, used)


def _merge_run_degradations(
    existing_report: Optional[Report],
    freshly_collected: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Führt eine bereits persistierte Degradationsliste mit frisch
    berechneten Einträgen zusammen, statt sie zu ersetzen.
    """
    existing = existing_report.run_degradations if existing_report else None
    merged: List[Dict[str, Any]] = list(existing or [])
    seen = {
        (entry.get("component"), entry.get("reason"))
        for entry in merged
        if isinstance(entry, dict)
    }
    for entry in freshly_collected:
        key = (entry.get("component"), entry.get("reason"))
        if key not in seen:
            merged.append(entry)
            seen.add(key)
    return merged


def _build_partial_report(
    report: Report,
    *,
    report_id: str,
    completed_section_titles: List[str],
    outline: Any,
    agent: Any,
    progress_callback: Optional[Callable[[str, int, str], None]],
    quote_validation_failed_section_indices: Optional[List[int]] = None,
    failed_section_indices: Optional[List[int]] = None,
) -> Report:
    """Finalisiert einen Teil-Report nach kooperativem Cancel."""
    cancelled_at = datetime.now().isoformat()
    report.markdown_content = _wf.ReportManager.assemble_full_report(report_id, outline)
    total_sections = len(outline.sections)
    report.status = resolve_report_status(
        total_sections=total_sections,
        failed_section_indices=failed_section_indices or [],
        required_section_indices=list(range(1, total_sections + 1)),
    )
    evidence_map = agent.evidence_map if isinstance(agent.evidence_map, dict) else {}
    report.status = apply_degradation_downgrade(
        report.status,
        evidence_map.get("degradation_log") or [],
    )
    report.status = apply_quote_validation_downgrade(
        report.status,
        quote_validation_failed_section_indices or [],
    )
    report.completed_at = cancelled_at

    persona_fallbacks, persona_total = _wf._load_persona_fallback_stats(agent)
    missing_section_count = max(
        len(outline.sections) - len(completed_section_titles), 0
    )
    sim_llm_total, sim_llm_failed = _wf.load_simulation_llm_call_stats(
        report.simulation_id
    )
    fresh_degradations = collect_run_degradations(
        simulation_snapshot=report.simulation_snapshot,
        simulation_llm_calls_total=sim_llm_total,
        simulation_llm_calls_failed=sim_llm_failed,
        persona_fallback_count=persona_fallbacks,
        persona_total=persona_total,
        interviews_requested=_wf.breaker_for(agent).request_count("interview_agents"),
        interviews_succeeded=_wf._count_interview_evidence(agent),
        interview_disabled_reason=_wf.breaker_for(agent).reason_for("interview_agents"),
        failed_section_indices=failed_section_indices or [],
        fallback_outline_used=events_for(agent).fallback_outline_used,
        cancelled_missing_section_count=missing_section_count,
        forced_final_section_indices=events_for(agent).forced_final_sections,
        work_trace_removed_section_indices=sorted(
            events_for(agent).work_trace_removed_sections
        ),
        metadata_failed_section_indices=events_for(agent).metadata_failed_sections,
        stance_analysis=_wf._stance_analysis_of(agent),
    )
    report.run_degradations = _merge_run_degradations(report, fresh_degradations)
    report.status = apply_run_degradation_downgrade(
        report.status, report.run_degradations
    )
    _apply_requirement_check(report, agent, report_id)

    _wf.ReportManager.save_report(report)
    _persist_evidence_density(agent, report_id)

    partial_metadata: Dict[str, Any] = {
        "partial": True,
        "cancelled_at": cancelled_at,
        "completed_stages": list(completed_section_titles),
        "report_id": report_id,
    }
    partial_path = os.path.join(
        _wf.ReportManager._ensure_report_folder(report_id), "partial_metadata.json"
    )
    try:
        _wf.ReportManager._write_json_atomic(partial_path, partial_metadata)
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "_build_partial_report: could not write partial_metadata.json: %r", exc
        )

    if report.status == ReportStatus.INCOMPLETE:
        terminal_stage = "incomplete"
        terminal_message = (
            f"Partial report incomplete ({len(completed_section_titles)} "
            "sections completed before cancel)"
        )
    else:
        terminal_stage = "completed"
        terminal_message = (
            f"Partial report generated ({len(completed_section_titles)} "
            "sections completed before cancel)"
        )
    _wf.ReportManager.update_progress(
        report_id,
        terminal_stage,
        100,
        terminal_message,
        completed_sections=completed_section_titles,
    )
    if progress_callback:
        progress_callback(
            terminal_stage,
            100,
            terminal_message,
        )
    if agent.report_logger:
        agent.report_logger.log_report_complete(
            total_sections=len(completed_section_titles),
            total_time_seconds=0.0,
        )
    if agent.console_logger:
        agent.console_logger.close()
        agent.console_logger = None
    logger.info(
        "generate_report: partial report finalised report_id=%s sections=%d",
        report_id,
        len(completed_section_titles),
    )
    return report


def _apply_requirement_check(report: Report, agent: Any, report_id: str) -> None:
    """Issue #1302 / #1778: maschinelle Vollständigkeitprüfung vor dem Abschluss."""
    if not _wf.Config.REPORT_REQUIREMENT_CHECKER_ENABLED:
        return
    simulation_requirement = getattr(agent, "simulation_requirement", "") or ""
    requirement_intent = detect_report_intent(simulation_requirement)
    has_contested_question: Optional[bool] = None
    stance_analysis = getattr(agent, "stance_analysis", None)
    if stance_analysis is not None:
        if isinstance(stance_analysis, dict):
            has_contested_question = bool(stance_analysis.get("applicable"))
        else:
            has_contested_question = bool(getattr(stance_analysis, "applicable", False))

    missing_requirements = find_missing_requirements(
        [report.markdown_content],
        checklist=checklist_for_intent(
            requirement_intent,
            has_contested_question=has_contested_question,
            simulation_requirement=simulation_requirement if stance_analysis is not None else None,
        ),
    )
    if not missing_requirements:
        return
    report.run_degradations = list(report.run_degradations) + (
        collect_requirement_degradations(missing_requirements)
    )
    report.status = apply_run_degradation_downgrade(
        report.status,
        [
            entry
            for entry in report.run_degradations
            if entry.get("component") == "requirement_checker"
        ],
    )
    logger.warning(
        "generate_report: report=%s verfehlt %d Pflichtaspekt(e): %s",
        report_id,
        len(missing_requirements),
        ", ".join(req.id for req in missing_requirements),
    )
    if not getattr(report, "error", None):
        report.error = (
            "Inhaltliche Vollständigkeit unzureichend — fehlende Aspekte: "
            + ", ".join(req.id for req in missing_requirements)
        )


def _sections_with_persisted_evidence(agent: Any, report_id: str) -> List[Dict[str, Any]]:
    """Persistierte Sektionen ohne verwaiste Markdown-Dateien."""
    persisted_evidence_section_indices = {
        section.get("section_index")
        for section in (agent.evidence_map or {}).get("sections") or []
    }
    return [
        section_info
        for section_info in _wf.ReportManager.get_generated_sections(report_id)
        if section_info["section_index"] in persisted_evidence_section_indices
    ]


def _build_and_validate_report_v3(
    report: Any,
    agent: Any,
    *,
    report_mode: Optional[str],
    report_id: str,
) -> None:
    """Baut ReportV3 vorab und stuft den Report bei Schema-Verstoessen ab."""
    if not (report.status == ReportStatus.COMPLETED and agent.evidence_map):
        return
    try:
        _wf.ReportManager.build_report_v3(report, agent.evidence_map, report_mode=report_mode)
    except ValidationError as val_exc:
        error_count = len(val_exc.errors())
        logger.error(
            "generate_report: build_report_v3 hat report=%s vor der ersten "
            "Persistierung abgelehnt — %d Schema-Verletzung(en). Errors=%s",
            report_id,
            error_count,
            val_exc.errors()[:5],
        )
        if not getattr(report, "error", None):
            report.error = (
                f"Report enthält {error_count} unvollständige Section(s) — "
                "LLM-Calls sind fehlgeschlagen. Server-Logs zeigen die "
                "betroffenen Felder. Mit gültigem LLM-Profil neu starten."
            )
        report.status = apply_report_v3_validation_downgrade(
            report.status, val_exc.errors()
        )
        report.run_degradations = list(report.run_degradations) + (
            collect_run_degradations(contract_validation_errors=val_exc.errors())
        )
