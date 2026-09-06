from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from pydantic import ValidationError

from ...config import Config
from ...llm.tokens import PROMPT_HEADROOM_TOKENS
from ...contracts.report_v3 import (
    DEFAULT_REPORT_MODE,
    RED_TEAM_FINDINGS_LIMIT,
    ModelAttribution,
    ReportMode,
    ReportV3,
)
from ...models.report import Report, ReportStatus
from ...utils.logger import get_logger
from ..artifact_store import resolve_default_store
from ..report_intent import ReportIntent, detect_report_intent
from ..report_prompts import DEFAULT_REPORT_SECTIONS
from .contract_constants import MIN_PERSONA_TABLE_ROWS
from .contract_validator import matches_known_preset, validate_required_sections
from .evidence import validate_quote_anchors
from .manager import ReportManager
from .output_contract import (
    FinalContentRejected,
    apply_degradation_downgrade,
    apply_quote_validation_downgrade,
    apply_report_v3_validation_downgrade,
    is_fallback_content,
    resolve_report_status,
    sanitize_final_content,
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
    mark_forced_final,
    mark_metadata_failure,
    mark_work_traces_removed,
)
from .tool_circuit_breaker import breaker_for

from .planning import plan_outline as plan_outline_impl
from .postprocess_timing import PostprocessPhaseTracker
from .section_pipeline import (
    SectionContext,
    SectionResult,
    _section_expects_quotes,
    process_section,
)
from .search_dedup import (
    REPEATED_EMPTY_SEARCH_MSG,
    is_search_tool,
    query_of,
    registry_for,
)
from .simulation_snapshot import capture_simulation_snapshot
from .text_verification import verify_prose
from .schemas import (
    EvidenceMapModel,
    _section_schema_for,
)
from ..evidence_migrations import migrate_v1_to_v2, normalize_persisted_evidence_map
#: Evidence-*Typ* einer Interview-Antwort.
#:
#: Nicht die Quellengattung: ``source_kind`` fasst Interview-Antwort und
#: Simulationsbeitrag beide zu ``agent_quote`` zusammen (ADR-0002 Anker 3,
#: bewusst). Wer danach zählt, hält jeden Post der Simulation für ein
#: Interview — und findet ausgerechnet dann Interviews, wenn eine Simulation
#: lief und keines zustande kam. Genau der Fall des Referenzlaufs.
_INTERVIEW_EVIDENCE_TYPE = "agent_interview"


def _count_interview_evidence(agent: Any) -> int:
    """Wie viele Interviews tatsächlich Evidence hinterlassen haben.

    Bewusst aus dem Index abgeleitet statt separat mitgezählt: der Index ist
    das, was der Bericht am Ende benutzt. Ein Interview, das dort nichts
    hinterlässt, hat für den Bericht nicht stattgefunden — egal was der
    Tool-Aufruf gemeldet hat.
    """
    index = (getattr(agent, "evidence_map", None) or {}).get("evidence_index") or {}
    return sum(
        1
        for record in index.values()
        if isinstance(record, dict)
        and record.get("type") == _INTERVIEW_EVIDENCE_TYPE
    )


logger = get_logger('agora.report_agent')

# Die Abschnittsverarbeitung liegt seit Issue #1212 in ``section_pipeline``.
# ``_section_expects_quotes`` bleibt hier als Name erreichbar, damit bestehende
# Referenzen auf ``workflow`` nicht brechen.
__all__ = ["_section_expects_quotes", "chat", "generate_report", "generate_section_react"]


def _load_persona_count(agent: Any) -> int:
    """Best-effort count of generated personas for the report contract gate."""
    for attr in ("personas", "profiles", "persona_ids"):
        value = getattr(agent, attr, None)
        if isinstance(value, list):
            return len(value)

    try:
        profiles = resolve_default_store().read_json(
            agent.simulation_id,
            "reddit_profiles",
            default=[],
        )
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "persona-floor check: failed to read profiles for simulation %s: %r",
            getattr(agent, "simulation_id", "<unknown>"),
            exc,
        )
        return 0
    return len(profiles) if isinstance(profiles, list) else 0


def _load_persona_fallback_stats(agent: Any) -> tuple[int, int]:
    """(Platzhalter, gesamt) fuer die Degradierungssumme des Laufs (#1419).

    Gezaehlt wird ``generation_error``, nicht ``generation_source``: die
    bewusste Wahl ``use_llm_for_profiles=False`` erzeugt ebenfalls
    regelbasierte Profile und ist keine Degradierung. Nur der Ausfall nach
    gescheiterten LLM-Versuchen zaehlt.

    Wie beim Persona-Floor gilt: das Gate darf am Store nicht scheitern.
    Ohne lesbare Profile wird nichts behauptet.
    """
    try:
        profiles = resolve_default_store().read_json(
            agent.simulation_id,
            "reddit_profiles",
            default=[],
        )
    except Exception as exc:  # noqa: BLE001 — Gate darf am Store nicht scheitern
        logger.warning(
            "persona-fallback check: failed to read profiles for simulation %s: %r",
            getattr(agent, "simulation_id", "<unknown>"),
            exc,
        )
        return (0, 0)

    if not isinstance(profiles, list):
        return (0, 0)

    failed = sum(
        1
        for profile in profiles
        if isinstance(profile, dict) and profile.get("generation_error")
    )
    return (failed, len(profiles))


def _load_persona_floor(agent: Any) -> int:
    """Effektiver Persona-Floor für das Report-Contract-Gate.

    Liest den bei der Preparation persistierten ``persona_floor`` aus dem
    Simulation-State (Task: 50-Personas-Minimum dynamisch). Fallback ist
    MIN_PERSONA_TABLE_ROWS; ein persistierter Wert kann den Floor nur
    senken, nie über den Contract anheben.
    """
    try:
        data = resolve_default_store().read_json(
            agent.simulation_id,
            "state",
            default=None,
        )
    except Exception as exc:  # noqa: BLE001 — Gate darf am Store nicht scheitern
        logger.warning(
            "persona-floor check: failed to read state for simulation %s: %r",
            getattr(agent, "simulation_id", "<unknown>"),
            exc,
        )
        return MIN_PERSONA_TABLE_ROWS

    floor = data.get("persona_floor") if isinstance(data, dict) else None
    if isinstance(floor, int) and floor > 0:
        return min(floor, MIN_PERSONA_TABLE_ROWS)
    return MIN_PERSONA_TABLE_ROWS


def _load_persona_candidate_count(agent: Any) -> Optional[int]:
    """Kandidatenzahl vor der Profilgenerierung, fuer die Gate-Fehlermeldung (#1420).

    ``state.entities_count`` wird in ``prepare_service.py::_phase_read_entities``
    nach Dedup und Cap, aber vor dem Aufruf des Persona-Generators persistiert
    (``state.entities_count = filtered.filtered_count``) — das deckt sich mit
    dem Log ``Simulation preparation completed: entities=N, profiles=M``. Diese
    Zahl ist die Kandidatenmenge, die der Generator sieht.

    ``None`` wenn der Wert (noch) nicht vorliegt — der Aufrufer degradiert dann
    auf die knappe Fehlermeldung ohne Ablehnungszahl.
    """
    try:
        data = resolve_default_store().read_json(
            agent.simulation_id,
            "state",
            default=None,
        )
    except Exception as exc:  # noqa: BLE001 — Gate darf am Store nicht scheitern
        logger.warning(
            "persona-floor check: failed to read entities_count for simulation %s: %r",
            getattr(agent, "simulation_id", "<unknown>"),
            exc,
        )
        return None

    if not isinstance(data, dict):
        return None
    count = data.get("entities_count")
    return count if isinstance(count, int) and count > 0 else None


