from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from ...config import Config
from ...contracts.report_v3 import DEFAULT_REPORT_MODE, ModelAttribution, ReportMode, ReportV3
from ...models.report import Report, ReportStatus
from ...utils.logger import get_logger
from ..artifact_store import resolve_default_store
from ..report_prompts import DEFAULT_REPORT_SECTIONS
from .contract_constants import MIN_PERSONA_TABLE_ROWS
from .contract_validator import validate_required_sections
from .evidence import validate_quote_anchors
from .manager import ReportManager
from .planning import plan_outline as plan_outline_impl
from .schemas import (
    CURRENT_SCHEMA_VERSION,
    EvidenceMapModel,
    _section_schema_for,
    migrate_v1_to_v2,
)

logger = get_logger('agora.report_agent')

# M11.8e — Section-Typen, die Persona-Zitate enthalten können/sollen.
# Für diese Sections wird validate_quote_anchors mit strict-Repair-Retry ausgeführt.
# Meta-Sections (Plan, Executive Summary, Datenlücken) sind ausgenommen.
_QUOTE_REQUIRED_SECTION_KEYWORDS = frozenset({
    "persona",
    "personas",
    "zielgrupp",
    "segment",
    "multipli",
    "multiplier",
    "friction",
    "reibung",
    "trust",
    "vertrauen",
    "interview",
    "reaktion",
    "reaction",
})


def _section_expects_quotes(section_title: str) -> bool:
    """Gibt True zurück wenn der Abschnittstyp Persona-Zitate erwarten lässt."""
    lower = section_title.lower()
    return any(kw in lower for kw in _QUOTE_REQUIRED_SECTION_KEYWORDS)


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