def _mark_incomplete_for_persona_floor(
    report: Report,
    *,
    report_id: str,
    persona_count: int,
    floor: int = MIN_PERSONA_TABLE_ROWS,
    candidate_count: Optional[int] = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> Report:
    report.status = ReportStatus.INCOMPLETE
    message = (
        "Persona-Mindestanzahl nicht erreicht: "
        f"{persona_count}/{floor} Personas vorhanden."
    )
    # Issue #1420 / Review-Nachbesserung (PR #1454): ohne diesen Zusatz sieht
    # die Meldung wie ein reiner Unterlauf aus, obwohl 15/20 durchaus aus 23
    # Kandidaten entstanden sein koennen. Die Differenz aber dem Eignungs-Gate
    # zuzuschreiben waere unbelegt: ``candidate_count`` (state.entities_count)
    # wird bei Branches unveraendert von der Quelle kopiert
    # (``branching_service.py::create_branch``), waehrend
    # ``_apply_persona_overrides`` und die manuelle Persona-Loeschroute
    # (``simulation_profiles.py``) nur ``reddit_profiles`` mutieren, nicht
    # diesen Zaehler. 20 kopierte Kandidaten mit einer absichtlich entfernten
    # Persona saehen dann wie eine Gate-Ablehnung aus, obwohl keine
    # stattgefunden hat. Reserve-Backfills koennen die Differenz ebenfalls von
    # der tatsaechlichen Ablehnungszahl des Generators abweichen lassen. Die
    # Meldung benennt die Differenz deshalb als Defizit, nicht als Ablehnung;
    # die tatsaechliche Ablehnungszahl kennt nur
    # ``OasisProfileGenerator.generate_profiles_from_entities`` (lokal,
    # aktuell nicht persistiert — Folgearbeit).
    if candidate_count is not None and candidate_count >= persona_count:
        deficit_count = candidate_count - persona_count
        message += (
            f" Von {candidate_count} Persona-Kandidaten sind nur {persona_count} "
            f"als Personas vorhanden — ein Defizit von {deficit_count}. Moegliche "
            "Ursachen sind das Eignungs-Gate (Ablehnung technischer Artefakte "
            "ohne eigene Interessenlage) oder eine nachtraegliche Entfernung "
            "(z. B. in einem Branch); aus dieser Zahl allein laesst sich das "
            "nicht unterscheiden."
        )
    report.missing_sections = [message]
    report.error = message
    ReportManager.update_progress(
        report_id,
        "incomplete",
        0,
        message,
        completed_sections=[],
    )
    ReportManager.save_report(report)
    if progress_callback:
        progress_callback("incomplete", 0, message)
    return report


def _get_echo_index(agent: Any) -> float:
    """Liest den aktuellen echo_chamber_index aus den Simulations-Metriken.

    Gibt 0.0 zurück wenn keine Metriken verfügbar sind.
    """
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


#: Ab diesem Echo-Chamber-Index lohnt der Red-Team-Call auch bei Report-Typen,
#: für die er nicht ohnehin verpflichtend ist.
_RED_TEAM_ECHO_THRESHOLD = 0.6

#: Report-Typen, bei denen die Red-Team-Stage unabhängig vom Echo-Index läuft.
#: Ein Risiko- oder Vergleichsreport und der vollständige Report stützen eine
#: Entscheidung — dort ist die Gegenprüfung Teil des Produkts, keine Zugabe für
#: unausgewogene Personas. Bei Meinungsbild und explorativem Report bleibt die
#: Schwelle als Kostenbremse.
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
    "Claim aus Abschnitt 3. Widersprüche zwischen weit auseinanderliegenden "
    "Abschnitten sind besonders zu prüfen — dort fallen sie beim Lesen am "
    "wenigsten auf.\n\n"
    "Identifiziere:\n"
    "(a) Widersprüche zwischen den Claims\n"
    "(b) Widersprüchliche operative Zahlen (zwei Schwellen für dieselbe Größe "
    "mit unterschiedlichen Werten)\n"
    "(c) Verfrühten Konsens (Claims, die ohne ausreichende Cross-Segment-Reaktionen "
    "als hoch-konfident markiert sind)\n"
    "(d) Fehlende Cross-Segment-Reaktionen\n\n"
    "Liefere maximal 10 Befunde als JSON-Objekt mit Feld 'findings' (Liste von Strings). "
    "Kein Markdown, reines JSON."
)

#: Obergrenze für die Antwort: zehn Befunde als Strings. Ausdrücklich gesetzt,
#: weil bei Ollama Prompt und Ausgabe ein Fenster teilen — eine großzügige
#: Ausgabe-Erlaubnis nimmt dem Entwurf den Platz weg
#: (``resolve_num_ctx_for_output``), und der Fehler käme still: der
#: ``except``-Zweig unten schriebe leere findings.
_RED_TEAM_MAX_TOKENS = 1_500

#: Zeichenbudget für den Berichtsentwurf, abgeleitet aus dem Platz, den der
#: Prompt bei Ollama sicher hat (``PROMPT_HEADROOM_TOKENS``). Gerechnet wird
#: mit knapp drei Zeichen je Token — deutscher Fachtext liegt eher darüber,
#: die Schätzung ist also die vorsichtige Richtung. Vom Ergebnis bleiben
#: 4000 Zeichen für System-Prompt und Rahmentext reserviert.
#:
#: Der Wert ist eine Kostenbremse gegen entartete Läufe (gemessen: bis 372
#: Claims in einem Artefakt), keine inhaltliche Auswahl.
_RED_TEAM_EXCERPT_BUDGET = PROMPT_HEADROOM_TOKENS * 3 - 4_000


def _build_red_team_excerpt(report_v3: ReportV3) -> str:
    """Baut den Berichtsentwurf für die Red-Team-Review (Issue #1359 B).

    Vorher sah der Reviewer ``claims[:20]``, ``hypotheses[:10]`` und davon die
    ersten 4000 Zeichen. Gemessen an acht Artefakten griff die Zeichengrenze in
    fünf Fällen — mitten im Satz. Im Referenzlauf hat der Reviewer daraus einen
    Befund erzeugt, der Bericht breche ab; das war der Schnitt des Excerpts,
    nicht des Berichts. Ein Reviewer, der einen Abbruch meldet, den es nicht
    gibt, ist schlimmer als keiner: er verbraucht Aufmerksamkeit für ein
    Artefakt des Werkzeugs.

    Die **Schwellen fehlten vollständig**. Genau darin lag der Widerspruch, den
    zu finden die Aufgabe der Stage ist: vier Wochen Pilotbetrieb in Abschnitt
    1, mindestens acht in Abschnitt 7. Der Reviewer konnte ihn nicht sehen.

    Gekürzt wird nur noch am Zeilenende und mit sichtbarer Marke, damit eine
    Kürzung als Kürzung erkennbar bleibt.
    """
    # Die Schwellen stehen zuerst, und das ist keine Frage der Lesbarkeit: die
    # Claim-Liste ist unbegrenzt (gemessen: 372 Stück). Stünden die Schwellen
    # dahinter, verbrauchten gerade die grossen Berichte — also die, bei denen
    # ein Widerspruch am ehesten unbemerkt bleibt — das Budget vor der ersten
    # Schwelle. Die Zahlen, wegen derer diese Stage existiert, fielen dann
    # genau dort weg, wo sie am nötigsten sind.
    lines: List[str] = []
    for threshold in report_v3.thresholds or []:
        # display_value statt f"{value:g} {unit}" (#1343): ein Datum trägt
        # keine Einheit, und ':g' an einem ISO-String würde den Entwurf
        # mitten in der Review-Vorbereitung sprengen.
        lines.append(
            f"- [{threshold.id}] [schwelle: {threshold.purpose}] {threshold.label}: "
            f"{threshold.display_value} "
            f"(Herkunft: {threshold.origin}, Beleglage: {threshold.evidence_status})"
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


#: Menschenlesbarer Wortlaut je Invariantenverletzung. Er steht im Bericht
#: neben den LLM-Befunden und muss ohne Codekenntnis verständlich sein.
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
    """Abzählbare Befunde über den Lauf — ohne LLM.

    Das Red Team des Referenzlaufs ``report_cc2ef45da5e9`` übersah null
    erfolgreiche Interviews, eine gescheiterte Simulation und einen leeren
    Degradation-Log. Alle drei lassen sich abzählen, und Abzählbares gehört
    nicht in einen Prompt: ein Sprachmodell kann sie übersehen, eine
    Invariante nicht.

    Läuft deshalb auch dann, wenn das LLM-Red-Team übersprungen wird.
    """
    snapshot = getattr(report, "simulation_snapshot", None) or {}
    violations = assert_run_invariants(
        status=str(getattr(getattr(report, "status", None), "value", "")),
        run_degradations=list(getattr(report, "run_degradations", []) or []),
        simulation_status=str(snapshot.get("simulation_status") or ""),
        interviews_requested=breaker_for(agent).request_count("interview_agents"),
        interviews_succeeded=_count_interview_evidence(agent),
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
    """Führt die Red-Team-Review-Stage aus und schreibt Findings in report_v3.

    Wird vor report_synthesis aufgerufen. Macht einen LLM-Call mit dem
    bestehenden agent.llm. Ob der Call stattfindet, entscheidet
    :func:`_red_team_required` aus Report-Typ und Echo-Index — bei
    entscheidungstragenden Reports immer, sonst ab der Echo-Schwelle. Bei
    Fehlern wird geloggt und unverändert zurückgegeben.

    Ein übersprungener Lauf hinterlässt keinen ``red_team``-Eintrag in
    ``model_attribution``; daran ist er von einem Lauf ohne Befunde
    unterscheidbar.

    Slice 5 (Issue #497), Intent-Gate aus dem Evidence-Chain-Audit (#1160).
    """
    # Die deterministischen Befunde hängen nicht am Intent-Gate: sie kosten
    # keinen LLM-Call und gelten für jeden Lauf.
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
        # Issue #978: Budgetabbruch (#764) ist kein Review-Fehler — hart
        # durchreichen, sonst schreibt der Red-Team-Schritt nach einem harten
        # Limit klaglos leere findings und der Run endet auf completed.
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
            # Die abzählbaren Befunde zuerst: sie sind sicher, die des Modells
            # sind Einschätzungen.
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


SECTION_FALLBACK_BODY = (
    "Diese Section konnte nicht generiert werden, weil der LLM-Aufruf "
    "fehlgeschlagen ist (siehe Server-Log: report_id={report_id}, "
    "section_index={section_index}). Mögliche Ursachen: ungültiger API-Key, "
    "Rate-Limit, Modell nicht verfügbar. Konfiguriere ein gültiges LLM-Profil "
    "(Settings → LLM-Provider) und starte den Report neu."
)
SECTION_FALLBACK_TITLE = "Section nicht generiert (LLM-Fehler)"

SECTION_EMPTY_RESPONSE_BODY = (
    "Dieser Abschnitt konnte nicht generiert werden: Das Modell lieferte eine "
    "leere Antwort. Bitte später erneut versuchen."
)

SECTION_UNUSABLE_OUTPUT_BODY = (
    "Dieser Abschnitt konnte nicht generiert werden: Das Modell lieferte "
    "ausschließlich interne Arbeitsschritte statt Berichtsinhalt ({reason}). "
    "Bitte später erneut versuchen."
)


def _finalize_content(
    response: str,
    *,
    section_title: str,
    section_index: int,
    agent: Any = None,
) -> str:
    """Wendet den Final-Content-Contract auf einen Modelloutput an.

    Ersetzt das frühere ``response.strip()``: interne Arbeitsschritte werden
    entfernt, und wenn danach kein Berichtsinhalt übrig bleibt, liefert die
    Funktion einen als solchen erkennbaren Fehlertext statt Modelloutput.
    Dieser Text wird von :func:`is_fallback_content` erkannt und weder zu
    Claims noch zu Evidence verarbeitet.

    Mit ``agent`` trägt eine Bereinigung mit erhaltenem Inhalt das Ereignis
    in ``RunEventLog.work_trace_removed_sections`` ein — Issue #1321: vorher
    stand sie nur im Server-Log, und der Bericht wies den Abschnitt aus wie
    jeden unangetasteten. Ohne ``agent`` bleibt es beim Log; der
    FinalContentRejected-Fall wird hier bewusst nicht markiert, er ist über
    ``generation_failed`` bzw. ``failed_section_indices`` bereits sichtbar.
    """
    try:
        sanitized = sanitize_final_content(response)
    except FinalContentRejected as exc:
        logger.warning(
            "section %d (%r): Final-Content-Contract hat den Output abgelehnt (%s). "
            "%d Arbeitsspur-Segment(e) verworfen.",
            section_index,
            section_title,
            exc.reason,
            len(exc.removed_segments),
        )
        return SECTION_UNUSABLE_OUTPUT_BODY.format(reason=exc.reason)

    if sanitized.removed_segments:
        logger.info(
            "section %d (%r): %d Arbeitsspur-Segment(e) aus dem Abschnittsinhalt entfernt.",
            section_index,
            section_title,
            len(sanitized.removed_segments),
        )
        if agent is not None:
            mark_work_traces_removed(agent, section_index)
    return sanitized.content


def _safe_generate_section_react(
    agent: Any,
    section,
    outline,
    previous_sections: List[str],
    progress_callback: Optional[Callable],
    section_index: int,
    report_id: str,
) -> str:
    """Track-3a-Wrapper: fängt Exceptions und leere Responses aus
    :func:`generate_section_react` und liefert einen sichtbaren Fallback-Text,
    damit die Pipeline nicht mit ``ReportV3.model_validate``-ValidationError
    aussteigt, wenn ein LLM-Call (z. B. 401 unauthorized) failed.
    """
    try:
        result = generate_section_react(
            agent,
            section=section,
            outline=outline,
            previous_sections=previous_sections,
            progress_callback=progress_callback,
            section_index=section_index,
        )
    except Exception as exc:  # noqa: BLE001 — Pipeline darf nicht crashen
        # Budgetabbruch (#764) ist kein Fallback-Fall: hart durchreichen, damit
        # der Run deterministisch mit termination_reason budget_* endet.
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.error(
            "section %d (%r): generate_section_react warf eine Exception: %r — "
            "Fallback-Content wird eingefügt.",
            section_index,
            getattr(section, "title", "<unbekannt>"),
            exc,
        )
        return SECTION_FALLBACK_BODY.format(
            report_id=report_id,
            section_index=section_index,
        )
    if not isinstance(result, str) or not result.strip():
        logger.warning(
            "section %d (%r) in report=%s: generate_section_react gab leeren/"
            "non-string Output zurück (type=%s) — Fallback-Content wird eingefügt.",
            section_index,
            getattr(section, "title", "<unbekannt>"),
            report_id,
            type(result).__name__,
        )
        return SECTION_FALLBACK_BODY.format(
            report_id=report_id,
            section_index=section_index,
        )
    return result


def generate_section_react(
    agent: Any,
    section,
    outline,
    previous_sections: List[str],
    progress_callback: Optional[Callable] = None,
    section_index: int = 0,
) -> str:
    logger.info(f"ReACT generating section: {section.title}")
    agent._current_section_index = section_index
    agent._active_section_evidence = []
    agent._active_section_unresolved_evidence = []

    if agent.report_logger:
        agent.report_logger.log_section_start(section.title, section_index)

    system_prompt = agent.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        report_title=outline.title,
        report_summary=outline.summary,
        simulation_requirement=agent.simulation_requirement,
        section_title=section.title,
        tools_description=agent._get_tools_description(),
        language=Config.REPORT_LANGUAGE,
    )

    if previous_sections:
        previous_parts = []
        for sec in previous_sections:
            truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
            previous_parts.append(truncated)
        previous_content = "\n\n---\n\n".join(previous_parts)
    else:
        previous_content = "(This is the first section)"

    user_prompt = agent.SECTION_USER_PROMPT_TEMPLATE.format(
        previous_content=previous_content,
        section_title=section.title,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    tool_calls_count = 0
    max_iterations = 5
    min_tool_calls = 1
    conflict_retries = 0
    # Issue #1191: die Merkliste ergebnisloser Suchen gilt pro Abschnitt. Ein
    # anderer Abschnitt darf dieselbe Suche erneut versuchen — sein Kontext ist
    # ein anderer, und die Suche ist billig genug, um sie nicht
    # abschnittsuebergreifend zu verbieten.
    # registry_for statt agent.empty_searches: der Zugriff muss auch dann eine
    # echte Merkliste liefern, wenn der Agent ein Test-Double ist — ein
    # MagicMock gaebe sonst fuer jede Suche ein truthy "war schon leer"
    # zurueck und wuerde alle Tool-Calls unterdruecken.
    registry_for(agent).reset()
    used_tools = set()
    all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}
    report_context = f"Section Title: {section.title}\nSimulation Requirement: {agent.simulation_requirement}"

    # Config normalisiert bereits, aber defense-in-depth: Runtime-Patches könnten
    # andere Casings/Werte einschleusen. Unbekannte Werte fallen auf "xml".
    _raw_toolcall_mode = (Config.REPORT_TOOLCALL_MODE or "xml").strip().lower()
    _toolcall_mode = _raw_toolcall_mode if _raw_toolcall_mode in ("native", "xml") else "xml"

    for iteration in range(max_iterations):
        if progress_callback:
            progress_callback(
                "generating",
                int((iteration / max_iterations) * 100),
                f"Deep retrieval and writing in progress ({tool_calls_count}/{agent.MAX_TOOL_CALLS_PER_SECTION})",
            )

        if _toolcall_mode == "native":
            # Nativer OpenAI function-calling Pfad
            openai_tools = agent._get_openai_tools_schema()
            native_result = agent.llm.chat_with_tools(
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
                temperature=0.5,
                max_tokens=4096,
                context="report",
            )
            response = native_result["content"]
            native_tool_calls = native_result["tool_calls"]

            if native_tool_calls:
                # Normalisiere zu internem Format {name, parameters}
                tool_calls = [
                    {"name": tc["name"], "parameters": tc["arguments"]}
                    for tc in native_tool_calls
                ]
                has_tool_calls = True
                has_final_answer = False
            else:
                # Kein nativer Tool-Call — Soft-Fallback: XML-Parser einmal probieren.
                # Issue #1277-1: ``content`` kann bei erschöpftem max_tokens,
                # Safety-Filter oder leerer Completion None sein. Dann wirft
                # ``_parse_tool_calls(None)`` (und ``"…" in None``) einen
                # TypeError, den ``_safe_generate_section_react`` abfängt — der
                # Section wird dauerhaft ``generation_failed``, obwohl der
                # vorgesehene None-Retry (weiter unten) einen weiteren Versuch
                # erlaubt. Hier None frühzeitig abfangen und den Retry-Pfad
                # erreichen lassen.
                if response is None:
                    tool_calls = []
                    has_tool_calls = False
                    has_final_answer = False
                else:
                    xml_fallback = agent._parse_tool_calls(response)
                    if xml_fallback:
                        tool_calls = xml_fallback
                        has_tool_calls = True
                        has_final_answer = False
                    else:
                        tool_calls = []
                        has_tool_calls = False
                        has_final_answer = "Final Answer:" in response
        else:
            # Legacy XML-Pfad
            response = agent.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)
            tool_calls = []
            has_tool_calls = False
            has_final_answer = False

        if response is None:
            logger.warning(f"Section {section.title} round {iteration + 1} iteration: LLM returned None")
            if iteration < max_iterations - 1:
                messages.append({"role": "assistant", "content": "(Response empty)"})
                messages.append({"role": "user", "content": "Please continue generating content."})
                continue
            break

        if _toolcall_mode == "xml":
            logger.debug(f"LLM response: {response[:200]}...")
            tool_calls = agent._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

        if has_tool_calls and has_final_answer:
            conflict_retries += 1
            logger.warning(
                f"Section {section.title} round {iteration+1} : "
                f"LLM simultaneously output tool calls and Final Answer (round {conflict_retries} conflicts)"
            )
            if conflict_retries <= 2:
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": (
                        "[Format Error] You cannot include both tool calls and Final Answer in one reply.\n"
                        "Each reply can only do one of the following:\n"
                        "- Call a tool (output a <tool_call> block, don't write Final Answer)\n"
                        "- Output final content (starting with 'Final Answer:', don't include <tool_call>)\n"
                        "Please reply again and only do one of these."
                    ),
                })
                continue
            logger.warning(
                "Section %s: %s consecutive conflicts, falling back to truncating the "
                "reply after the first tool call",
                section.title,
                conflict_retries,
            )
            first_tool_end = response.find('</tool_call>')
            if first_tool_end != -1:
                response = response[:first_tool_end + len('</tool_call>')]
                tool_calls = agent._parse_tool_calls(response)
                has_tool_calls = bool(tool_calls)
            has_final_answer = False
            conflict_retries = 0

        if agent.report_logger:
            agent.report_logger.log_llm_response(
                section_title=section.title,
                section_index=section_index,
                response=response,
                iteration=iteration + 1,
                has_tool_calls=has_tool_calls,
                has_final_answer=has_final_answer,
            )

        if has_final_answer:
            if tool_calls_count < min_tool_calls:
                messages.append({"role": "assistant", "content": response})
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)})" if unused_tools else ""
                messages.append({
                    "role": "user",
                    "content": agent.REACT_INSUFFICIENT_TOOLS_MSG.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            final_answer = _finalize_content(
                response,
                section_title=section.title,
                section_index=section_index,
                agent=agent,
            )
            logger.info(
                "Section %s generation completed (tool calls: %s)",
                section.title,
                tool_calls_count,
            )
            if agent.report_logger:
                agent.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count,
                )
            agent._current_section_index = None
            return final_answer

        if has_tool_calls:
            if tool_calls_count >= agent.MAX_TOOL_CALLS_PER_SECTION:
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": agent.REACT_TOOL_LIMIT_MSG.format(
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
                    ),
                })
                continue

            call = tool_calls[0]
            # Issue #1191: eine bereits ergebnislose Suche wird nicht mit einem
            # anderen Werkzeug wiederholt. Der Versuch zaehlt bewusst NICHT
            # gegen tool_calls_count — sonst spart die Unterdrueckung keine
            # Iteration ein und der Iterationsanschlag kommt genauso.
            _call_params = call.get("parameters", {}) or {}
            _call_query = query_of(_call_params)
            if is_search_tool(call["name"]) and registry_for(agent).was_empty(_call_query):
                logger.info(
                    "section %r: Suche %r uebersprungen — in diesem Abschnitt "
                    "bereits ergebnislos (Werkzeug %s)",
                    section.title,
                    _call_query,
                    call["name"],
                )
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REPEATED_EMPTY_SEARCH_MSG.format(
                        query=_call_query,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
                    ),
                })
                continue

            if agent.report_logger:
                agent.report_logger.log_tool_call(
                    section_title=section.title,
                    section_index=section_index,
                    tool_name=call["name"],
                    parameters=call.get("parameters", {}),
                    iteration=iteration + 1,
                )
            result = agent._execute_tool(call["name"], call.get("parameters", {}), report_context=report_context)
            if agent.report_logger:
                agent.report_logger.log_tool_result(
                    section_title=section.title,
                    section_index=section_index,
                    tool_name=call["name"],
                    result=result,
                    iteration=iteration + 1,
                )
            tool_calls_count += 1
            used_tools.add(call['name'])
            unused_tools = all_tools - used_tools
            unused_hint = ""
            if unused_tools and tool_calls_count < agent.MAX_TOOL_CALLS_PER_SECTION:
                unused_hint = agent.REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": agent.REACT_OBSERVATION_TEMPLATE.format(
                    tool_name=call["name"],
                    result=result,
                    tool_calls_count=tool_calls_count,
                    max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
                    used_tools_str=", ".join(used_tools),
                    unused_hint=unused_hint,
                ),
            })
            continue

        messages.append({"role": "assistant", "content": response})
        if tool_calls_count < min_tool_calls:
            unused_tools = all_tools - used_tools
            unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)})" if unused_tools else ""
            messages.append({
                "role": "user",
                "content": agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                    tool_calls_count=tool_calls_count,
                    min_tool_calls=min_tool_calls,
                    unused_hint=unused_hint,
                ),
            })
            continue

        # Kein "Final Answer:"-Präfix: der Output geht trotzdem durch den
        # Final-Content-Contract. Vorher wurde hier jeder Modelloutput
        # ungeprüft zum Abschnittsinhalt — inklusive "Thought:"-Spuren.
        final_answer = _finalize_content(
            response,
            section_title=section.title,
            section_index=section_index,
            agent=agent,
        )
        logger.info(
            "Section %s: no 'Final Answer:' prefix detected, using the sanitized LLM "
            "output as final content (tool calls: %s)",
            section.title,
            tool_calls_count,
        )
        if agent.report_logger:
            agent.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count,
            )
        agent._current_section_index = None
        return final_answer

    logger.warning(
        "Section %s reached the maximum iteration count, forcing final generation",
        section.title,
    )
    # Der Abschnitt entsteht unter Abbruchbedingungen. Bis hierher stand das
    # nur im Log — der Leser sah einen Abschnitt, dem er nicht ansehen konnte,
    # dass dem Agenten die Schritte ausgegangen waren.
    mark_forced_final(agent, section_index)
    messages.append({"role": "user", "content": agent.REACT_FORCE_FINAL_MSG})
    if _toolcall_mode == "native":
        force_result = agent.llm.chat_with_tools(
            messages=messages,
            tools=agent._get_openai_tools_schema(),
            tool_choice="none",
            temperature=0.5,
            max_tokens=4096,
            context="report",
        )
        response = force_result["content"]
    else:
        response = agent.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)
    if response is None:
        final_answer = SECTION_EMPTY_RESPONSE_BODY
    else:
        final_answer = _finalize_content(
            response,
            section_title=section.title,
            section_index=section_index,
            agent=agent,
        )
    if agent.report_logger:
        agent.report_logger.log_section_content(
            section_title=section.title,
            section_index=section_index,
            content=final_answer,
            tool_calls_count=tool_calls_count,
        )
    agent._current_section_index = None
    return final_answer