def _mark_incomplete_for_persona_floor(
    report: Report,
    *,
    report_id: str,
    persona_count: int,
    floor: int = MIN_PERSONA_TABLE_ROWS,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> Report:
    report.status = ReportStatus.INCOMPLETE
    message = (
        "Persona-Mindestanzahl nicht erreicht: "
        f"{persona_count}/{floor} Personas vorhanden."
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


_RED_TEAM_SYSTEM_PROMPT = (
    "Du bist ein kritischer Qualitätsprüfer für Szenarienanalysen. "
    "Du prüfst einen Berichtsentwurf auf Schwachstellen im Wording-Glossar v1 "
    "(VERBOTEN: 'Vorhersage', 'Prognose', 'wird eintreten'; ERLAUBT: Simulation, "
    "Szenarienanalyse, Reaktionsmuster, Einschätzung). "
    "Antworte ausschliesslich auf Deutsch."
)

_RED_TEAM_USER_TEMPLATE = (
    "Berichtsentwurf (gekürzt):\n\n{report_excerpt}\n\n"
    "Identifiziere:\n"
    "(a) Widersprüche zwischen den Claims\n"
    "(b) Verfrühten Konsens (Claims, die ohne ausreichende Cross-Segment-Reaktionen "
    "als hoch-konfident markiert sind)\n"
    "(c) Fehlende Cross-Segment-Reaktionen\n\n"
    "Liefere maximal 10 Befunde als JSON-Objekt mit Feld 'findings' (Liste von Strings). "
    "Kein Markdown, reines JSON."
)


def _run_red_team_review(
    agent: Any,
    report_v3: ReportV3,
    echo_index: float,
) -> ReportV3:
    """Führt die Red-Team-Review-Stage aus und schreibt Findings in report_v3.

    Wird vor report_synthesis aufgerufen. Macht einen LLM-Call mit dem
    bestehenden agent.llm. Bei echo_index <= 0.6 wird kein LLM-Call ausgeführt
    (findings bleibt leer). Bei Fehlern wird geloggt und unverändert zurückgegeben.

    Slice 5 (Issue #497).
    """
    if echo_index <= 0.6:
        logger.info(
            "_run_red_team_review: echo_index=%.3f <= 0.6, kein LLM-Call (balanced Personas)",
            echo_index,
        )
        return report_v3

    # Berichtsentwurf-Excerpt aufbauen (Claims + Hypotheses als Kontext)
    claim_lines = [
        f"- [{c.confidence}] {c.statement}"
        for c in (report_v3.claims or [])[:20]
    ]
    hyp_lines = [
        f"- [hypothesis] {h.hypothesis_text}"
        for h in (report_v3.hypotheses or [])[:10]
    ]
    report_excerpt = "\n".join(claim_lines + hyp_lines) or "(kein Inhalt)"

    user_msg = _RED_TEAM_USER_TEMPLATE.format(report_excerpt=report_excerpt[:4000])

    started_at = datetime.now(timezone.utc)
    try:
        raw = agent.llm.chat_json(
            messages=[
                {"role": "system", "content": _RED_TEAM_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
            context="report",
        )
        findings_raw = raw.get("findings") if isinstance(raw, dict) else None
        if isinstance(findings_raw, list):
            findings = [str(f) for f in findings_raw if str(f).strip()][:10]
        else:
            findings = []
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
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
            "red_team_findings": findings,
            "model_attribution": updated_attribution,
        }
    )
    logger.info(
        "_run_red_team_review: %d Befunde, echo_index=%.3f",
        len(findings),
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
    min_tool_calls = 3
    conflict_retries = 0
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
                # Kein nativer Tool-Call — Soft-Fallback: XML-Parser einmal probieren
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
                f"Section {section.title}: consecutive {conflict_retries} conflicts，downgraded to truncate and execute first tool call"
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
                unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)}）" if unused_tools else ""
                messages.append({
                    "role": "user",
                    "content": agent.REACT_INSUFFICIENT_TOOLS_MSG.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            final_answer = response.split("Final Answer:")[-1].strip()
            logger.info(f"Section {section.title} generation completed (tool calls: {tool_calls_count}times)")
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
                unused_hint = agent.REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))
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
            unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)}）" if unused_tools else ""
            messages.append({
                "role": "user",
                "content": agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                    tool_calls_count=tool_calls_count,
                    min_tool_calls=min_tool_calls,
                    unused_hint=unused_hint,
                ),
            })
            continue

        final_answer = response.strip()
        logger.info(f"Section {section.title} did not detectto 'Final Answer:' prefix, directlyadoptLLM outputas finalcontent（Tool call: {tool_calls_count}times)")
        if agent.report_logger:
            agent.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count,
            )
        agent._current_section_index = None
        return final_answer

    logger.warning(f"Section {section.title} reachedmaximumiterationscount，Forcegenerate")
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
        final_answer = "(ThisSectiongeneratefailed: LLM returnedemptyresponse, pleaselaterretry)"
    elif "Final Answer:" in response:
        final_answer = response.split("Final Answer:")[-1].strip()
    else:
        final_answer = response
    if agent.report_logger:
        agent.report_logger.log_section_content(
            section_title=section.title,
            section_index=section_index,
            content=final_answer,
            tool_calls_count=tool_calls_count,
        )
    agent._current_section_index = None
    return final_answer


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
    user_msg = (
        f"## Abschnittstitel\n{section_title}\n\n"
        f"## Inhalt\n{section_content[:6000]}"
    )

    try:
        result = agent.llm.chat_json(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
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
        logger.warning(
            "generate_section_metadata: section=%d schema=%s extraction failed: %r",
            section_index,
            schema_cls.__name__,
            exc,
        )
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


def _build_partial_report(
    report: "Report",
    *,
    report_id: str,
    completed_section_titles: List[str],
    outline: Any,
    agent: Any,
    progress_callback: Optional[Callable[[str, int, str], None]],
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
    report.completed_at = cancelled_at

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
    )

    completed_section_titles = []

    try:
        ReportManager._ensure_report_folder(report_id)
        agent.evidence_map = migrate_v1_to_v2(ReportManager.get_evidence_map(report_id)) or (
            EvidenceMapModel.model_validate({
                "schema_version": CURRENT_SCHEMA_VERSION,
                "report_id": report_id,
                "simulation_id": agent.simulation_id,
                "global_evidence": agent._collect_simulation_evidence_items(),
                "sections": [],
            }).model_dump(mode="json")
        )

        agent.report_logger = agent.ReportLogger(report_id)
        agent.report_logger.log_start(
            simulation_id=agent.simulation_id,
            graph_id=agent.graph_id,
            simulation_requirement=agent.simulation_requirement,
        )
        agent.console_logger = agent.ReportConsoleLogger(report_id)

        ReportManager.update_progress(report_id, "pending", 0, "Initializereport...", completed_sections=[])
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
        ReportManager.update_progress(report_id, "planning", 15, f"Outline planning completed, total{len(outline.sections)}sections", completed_sections=[])
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
        missing = validate_required_sections(outline_titles, required_titles)
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
                progress_callback=progress_callback,
            )
            if agent.console_logger:
                agent.console_logger.close()
                agent.console_logger = None
            return report

        report.status = ReportStatus.GENERATING
        total_sections = len(outline.sections)
        generated_sections = []
        existing_sections = {item["section_index"]: item["content"] for item in ReportManager.get_generated_sections(report_id)}
        for section_info in ReportManager.get_generated_sections(report_id):
            title = outline.sections[section_info["section_index"] - 1].title if outline.sections and section_info["section_index"] <= len(outline.sections) else ""
            completed_section_titles.append(title)
            generated_sections.append(section_info["content"])

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
                )
            section_num = i + 1
            base_progress = 20 + int((i / total_sections) * 70)
            if section_num in existing_sections:
                section.content = ReportManager._clean_section_content(existing_sections[section_num], section.title)
                persisted_sections = (agent.evidence_map or {}).get("sections") or []
                has_persisted_evidence = any(s.get("section_index") == section_num for s in persisted_sections)
                if not has_persisted_evidence:
                    logger.warning(
                        "Section %s already exists on disk without persisted evidence; preserving markdown and leaving evidence unchanged",
                        section_num,
                    )
                continue
            ReportManager.update_progress(report_id, "generating", base_progress, f"generatinggenerateSection: {section.title} ({section_num}/{total_sections})", current_section=section.title, completed_sections=completed_section_titles)
            if progress_callback:
                progress_callback("generating", base_progress, f"generatinggenerateSection: {section.title} ({section_num}/{total_sections})")
            section_content = _safe_generate_section_react(
                agent,
                section=section,
                outline=outline,
                previous_sections=generated_sections,
                progress_callback=lambda stage, prog, msg: progress_callback(stage, base_progress + int(prog * 0.7 / total_sections), msg) if progress_callback else None,
                section_index=section_num,
                report_id=report_id,
            )
            # M11.8e + P4.1: Quote-Anchor-Validierung für Persona-/Segment-/Friction-Sections.
            # Nur bei Section-Typen, die Persona-Zitate erwarten (nicht Plan/Meta-Sections).
            # explorative: Validierung vollständig überspringen.
            # balanced: Best-Effort-Repair-Retry (aktuelles Verhalten).
            # strict: Hart — fehlgeschlagener Repair setzt quota_validation_failed=True
            #         und wird prominent geloggt; kein weiteres Fallback.
            if _section_expects_quotes(section.title) and report_mode != "explorative":
                evidence_map_for_validation = agent.evidence_map or {}
                persona_ids_for_validation: List[str] = getattr(agent, "persona_ids", []) or []
                quote_result = validate_quote_anchors(
                    section_content,
                    evidence_map_for_validation,
                    persona_ids_for_validation,
                )
                if not quote_result.valid:
                    repair_hint = (
                        f"Korrigiere die Persona-Zitate: "
                        f"invalid_quotes={quote_result.invalid_quotes!r}, "
                        f"unbound_evidence_refs={quote_result.unbound_evidence_refs!r}. "
                        f"Jedes Zitat MUSS <simulated_quote persona_id=\"...\" seed_anchor=\"...\">...</simulated_quote> "
                        f"mit gültigen Attributen verwenden."
                    )
                    logger.warning(
                        "quote_anchor_validation: section=%d title=%r mode=%s — "
                        "invalid quotes detected, attempting repair retry. "
                        "invalid_quotes=%r unbound_refs=%r",
                        section_num,
                        section.title,
                        report_mode,
                        quote_result.invalid_quotes,
                        quote_result.unbound_evidence_refs,
                    )
                    repair_content = _safe_generate_section_react(
                        agent,
                        section=section,
                        outline=outline,
                        previous_sections=generated_sections,
                        progress_callback=None,
                        section_index=section_num,
                        report_id=report_id,
                    )
                    repair_result = validate_quote_anchors(
                        repair_content,
                        evidence_map_for_validation,
                        persona_ids_for_validation,
                    )
                    if repair_result.valid:
                        section_content = repair_content
                        logger.info(
                            "quote_anchor_validation: section=%d repair successful",
                            section_num,
                        )
                    else:
                        # Repair fehlgeschlagen — Section trotzdem weiter, Flag setzen
                        log_fn = logger.error if report_mode == "strict" else logger.warning
                        log_fn(
                            "quote_anchor_validation: section=%d mode=%s repair retry also failed. "
                            "Setting quote_validation_failed=True. "
                            "repair_invalid_quotes=%r repair_unbound=%r",
                            section_num,
                            report_mode,
                            repair_result.invalid_quotes,
                            repair_result.unbound_evidence_refs,
                        )
                        if not hasattr(section, "metadata") or section.metadata is None:
                            section.metadata = {}
                        section.metadata["quote_validation_failed"] = True
                        section_content = repair_content
                        _ = repair_hint  # consumed in log above
            # M11.8d: Strukturierte Metadaten-Extraktion via strict-schema chat_json.
            # Fehler blockieren nicht die Hauptgenerierung (generate_section_metadata
            # gibt bei Exception {} zurück). Metadaten werden im Report-Logger
            # für Provenance-Tracking gespeichert.
            section_meta = generate_section_metadata(
                agent,
                section_title=section.title,
                section_content=section_content,
                section_index=section_num,
            )
            if section_meta and agent.report_logger and hasattr(agent.report_logger, "log_section_metadata"):
                agent.report_logger.log_section_metadata(
                    section_title=section.title,
                    section_index=section_num,
                    metadata=section_meta,
                )
            section.content = section_content
            generated_sections.append(f"## {section.title}\n\n{section_content}")
            ReportManager.save_section(report_id, section_num, section)
            agent._save_evidence_section(report_id, section_num, section.title, section_content)
            completed_section_titles.append(section.title)
            if agent.report_logger:
                agent.report_logger.log_section_full_complete(
                    section_title=section.title,
                    section_index=section_num,
                    full_content=f"## {section.title}\n\n{section_content}".strip(),
                )
            ReportManager.update_progress(report_id, "generating", base_progress + int(70 / total_sections), f"Section {section.title} completed", current_section=None, completed_sections=completed_section_titles)

        if progress_callback:
            progress_callback("generating", 95, "generatingassemblecompletereport...")
        ReportManager.update_progress(report_id, "generating", 95, "generatingassemblecompletereport...", completed_sections=completed_section_titles)
        report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
        report.status = ReportStatus.COMPLETED
        report.completed_at = datetime.now().isoformat()
        total_time_seconds = (datetime.now() - start_time).total_seconds()
        if agent.report_logger:
            agent.report_logger.log_report_complete(total_sections=total_sections, total_time_seconds=total_time_seconds)
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
                    # Pipeline weiter ohne red_team_review — Report bleibt nutzbar
                    # mit Fallback-Content in den betroffenen Sections.
                    report_v3_obj = None
                if report_v3_obj is not None:
                    echo_index = _get_echo_index(agent)
                    report_v3_obj = _run_red_team_review(agent, report_v3_obj, echo_index)
                    ReportManager.save_report_v3(report_v3_obj)
                    logger.info(
                        "generate_report: red_team_review abgeschlossen, "
                        "findings=%d, echo_index=%.3f",
                        len(report_v3_obj.red_team_findings),
                        echo_index,
                    )
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.warning("generate_report: red_team_review fehlgeschlagen: %r", exc)
        ReportManager.update_progress(report_id, "completed", 100, "reportgeneratecomplete", completed_sections=completed_section_titles)
        if progress_callback:
            progress_callback("completed", 100, "reportgeneratecomplete")
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report

    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error(f"reportgeneratefailed: {str(e)}")
        report.status = ReportStatus.FAILED
        report.error = str(e)
        if agent.report_logger:
            agent.report_logger.log_error(str(e), "failed")
        try:
            ReportManager.save_report(report)
            ReportManager.update_progress(report_id, "failed", -1, f"reportgeneratefailed: {str(e)}", completed_sections=completed_section_titles)
        except Exception as exc:  # noqa: BLE001 — exc used in report status; error recorded
            logger.debug("workflow: save_report/update_progress failed in error handler, ignoring: %s", exc)
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report


def chat(agent: Any, message: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    logger.info(f"Report Agentchat: {message[:50]}...")
    chat_history = chat_history or []
    report_content = ""
    try:
        report = ReportManager.get_report_by_simulation(agent.simulation_id)
        if report and report.markdown_content:
            report_content = report.markdown_content[:15000]
            if len(report.markdown_content) > 15000:
                report_content += "\n\n... [reportcontenthasTruncate] ..."
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(f"getreportcontentfailed: {e}")

    system_prompt = agent.CHAT_SYSTEM_PROMPT_TEMPLATE.format(
        simulation_requirement=agent.simulation_requirement,
        report_content=report_content if report_content else "（nonereport）",
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