#: Notbremse für die Metadata-Extraktion: reale Sections liegen bei 5-12k
#: Zeichen; erst weit darüber wird gekürzt (und geloggt), damit keine
#: falschen "Abschnitt bricht ab"-Data-Gaps aus einem Preview entstehen.
METADATA_MAX_CONTENT_CHARS = 24000

#: Issue #1321: der frühere Aufruf setzte kein eigenes ``max_tokens`` und erbte
#: damit ``LLM_MAX_TOKENS_FLOOR`` — einen Boden, der für volle Fließtext-
#: Sections gedacht ist. Die Metadaten-Extraktion ist eine andere Aufgabe und
#: soll nicht mitwandern, wenn jemand den Prosa-Boden nachjustiert. Deshalb
#: ein eigener Wert plus ``enforce_token_floor=False``.
#:
#: **Bewusst nicht kleiner.** Naheliegend wäre ein enger Wert gewesen — die
#: Extraktion liefert kompaktes JSON. Genau das wäre hier falsch: im
#: beobachteten Lauf lief sie in das Ausgabelimit von ``gemini-2.0-flash``
#: (8192, ``app/llm/tokens.py::_MODEL_OUTPUT_LIMITS``). Dieses Modell ist
#: Legacy; aktuelle Gemini-Modelle greifen über den ``gemini-3``-Präfix und
#: lösen auf 65536 auf. Ein Deckel von 8192 hätte ihnen das Legacy-Limit
#: aufgezwungen — ausgerechnet den Wert, bei dem die Truncation auftrat.
#:
#: 32768 entspricht dem, was für Modelle mit ausreichendem Limit ohnehin galt.
#: Der Wert ist damit heute verhaltensneutral; was sich ändert, ist die
#: Entkopplung vom Prosa-Boden. ``resolve_max_tokens`` deckelt weiterhin auf
#: das Modell-Limit, Legacy-Modelle bekommen also unverändert ihre 8192 — und
#: ein Anschlag dort bleibt nicht mehr stumm (siehe
#: ``_record_metadata_truncation_degradation``). Der Hebel gegen die
#: Truncation selbst liegt auf der Eingangsseite
#: (``METADATA_MAX_CONTENT_CHARS``, Schemagröße) und gehört in einen eigenen
#: Slice.
METADATA_MAX_OUTPUT_TOKENS = 32768


def _record_metadata_truncation_degradation(
    agent: Any,
    *,
    section_index: int,
    schema_name: str,
    exc: Exception,
) -> None:
    """Haengt einen Truncation-Eintrag an ``agent.evidence_map['degradation_log']``.

    Feldform folgt ``EvidenceDegradationModel`` (``report_contract.py``) — das
    Feld ist additiv und Teil des persistierten ``EvidenceMapModel``-Contracts,
    daher keine freien Zusatzfelder. ``claim_id`` bleibt leer: die Extraktion
    ist an dieser Stelle abgebrochen, bevor irgendein Claim entstand.

    Defensiv: ``generate_section_metadata`` läuft früh in der Section-Pipeline;
    ``agent.evidence_map`` kann dort noch ``None`` sein (siehe
    ``ReportAgent.__init__``) oder in Tests ein ``MagicMock``. In beiden Fällen
    wird nur geloggt, nicht geschrieben — der Aufrufer bleibt unblockiert.
    """
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


def generate_section_metadata(
    agent: Any,
    section_title: str,
    section_content: str,
    section_index: int,
) -> Dict[str, Any]:
    """Extrahiert strukturierte Metadaten aus einem fertig generierten Abschnitt.

    Wählt via :func:`_section_schema_for` das passende ReportV3-DTO aus
    und übergibt es als ``schema=`` an :meth:`LLMClient.chat_json`.
    Bei nicht-strict-fähigen Providern greift llm_client.py automatisch
    auf json_object zurück — kein manueller Fallback nötig.

    Args:
        agent: Report-Agent-Instanz mit ``llm``-Attribut.
        section_title: Titel des Abschnitts (steuert DTO-Auswahl).
        section_content: Markdown-Text des generierten Abschnitts.
        section_index: 1-basierter Abschnittsindex (für Logging).

    Returns:
        Validiertes dict aus dem gewählten DTO (via model_dump).
        Bei Fehler leeres dict — die Hauptgenerierung ist nicht blockiert.
    """
    schema_cls = _section_schema_for(section_title)
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
    # Der frühere 6000-Zeichen-Cap schnitt reale Sections mittendrin ab —
    # die Metadata-Extraktion meldete daraufhin erfundene Data-Gaps wie
    # "Abschnitt bricht ab", obwohl der persistierte Text vollständig war
    # (report_06f654800817, Sections 3-6). Der Guard bleibt nur als
    # Notbremse gegen entartete Inhalte weit oberhalb realer Sectionlängen.
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
    )

    try:
        result = agent.llm.chat_json(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=METADATA_MAX_OUTPUT_TOKENS,
            # Kompakte Extraktion, kein Fließtext — der generische Report-Boden
            # (siehe Kommentar an METADATA_MAX_OUTPUT_TOKENS) ist hier fehl am Platz.
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
        # Issue #978: Budgetabbruch (#764) ist kein Extraktionsfehler — hart
        # durchreichen, sonst läuft die Section-Schleife nach einem harten
        # Limit klaglos weiter statt mit termination_reason=budget_* zu enden.
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.warning(
            "generate_section_metadata: section=%d schema=%s extraction failed: %r",
            section_index,
            schema_cls.__name__,
            exc,
        )
        # Issue #1321: Truncation lief bisher stumm in dieses generische
        # except — status=incomplete (#1299) hatte danach keine sichtbare
        # Begründung im console_log.txt. LLMOutputTruncatedError bekommt
        # deshalb einen eigenen degradation_log-Eintrag; weiterhin nicht
        # blockierend, ``return {}`` bleibt unten unverändert bestehen.
        from ...llm.errors import LLMOutputTruncatedError

        if isinstance(exc, LLMOutputTruncatedError):
            _record_metadata_truncation_degradation(
                agent,
                section_index=section_index,
                schema_name=schema_cls.__name__,
                exc=exc,
            )
        # Unabhängig von der Ursache: für diesen Abschnitt gibt es keine
        # strukturierten Metadaten. Personas, Schwellenwerte und
        # Reibungspunkte daraus fehlen im Artefakt, und das gehört in die
        # Qualitätsbilanz des Laufs — nicht nur ins Log.
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
    """Issue #1321 (Review-Finding PR #1378): Resume baut einen neuen
    Agenten; bereits persistierte Sections laufen nicht erneut durch
    _finalize_content, ihr Sanitization-Marker wäre also endgültig
    verloren. Der Zustand wird pro Lauf persistiert und hier — vor der
    ersten Cancel-Grenze — wiederhergestellt."""
    for index in sorted(ReportManager.load_work_trace_removed_sections(report_id)):
        mark_work_traces_removed(agent, index)


def _persist_work_trace_markers(agent: Any, report_id: str) -> None:
    """Issue #1321 (Review-Finding PR #1378): der Marker muss den Lauf
    überleben — Crash, Budgetabbruch und kooperativer Cancel dürfen ihn
    nicht mit dem Prozess vergessen. Deshalb pro Section fortschreiben,
    nicht erst am Laufende."""
    markers = events_for(agent).work_trace_removed_sections
    if markers:
        ReportManager.save_work_trace_removed_sections(report_id, markers)


def _build_partial_report(
    report: "Report",
    *,
    report_id: str,
    completed_section_titles: List[str],
    outline: Any,
    agent: Any,
    progress_callback: Optional[Callable[[str, int, str], None]],
    quote_validation_failed_section_indices: Optional[List[int]] = None,
) -> "Report":
    """Finalisiert einen Teil-Report nach kooperativem Cancel.

    Assembliert den Markdown-Inhalt aus den bereits geschriebenen Sections,
    setzt ``status=COMPLETED`` (success-with-caveat) und persistiert
    einen separaten Partial-Metadata-JSON-Artifact neben dem Report.
    """
    from ...models.report import ReportStatus
    from datetime import datetime
    import os

    cancelled_at = datetime.now().isoformat()
    report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
    report.status = ReportStatus.COMPLETED
    # Issue #1299 (Review-Finding Codex): eine bereits vor dem Cancel
    # erfolglos gebliebene Zitatpruefung (Repair-Retry ausgeschoepft) darf
    # den Teil-Report nicht unbemerkt als COMPLETED ausweisen — sonst
    # verschwindet das Signal beim naechsten Cancel genauso wie es der
    # Normalpfad ohne diesen Aufruf vermeidet.
    report.status = apply_quote_validation_downgrade(
        report.status, quote_validation_failed_section_indices or []
    )
    report.completed_at = cancelled_at

    # Issue #1321 (Review-Finding PR #1378): der Teil-Report erreichte die
    # einzige Degradations-Aggregation am normalen Laufende nie — eine vor
    # dem Cancel still bereinigte Section war damit auch im Partial Report
    # von einer unangetasteten nicht zu unterscheiden. Im flüchtigen
    # RunEventLog ist die Menge zu diesem Zeitpunkt vollständig; hier wird
    # die Summe gezogen, statt sie beim Abbruch zu verlieren.
    # Issue #1419 (Codex-Review PR #1420): auch der Teil-Report muss sagen,
    # worauf er beruht. Ohne die Persona-Zahlen ging ein nach dem Abbruch
    # finalisierter Bericht als COMPLETED hinaus, obwohl saemtliche Stimmen
    # darin regelbasierte Platzhalter waren — genau die Luecke, die der
    # Normalpfad seit diesem Issue schliesst.
    persona_fallbacks, persona_total = _load_persona_fallback_stats(agent)
    report.run_degradations = collect_run_degradations(
        persona_fallback_count=persona_fallbacks,
        persona_total=persona_total,
        work_trace_removed_section_indices=sorted(
            events_for(agent).work_trace_removed_sections
        ),
    )
    report.status = apply_run_degradation_downgrade(
        report.status, report.run_degradations
    )

    ReportManager.save_report(report)

    # Partial-Marker als separates Artifact persistieren
    # (Report-Dataclass hat kein metadata-Feld — Erweiterung ohne Schema-Migration)
    partial_metadata: Dict[str, Any] = {
        "partial": True,
        "cancelled_at": cancelled_at,
        "completed_stages": list(completed_section_titles),
        "report_id": report_id,
    }
    partial_path = os.path.join(
        ReportManager._ensure_report_folder(report_id), "partial_metadata.json"
    )
    try:
        ReportManager._write_json_atomic(partial_path, partial_metadata)
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "_build_partial_report: could not write partial_metadata.json: %r", exc
        )

    ReportManager.update_progress(
        report_id,
        "completed",
        100,
        f"Partial report generated ({len(completed_section_titles)} sections completed before cancel)",
        completed_sections=completed_section_titles,
    )
    if progress_callback:
        progress_callback(
            "completed",
            100,
            f"Partial report generated ({len(completed_section_titles)} sections)",
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
    """Issue #1302: maschinelle Vollständigkeitprüfung vor dem Abschluss.

    Der Reporter setzte ``completed``, ohne zu prüfen, ob die geforderten
    Analyseaspekte (Widersprüche, Frühwarnindikatoren, Stop-/Expand-
    Bedingungen, Positionswechsel, Koalitionen) im Bericht stehen. Fehlende
    Aspekte hängen als ``requirement_checker``-Degradationen an
    ``run_degradations`` und werden über dieselbe Mechanik abgestuft wie
    #1006/#1299 — keine zweite Statuslogik.

    Der Aufruf liegt NACH dem ReportV3-Build: der Contract-Export entscheidet
    über den Status bis dahin noch mit COMPLETED — würde dieser Check früher
    abstuften, würde ``build_report_v3`` übersprungen und das Artefakt
    fehlte. Erst danach stuft dieser Check ab und ein einziger ``save_report``
    persistiert Status + Fehlerliste zusammen.
    """
    if not Config.REPORT_REQUIREMENT_CHECKER_ENABLED:
        return
    requirement_intent = detect_report_intent(
        getattr(agent, "simulation_requirement", "") or ""
    )
    missing_requirements = find_missing_requirements(
        [report.markdown_content],
        checklist=checklist_for_intent(requirement_intent),
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


def generate_report(
    agent: Any,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    report_id: Optional[str] = None,
    *,
    report_mode: ReportMode = DEFAULT_REPORT_MODE,
    cancel_run_id: Optional[str] = None,
) -> Report:
    import uuid

    if not report_id:
        report_id = f"report_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()

    report = Report(
        report_id=report_id,
        simulation_id=agent.simulation_id,
        graph_id=agent.graph_id,
        simulation_requirement=agent.simulation_requirement,
        status=ReportStatus.PENDING,
        created_at=datetime.now().isoformat(),
        # Issue #1192: hier — und nicht am Ende — ist der Datenbestand
        # festgehalten, den der Agent tatsaechlich sieht.
        simulation_snapshot=capture_simulation_snapshot(agent.simulation_id),
    )

    completed_section_titles = []

    try:
        ReportManager._ensure_report_folder(report_id)
        # Issue #1340 (Codex-Review PR #1349): ``build_report_v3`` uebernimmt
        # Red-Team-Befunde und deren Modell-Zuordnung aus dem bestehenden
        # Artefakt, weil ein spaeterer ``save_report()`` sie sonst mit dem
        # Feld-Default ueberschreibt. Bei ``force_regenerate`` laeuft die
        # Generierung aber erneut auf derselben ``report_id`` — dann gehoeren
        # die alten Befunde zu einem anderen Claim-Set. Laeuft die
        # Red-Team-Stage im neuen Lauf durch, ueberschreibt sie sie ohnehin;
        # ueberspringt ``_red_team_required`` sie, blieben sie ohne diesen
        # Schnitt als stille Altlast stehen. Der Lauf beginnt deshalb ohne
        # fremden Review-Stand — das Erben gilt nur innerhalb eines Laufs.
        ReportManager.reset_review_state(report_id)
        legacy_evidence_map = migrate_v1_to_v2(
            ReportManager.get_evidence_map(report_id)
        )
        agent.evidence_map = normalize_persisted_evidence_map(legacy_evidence_map)
        if agent.evidence_map is None:
            agent._init_evidence_map(report_id)
            agent.evidence_map = EvidenceMapModel.model_validate(
                agent.evidence_map
            ).model_dump(mode="json")

        _restore_work_trace_markers(agent, report_id)

        agent.report_logger = agent.ReportLogger(report_id)
        agent.report_logger.log_start(
            simulation_id=agent.simulation_id,
            graph_id=agent.graph_id,
            simulation_requirement=agent.simulation_requirement,
        )
        agent.console_logger = agent.ReportConsoleLogger(report_id)

        ReportManager.update_progress(report_id, "pending", 0, "Initializing report...", completed_sections=[])
        ReportManager.save_report(report)

        report.status = ReportStatus.PLANNING
        ReportManager.update_progress(report_id, "planning", 5, "Start planning report outline...", completed_sections=[])
        agent.report_logger.log_planning_start()
        if progress_callback:
            progress_callback("planning", 0, "Start planning report outline...")

        existing_outline = ReportManager.get_report(report_id)
        if existing_outline and existing_outline.outline:
            outline = existing_outline.outline
        else:
            outline = plan_outline_impl(
                agent,
                progress_callback=lambda stage, prog, msg: progress_callback(stage, prog // 5, msg) if progress_callback else None,
            )
            agent.report_logger.log_planning_complete(outline.to_dict())
            ReportManager.save_outline(report_id, outline)

        report.outline = outline
        ReportManager.update_progress(report_id, "planning", 15, f"Outline planning completed, {len(outline.sections)} sections in total", completed_sections=[])
        ReportManager.save_report(report)

        # Cancel-Check nach Outline (Stage-Boundary 1)
        if _is_cancel_requested(cancel_run_id):
            return _build_partial_report(
                report,
                report_id=report_id,
                completed_section_titles=completed_section_titles,
                outline=outline,
                agent=agent,
                progress_callback=progress_callback,
            )

        required_titles = [title for title, _ in DEFAULT_REPORT_SECTIONS]
        outline_titles = [section.title for section in outline.sections]
        # Ein Intent-Preset (opinion, risk, …) ist ein vollständiger Report für
        # seine Fragestellung — nur der Full-Report schuldet die elf
        # Pflichtabschnitte. Spiegelt ReportOutlineModel.require_default_sections.
        missing = (
            []
            if matches_known_preset(outline_titles)
            else validate_required_sections(outline_titles, required_titles)
        )
        if missing:
            report.status = ReportStatus.INCOMPLETE
            report.missing_sections = missing
            message = f"Fehlende Pflichtabschnitte: {', '.join(missing)}"
            ReportManager.update_progress(
                report_id,
                "incomplete",
                0,
                message,
                completed_sections=[],
            )
            ReportManager.save_report(report)
            if progress_callback:
                progress_callback("incomplete", 0, message)
            if agent.console_logger:
                agent.console_logger.close()
                agent.console_logger = None
            return report

        persona_count = _load_persona_count(agent)
        persona_floor = _load_persona_floor(agent)
        if persona_count < persona_floor:
            report = _mark_incomplete_for_persona_floor(
                report,
                report_id=report_id,
                persona_count=persona_count,
                floor=persona_floor,
                candidate_count=_load_persona_candidate_count(agent),
                progress_callback=progress_callback,
            )
            if agent.console_logger:
                agent.console_logger.close()
                agent.console_logger = None
            return report

        report.status = ReportStatus.GENERATING
        total_sections = len(outline.sections)
        generated_sections = []
        # P0-7: Abschnitte, deren Generierung fehlgeschlagen ist. Eine
        # fehlgeschlagene Pflichtsection macht den Report INCOMPLETE.
        failed_section_indices: List[int] = []
        # Issue #1299: Abschnitte, deren Zitatprüfung (inkl. Repair-Retry)
        # erfolglos blieb — macht den Report ebenfalls höchstens INCOMPLETE.
        quote_validation_failed_section_indices: List[int] = []
        existing_sections = {item["section_index"]: item["content"] for item in ReportManager.get_generated_sections(report_id)}
        for section_info in ReportManager.get_generated_sections(report_id):
            title = outline.sections[section_info["section_index"] - 1].title if outline.sections and section_info["section_index"] <= len(outline.sections) else ""
            completed_section_titles.append(title)
            generated_sections.append(section_info["content"])

        # Issue #1212: Der Abschnitts-Durchlauf steht in ``section_pipeline``.
        # Die Seams werden hier aus den Modul-Globals dieses Moduls gebunden —
        # damit bleibt patchbar, was bisher patchbar war, ohne dass die
        # Pipeline ``workflow`` kennen muss.
        section_ctx = SectionContext(
            report_id=report_id,
            outline=outline,
            total_sections=total_sections,
            generate_section=_safe_generate_section_react,
            generate_metadata=generate_section_metadata,
            report_mode=report_mode,
            previous_sections=generated_sections,
            completed_section_titles=completed_section_titles,
            persisted_section_contents=existing_sections,
            progress_callback=progress_callback,
            validate_quotes=validate_quote_anchors,
            verify_prose_fn=verify_prose,
            is_fallback=is_fallback_content,
            report_manager=ReportManager,
            phase_tracker_factory=PostprocessPhaseTracker,
        )

        for i, section in enumerate(outline.sections):
            # Cancel-Check am Anfang jeder Section-Iteration (Stage-Boundary 2+)
            if _is_cancel_requested(cancel_run_id):
                return _build_partial_report(
                    report,
                    report_id=report_id,
                    completed_section_titles=completed_section_titles,
                    outline=outline,
                    agent=agent,
                    progress_callback=progress_callback,
                    quote_validation_failed_section_indices=quote_validation_failed_section_indices,
                )
            section_num = i + 1
            result: SectionResult = process_section(
                agent, section, section_ctx, section_index=section_num
            )
            if result.restored:
                continue
            if result.failed:
                failed_section_indices.append(section_num)
            if result.quote_validation_failed:
                quote_validation_failed_section_indices.append(section_num)
            generated_sections.append(result.markdown)
            completed_section_titles.append(result.title)
            _persist_work_trace_markers(agent, report_id)
            if agent.report_logger:
                agent.report_logger.log_section_full_complete(
                    section_title=result.title,
                    section_index=section_num,
                    full_content=result.markdown.strip(),
                )
            ReportManager.update_progress(
                report_id,
                "generating",
                section_ctx.base_progress_for(section_num) + int(70 / total_sections),
                f"Section {result.title} completed",
                current_section=None,
                completed_sections=completed_section_titles,
            )

        assembling_message = "Assembling the complete report..."
        if progress_callback:
            progress_callback("generating", 95, assembling_message)
        ReportManager.update_progress(report_id, "generating", 95, assembling_message, completed_sections=completed_section_titles)
        report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
        # P0-7: Status folgt dem tatsächlichen Erfolg der Abschnitte. Ein
        # Report mit fehlgeschlagener Pflichtsection ist INCOMPLETE — der Rest
        # bleibt nutzbar, aber der Nutzer sieht, was fehlt.
        report.status = resolve_report_status(
            total_sections=total_sections,
            failed_section_indices=failed_section_indices,
            required_section_indices=list(range(1, total_sections + 1)),
        )
        # Issue #1006: eine lokale Claim-Degradierung darf ein sonst
        # vollständiges Ergebnis nicht als COMPLETED ausweisen.
        report.status = apply_degradation_downgrade(
            report.status,
            (agent.evidence_map or {}).get("degradation_log") or [],
        )
        # Issue #1299: eine Section mit erfolglos gebliebener Zitatprüfung
        # (Repair-Retry ausgeschöpft) darf den Report nicht als COMPLETED
        # ausweisen — die Zitate darin sind nicht gegen die Evidenzbasis
        # verifiziert.
        report.status = apply_quote_validation_downgrade(
            report.status,
            quote_validation_failed_section_indices,
        )
        # Der Bericht muss über die Qualität seiner eigenen Grundlage Auskunft
        # geben. Im Referenzlauf report_cc2ef45da5e9 stand "completed" über
        # einer gescheiterten Simulation mit 45 von 48 Runden und null
        # zustande gekommenen Interviews — jede Komponente tat, was sie sollte,
        # nur zog niemand die Summe.
        persona_fallbacks, persona_total = _load_persona_fallback_stats(agent)
        report.run_degradations = collect_run_degradations(
            simulation_snapshot=report.simulation_snapshot,
            # Issue #1419: Ein Lauf, dessen Personas saemtlich Platzhalter
            # waren, meldete sich bis hierher als vollstaendig. Die
            # Vorbereitung erfasst den Ausfall bereits — nur zog ihn niemand
            # in den Bericht, der am Ende weitergegeben wird.
            persona_fallback_count=persona_fallbacks,
            persona_total=persona_total,
            interviews_requested=breaker_for(agent).request_count("interview_agents"),
            interviews_succeeded=_count_interview_evidence(agent),
            interview_disabled_reason=breaker_for(agent).reason_for("interview_agents"),
            failed_section_indices=failed_section_indices,
            forced_final_section_indices=events_for(agent).forced_final_sections,
            work_trace_removed_section_indices=events_for(
                agent
            ).work_trace_removed_sections,
            metadata_failed_section_indices=events_for(agent).metadata_failed_sections,
        )
        report.status = apply_run_degradation_downgrade(
            report.status, report.run_degradations
        )
        if failed_section_indices:
            failed_note = (
                f"{total_sections - len(failed_section_indices)}/{total_sections} "
                f"Sections erfolgreich. Fehlgeschlagen: "
                f"{', '.join(str(i) for i in sorted(failed_section_indices))}."
            )
            logger.warning("report %s: %s", report_id, failed_note)
            report.error = failed_note if not getattr(report, "error", None) else report.error
        report.completed_at = datetime.now().isoformat()
        total_time_seconds = (datetime.now() - start_time).total_seconds()
        if agent.report_logger:
            agent.report_logger.log_report_complete(total_sections=total_sections, total_time_seconds=total_time_seconds)

        # Issue #1299 (Review-Finding Codex/CodeRabbit): ``ReportManager.save_report()``
        # baut ``report-v3.json`` nur wenn ``report.status == COMPLETED`` ist und faengt
        # einen ``ValidationError`` dabei INTERN ab (kein Artefakt, aber auch kein Signal
        # an den Aufrufer, siehe ``manager.py::save_report``). Ohne diesen Vorab-Check
        # erreicht ein frisch fehlgeschlagener ReportV3-Build den Downgrade-Block unten
        # nie: ``get_report_v3()`` liefert ``None`` (kein Artefakt geschrieben), die
        # Truthiness-Pruefung dort ueberspringt den gesamten Validierungsblock, und
        # ``report.status`` bleibt faelschlich ``COMPLETED``.
        if report.status == ReportStatus.COMPLETED and agent.evidence_map:
            try:
                ReportManager.build_report_v3(report, agent.evidence_map, report_mode=report_mode)
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
                # Die Bilanz wurde oben gezogen, bevor dieser Fehler auftrat.
                # Ohne den Nachtrag stufte der Status zwar ab, aber
                # ``run_degradations`` bliebe leer — die API meldete einen
                # unvollständigen Contract-Export ohne einen einzigen Grund,
                # und die Red-Team-Invariante "degradiert, aber completed"
                # liefe ins Leere.
                report.run_degradations = list(report.run_degradations) + (
                    collect_run_degradations(
                        contract_validation_errors=val_exc.errors()
                    )
                )
        # Issue #1302: siehe _apply_requirement_check.
        _apply_requirement_check(report, agent, report_id)
        ReportManager.save_report(report)

        # ========== Red-Team-Review (Slice 5, Issue #497) — vor report_synthesis ==========
        # Track 3b: ValidationError separat fangen, damit ein durch LLM-Failures
        # entstandenes ReportV3-Schema-Loch (sections.N.title missing usw.) eine
        # klare user-facing Message produziert statt einen Pydantic-Stack-Trace
        # ins Frontend zu schicken.
        try:
            report_v3_raw = ReportManager.get_report_v3(report_id)
            if report_v3_raw:
                try:
                    report_v3_obj = ReportV3.model_validate(report_v3_raw)
                except ValidationError as val_exc:
                    error_count = len(val_exc.errors())
                    logger.error(
                        "generate_report: ReportV3.model_validate hat report=%s "
                        "abgelehnt — %d Schema-Verletzung(en), vermutlich aus "
                        "fehlgeschlagenen LLM-Calls. Errors=%s",
                        report_id,
                        error_count,
                        val_exc.errors()[:5],  # erste 5 für Logs, nicht den ganzen Trace
                    )
                    if report and not getattr(report, "error", None):
                        report.error = (
                            f"Report enthält {error_count} unvollständige Section(s) — "
                            "LLM-Calls sind fehlgeschlagen. Server-Logs zeigen die "
                            "betroffenen Felder. Mit gültigem LLM-Profil neu starten."
                        )
                    # Issue #1299: ein ReportV3, das seinen eigenen Contract
                    # nicht erfüllt, darf den Report nicht als COMPLETED
                    # stehen lassen. Der ``save_report`` oben (Zeile ~1209)
                    # hat bereits mit dem alten Status persistiert — bei einer
                    # Abstufung hier muss deshalb erneut gespeichert werden,
                    # sonst weichen persistierter Report und
                    # terminal_stage/Progress-Message voneinander ab.
                    previous_status = report.status
                    report.status = apply_report_v3_validation_downgrade(
                        report.status, val_exc.errors()
                    )
                    if report.status != previous_status:
                        ReportManager.save_report(report)
                    # Pipeline weiter ohne red_team_review — Report bleibt nutzbar
                    # mit Fallback-Content in den betroffenen Sections.
                    report_v3_obj = None
                if report_v3_obj is not None:
                    echo_index = _get_echo_index(agent)
                    # Gleiche reine Funktion wie in plan_outline auf derselben
                    # Eingabe — deterministisch identisch, kein zweiter Zustand.
                    intent = detect_report_intent(
                        getattr(agent, "simulation_requirement", "") or ""
                    )
                    report_v3_obj = _run_red_team_review(
                        agent,
                        report_v3_obj,
                        echo_index,
                        intent=intent,
                        deterministic_findings=_deterministic_red_team_findings(
                            agent, report
                        ),
                    )
                    ReportManager.save_report_v3(report_v3_obj)
                    logger.info(
                        "generate_report: red_team_review abgeschlossen, "
                        "findings=%d, intent=%s, echo_index=%.3f",
                        len(report_v3_obj.red_team_findings),
                        intent.value,
                        echo_index,
                    )
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            # Issue #978: Dieser Handler umschliesst den _run_red_team_review-Aufruf.
            # Ohne den Reraise waere der Fix INNERHALB von _run_red_team_review
            # wirkungslos — der dort korrekt durchgereichte Budgetabbruch wuerde
            # hier erneut verschluckt, die naechste Zeile setzte "completed", und
            # report_generation.py::except BudgetExceededError -> mark_budget_abort
            # wuerde nie erreicht. Genau das Symptom aus #978.
            from ..run_budget import BudgetExceededError

            if isinstance(exc, BudgetExceededError):
                raise
            logger.warning("generate_report: red_team_review fehlgeschlagen: %r", exc)
        # Issue #1277-2: Stage und Message folgen dem tatsächlichen Report-Status.
        # ``resolve_report_status``/``apply_degradation_downgrade`` können den
        # Report auf INCOMPLETE setzen (fehlgeschlagene Pflichtsection, lokale
        # Claim-Degradierung). Ein unbedingtes „completed“ bei 100 % würde
        # Consumern (WebSocket, Polling-Client, Streaming-UI) Erfolg vorgaukeln,
        # den die Pipeline selbst nicht einlöst — genau die Fehldarstellung, die
        # #1006 / P0-7 beseitigen sollte.
        if report.status == ReportStatus.INCOMPLETE:
            terminal_stage = "incomplete"
            terminal_message = report.error or "Report generation incomplete"
        else:
            terminal_stage = "completed"
            terminal_message = "Report generation completed"
        ReportManager.update_progress(report_id, terminal_stage, 100, terminal_message, completed_sections=completed_section_titles)
        if progress_callback:
            progress_callback(terminal_stage, 100, terminal_message)
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report

    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        # Budgetabbruch (#764) ist kein technischer Fehler: durchreichen, damit
        # report_generation den Run als "stopped" + termination_reason markiert.
        from ..run_budget import BudgetExceededError

        if isinstance(e, BudgetExceededError):
            raise
        # Bewusst nicht dieselbe Variable wie die Fortschrittsmeldung unten: der
        # Logger formatiert lazy über %, damit bei abgeschaltetem Level gar nichts
        # zusammengebaut wird. Genau dafür wurde die Zeile umgestellt.
        logger.error("Report generation failed: %s", e)
        report.status = ReportStatus.FAILED
        report.error = str(e)
        if agent.report_logger:
            agent.report_logger.log_error(str(e), "failed")
        try:
            ReportManager.save_report(report)
            ReportManager.update_progress(report_id, "failed", -1, f"Report generation failed: {e}", completed_sections=completed_section_titles)
        except Exception as exc:  # noqa: BLE001 — exc used in report status; error recorded
            logger.debug("workflow: save_report/update_progress failed in error handler, ignoring: %s", exc)
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report


def chat(agent: Any, message: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    logger.info("Report agent chat: %s...", message[:50])
    chat_history = chat_history or []
    report_content = ""
    try:
        report = ReportManager.get_report_by_simulation(agent.simulation_id)
        if report and report.markdown_content:
            report_content = report.markdown_content[:15000]
            if len(report.markdown_content) > 15000:
                report_content += "\n\n... [reportcontenthasTruncate] ..."
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning("Could not read the report content: %s", e)

    system_prompt = agent.CHAT_SYSTEM_PROMPT_TEMPLATE.format(
        simulation_requirement=agent.simulation_requirement,
        report_content=report_content if report_content else "(nonereport)",
        tools_description=agent._get_tools_description(),
        language=Config.REPORT_LANGUAGE,
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in chat_history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    tool_calls_made = []
    max_iterations = 2
    # Casing-tolerant + Whitelist (symmetrisch zu generate_section_react).
    _raw_chat_toolcall_mode = (Config.REPORT_TOOLCALL_MODE or "xml").strip().lower()
    _chat_toolcall_mode = (
        _raw_chat_toolcall_mode if _raw_chat_toolcall_mode in ("native", "xml") else "xml"
    )

    for _ in range(max_iterations):
        if _chat_toolcall_mode == "native":
            chat_result = agent.llm.chat_with_tools(
                messages=messages,
                tools=agent._get_openai_tools_schema(),
                tool_choice="auto",
                temperature=0.5,
                max_tokens=4096,
                context="report",
            )
            response = chat_result["content"]
            native_calls = chat_result["tool_calls"]
            tool_calls = (
                [{"name": tc["name"], "parameters": tc["arguments"]} for tc in native_calls]
                if native_calls
                else agent._parse_tool_calls(response)
            )
        else:
            response = agent.llm.chat(messages=messages, temperature=0.5)
            tool_calls = []

        if response is None:
            return {
                "response": "",
                "tool_calls": tool_calls_made,
                "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made],
            }

        if _chat_toolcall_mode == "xml":
            tool_calls = agent._parse_tool_calls(response)

        if not tool_calls:
            clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
            clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
            return {
                "response": clean_response.strip(),
                "tool_calls": tool_calls_made,
                "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made],
            }
        tool_results = []
        for call in tool_calls[:1]:
            if len(tool_calls_made) >= agent.MAX_TOOL_CALLS_PER_CHAT:
                break
            result = agent._execute_tool(call["name"], call.get("parameters", {}))
            tool_results.append({"tool": call["name"], "result": result[:1500]})
            tool_calls_made.append(call)
        messages.append({"role": "assistant", "content": response})
        observation = "\n".join([f"[{r['tool']}result]\n{r['result']}" for r in tool_results])
        messages.append({"role": "user", "content": observation + agent.CHAT_OBSERVATION_SUFFIX})

    if _chat_toolcall_mode == "native":
        final_result = agent.llm.chat_with_tools(
            messages=messages,
            tools=agent._get_openai_tools_schema(),
            tool_choice="none",
            temperature=0.5,
            max_tokens=4096,
            context="report",
        )
        final_response = final_result["content"]
    else:
        final_response = agent.llm.chat(messages=messages, temperature=0.5)
    if final_response is None:
        final_response = ""
    clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
    clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
    return {
        "response": clean_response.strip(),
        "tool_calls": tool_calls_made,
        "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made],
    }


__all__ = [
    "chat",
    "generate_report",
    "generate_section_metadata",
    "generate_section_react",
]
