from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ...utils.logger import get_logger
from ...utils.provider_message import redacted_provider_message as _redacted_provider_message
from .output_contract import (
    FinalContentRejected,
    is_fallback_content,
    sanitize_final_content,
)
from .run_degradation import (
    events_for,
    mark_forced_final,
    mark_work_traces_removed,
)
from .search_dedup import (
    dedup_key,
    is_search_tool,
    query_of,
    registry_for,
    repeated_empty_search_message,
)
from .section_coverage import section_has_sufficient_evidence
from . import workflow as _wf

logger = get_logger("agora.report_agent")

SECTION_FALLBACK_BODY = (
    "Diese Section konnte nicht generiert werden, weil der LLM-Aufruf "
    "fehlgeschlagen ist (siehe Server-Log: report_id={report_id}, "
    "section_index={section_index}). Mögliche Ursachen: ungültiger API-Key, "
    "Rate-Limit, Modell nicht verfügbar. Konfiguriere ein gültiges LLM-Profil "
    "(Settings → LLM-Provider) und starte den Report neu."
)
SECTION_FALLBACK_TITLE = "Section nicht generiert (LLM-Fehler)"

SECTION_FALLBACK_ERROR_BODY = (
    "Diese Section konnte nicht generiert werden, weil der LLM-Aufruf "
    "fehlgeschlagen ist (siehe Server-Log: report_id={report_id}, "
    "section_index={section_index}). Fehlerklasse: {error_class}. "
    "Providermeldung: {message} {hint}"
)
SECTION_FALLBACK_HINT_GENERIC = (
    "Mögliche Ursachen: ungültiger API-Key, Rate-Limit, Modell nicht "
    "verfügbar. Konfiguriere ein gültiges LLM-Profil "
    "(Settings → LLM-Provider) und starte den Report neu."
)
SECTION_FALLBACK_HINT_BAD_REQUEST = (
    "Der Provider hat die Anfrage als ungültig abgelehnt (HTTP 400); "
    "dieselbe Konfiguration wiederholt den Fehler deterministisch. Prüfe "
    "Modell und Parameter der Route (Settings → LLM-Provider) und starte "
    "den Report neu."
)
SECTION_FALLBACK_HINT_SKIPPED = (
    "Diese Section wurde übersprungen, weil ein vorheriger Abschnitt mit "
    "demselben nicht-transienten Provider-Fehler (HTTP 400) scheiterte; es "
    "wurde kein weiterer LLM-Aufruf abgesetzt. Prüfe Modell und Parameter "
    "der Route (Settings → LLM-Provider) und starte den Report neu."
)

_PROMPT_SPECIFIC_400_CODES = frozenset(
    {"context_length_exceeded", "content_policy_violation", "content_filter"}
)
_PROMPT_SPECIFIC_400_PHRASES = (
    "context length",
    "context_length",
    "maximum context",
    "too many tokens",
    "content policy",
    "content_filter",
)


def _is_persistent_provider_400(exc: BaseException) -> bool:
    """HTTP 400 des Providers, der für jeden Abschnitt gleich ausfiele (#1738)."""
    if getattr(exc, "status_code", None) != 400:
        return False
    body = getattr(exc, "body", None)
    message = str(exc).lower()
    if isinstance(body, dict):
        if str(body.get("code") or "").lower() in _PROMPT_SPECIFIC_400_CODES:
            return False
        message += " " + str(body.get("message") or "").lower()
    return not any(phrase in message for phrase in _PROMPT_SPECIFIC_400_PHRASES)


def _persistent_error_note(persistent_error: Optional[tuple[str, str]]) -> str:
    """Ursachen-Zusatz fuer ``report.error`` bei nicht-transientem 400 (#1738)."""
    if persistent_error is None:
        return ""
    return f" Ursache: {persistent_error[0]}: {persistent_error[1]}"


def _section_error_fallback(
    *,
    report_id: str,
    section_index: int,
    error_class: str,
    message: str,
    hint: str,
) -> str:
    return SECTION_FALLBACK_ERROR_BODY.format(
        report_id=report_id,
        section_index=section_index,
        error_class=error_class,
        message=message,
        hint=hint,
    )


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
    """Wendet den Final-Content-Contract auf einen Modelloutput an."""
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


def _draft_content(response: Optional[str]) -> str:
    """Berichtsinhalt eines Entwurfs, ohne ``_finalize_content``-Nebenwirkung."""
    if response is None:
        return ""
    try:
        content = sanitize_final_content(response).content
    except FinalContentRejected:
        return ""
    return "" if is_fallback_content(content) else content


def _section_has_sufficient_evidence(agent: Any, draft: str) -> bool:
    """Issue #1294: Deckung statt Tool-Call-Anzahl entscheidet über Retrieval."""
    return section_has_sufficient_evidence(
        draft,
        section_evidence=getattr(agent, "_active_section_evidence", None),
        evidence_map=getattr(agent, "evidence_map", None),
    )


def _request_coverage_retrieval(
    messages: List[Dict[str, str]],
    response: str,
    template: str,
    tool_calls_count: int,
    unused_tools: set,
) -> None:
    """Weist den ungedeckten Entwurf zurück und fordert gezieltes Retrieval an."""
    unused_hint = (
        f"(These tools have not been used, recommend using them: {', '.join(unused_tools)})"
        if unused_tools else ""
    )
    messages.append({"role": "assistant", "content": response})
    messages.append({
        "role": "user",
        "content": template.format(
            tool_calls_count=tool_calls_count,
            unused_hint=unused_hint,
        ),
    })


def _forced_final_response(
    agent: Any,
    messages: List[Dict[str, str]],
    toolcall_mode: str,
    pending_draft: Optional[str],
) -> Optional[str]:
    """Antwort für den Abschnitt, nachdem die Iterationen erschöpft sind."""
    if pending_draft is not None:
        return pending_draft
    messages.append({"role": "user", "content": agent.REACT_FORCE_FINAL_MSG})
    if toolcall_mode == "native":
        force_result = agent.llm.chat_with_tools(
            messages=messages,
            tools=agent._get_openai_tools_schema(),
            tool_choice="none",
            temperature=0.5,
            max_tokens=4096,
            context="report",
        )
        return force_result["content"]
    return agent.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)


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
    :func:`generate_section_react` und liefert einen sichtbaren Fallback-Text.
    """
    persistent = events_for(agent).persistent_provider_error
    if persistent is not None:
        logger.warning(
            "section %d (%r): übersprungen, vorheriger nicht-transienter "
            "Provider-400 (%s) — kein LLM-Call.",
            section_index,
            getattr(section, "title", "<unbekannt>"),
            persistent[0],
        )
        return _section_error_fallback(
            report_id=report_id,
            section_index=section_index,
            error_class=persistent[0],
            message=persistent[1],
            hint=SECTION_FALLBACK_HINT_SKIPPED,
        )
    try:
        result = _wf.generate_section_react(
            agent,
            section=section,
            outline=outline,
            previous_sections=previous_sections,
            progress_callback=progress_callback,
            section_index=section_index,
        )
    except Exception as exc:  # noqa: BLE001 — Pipeline darf nicht crashen
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
        error_class = type(exc).__name__
        message = _redacted_provider_message(exc)
        persistent_400 = _is_persistent_provider_400(exc)
        if persistent_400:
            events_for(agent).persistent_provider_error = (error_class, message)
        return _section_error_fallback(
            report_id=report_id,
            section_index=section_index,
            error_class=error_class,
            message=message,
            hint=(
                SECTION_FALLBACK_HINT_BAD_REQUEST
                if persistent_400
                else SECTION_FALLBACK_HINT_GENERIC
            ),
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


_POST_SEARCH_TOOL = "search_simulation_actions"


def _prefetch_simulation_posts(
    agent: Any,
    section: Any,
    section_index: int,
    report_context: str,
) -> tuple[Optional[str], int]:
    """Führt die Beitragssuche für den Abschnitt aus (Issue #1778)."""
    tools = getattr(agent, "tools", None)
    if not isinstance(tools, dict) or _POST_SEARCH_TOOL not in tools:
        return None, 0
    section_query = " ".join(
        part
        for part in (section.title, getattr(section, "description", "") or "")
        if isinstance(part, str) and part
    )
    requirement = agent.simulation_requirement
    queries = [section_query]
    if isinstance(requirement, str) and requirement:
        queries.append(requirement)
    executed = 0
    for query in queries:
        if not query:
            continue
        executed += 1
        result = _run_post_search(
            agent, section, section_index, report_context, {"query": query, "limit": 12}
        )
        if result is not None:
            return result, executed
    return None, executed


def _run_post_search(
    agent: Any,
    section: Any,
    section_index: int,
    report_context: str,
    parameters: Dict[str, Any],
) -> Optional[str]:
    """Ein Aufruf der Beitragssuche; ``None`` ohne Treffer oder bei Werkzeugfehler."""
    if agent.report_logger:
        agent.report_logger.log_tool_call(
            section_title=section.title,
            section_index=section_index,
            tool_name=_POST_SEARCH_TOOL,
            parameters=parameters,
            iteration=0,
        )
    result = agent._execute_tool(_POST_SEARCH_TOOL, parameters, report_context=report_context)
    if agent.report_logger:
        agent.report_logger.log_tool_result(
            section_title=section.title,
            section_index=section_index,
            tool_name=_POST_SEARCH_TOOL,
            result=result,
            iteration=0,
        )
    if not isinstance(result, str) or not result.startswith("Simulation posts"):
        return None
    if "no matching posts" in result.splitlines()[0]:
        return None
    return result


def _prefetch_into_prompt(
    agent: Any,
    section: Any,
    section_index: int,
    report_context: str,
    messages: List[Dict[str, Any]],
    used_tools: set,
) -> int:
    """Hängt die Vorab-Treffer an den ersten Prompt; liefert die Zahl der Suchen."""
    prefetched_posts, prefetch_calls = _prefetch_simulation_posts(
        agent, section, section_index, report_context
    )
    if prefetch_calls:
        used_tools.add(_POST_SEARCH_TOOL)
    if prefetched_posts is not None:
        messages[-1]["content"] += agent.REACT_PREFETCHED_POSTS_TEMPLATE.format(
            result=prefetched_posts,
            tool_calls_count=prefetch_calls,
            max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
        )
    elif prefetch_calls:
        messages[-1]["content"] += agent.REACT_PREFETCH_EMPTY_NOTE.format(
            tool_calls_count=prefetch_calls,
            max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
        )
    return prefetch_calls


def _build_initial_section_messages(
    agent: Any,
    section: Any,
    outline: Any,
    previous_sections: List[str],
) -> List[Dict[str, str]]:
    system_prompt = agent.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        report_title=outline.title,
        report_summary=outline.summary,
        simulation_requirement=agent.simulation_requirement,
        section_title=section.title,
        tools_description=agent._get_tools_description(),
        language=_wf.Config.REPORT_LANGUAGE,
    )
    if previous_sections:
        previous_parts = [
            sec[:4000] + "..." if len(sec) > 4000 else sec
            for sec in previous_sections
        ]
        previous_content = "\n\n---\n\n".join(previous_parts)
    else:
        previous_content = "(This is the first section)"

    user_prompt = agent.SECTION_USER_PROMPT_TEMPLATE.format(
        previous_content=previous_content,
        section_title=section.title,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _resolve_toolcall_mode() -> str:
    raw_mode = (_wf.Config.REPORT_TOOLCALL_MODE or "native").strip().lower()
    return raw_mode if raw_mode in ("native", "xml") else "native"


def _call_react_step_native(
    agent: Any,
    messages: List[Dict[str, str]],
) -> tuple[Optional[str], List[Dict[str, Any]], bool, bool]:
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
        tool_calls = [
            {"name": tc["name"], "parameters": tc["arguments"]}
            for tc in native_tool_calls
        ]
        return response, tool_calls, True, False
    if response is None:
        return None, [], False, False
    xml_fallback = agent._parse_tool_calls(response)
    if xml_fallback:
        return response, xml_fallback, True, False
    return response, [], False, "Final Answer:" in response


def _call_react_step_llm(
    agent: Any,
    messages: List[Dict[str, str]],
    toolcall_mode: str,
) -> tuple[Optional[str], List[Dict[str, Any]], bool, bool]:
    if toolcall_mode == "native":
        return _call_react_step_native(agent, messages)
    response = agent.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)
    if response is None:
        return None, [], False, False
    logger.debug(f"LLM response: {response[:200]}...")
    tool_calls = agent._parse_tool_calls(response)
    return response, tool_calls, bool(tool_calls), "Final Answer:" in response


def _resolve_tool_final_conflict(
    agent: Any,
    section: Any,
    messages: List[Dict[str, str]],
    response: str,
    tool_calls: List[Dict[str, Any]],
    iteration: int,
    conflict_retries: int,
) -> tuple[str, List[Dict[str, Any]], bool, bool, int, bool]:
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
        return response, tool_calls, True, True, conflict_retries, True
    logger.warning(
        "Section %s: %s consecutive conflicts, falling back to truncating the "
        "reply after the first tool call",
        section.title,
        conflict_retries,
    )
    first_tool_end = response.find("</tool_call>")
    has_tool_calls = True
    if first_tool_end != -1:
        response = response[: first_tool_end + len("</tool_call>")]
        tool_calls = agent._parse_tool_calls(response)
        has_tool_calls = bool(tool_calls)
    return response, tool_calls, has_tool_calls, False, 0, False


def _execute_react_tool_step(
    agent: Any,
    section: Any,
    section_index: int,
    iteration: int,
    response: str,
    call: Dict[str, Any],
    messages: List[Dict[str, str]],
    tool_calls_count: int,
    used_tools: set,
    all_tools: set,
    report_context: str,
) -> int:
    if tool_calls_count >= agent.MAX_TOOL_CALLS_PER_SECTION:
        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": agent.REACT_TOOL_LIMIT_MSG.format(
                tool_calls_count=tool_calls_count,
                max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
            ),
        })
        return tool_calls_count

    call_params = call.get("parameters", {}) or {}
    call_query = query_of(call_params)
    if is_search_tool(call["name"]) and registry_for(agent).was_empty(
        dedup_key(call["name"], call_params)
    ):
        logger.info(
            "section %r: Suche %r uebersprungen — in diesem Abschnitt "
            "bereits ergebnislos (Werkzeug %s)",
            section.title,
            call_query,
            call["name"],
        )
        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": repeated_empty_search_message(
                call["name"],
                call_params,
                tool_calls_count=tool_calls_count,
                max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
            ),
        })
        return tool_calls_count

    if agent.report_logger:
        agent.report_logger.log_tool_call(
            section_title=section.title,
            section_index=section_index,
            tool_name=call["name"],
            parameters=call.get("parameters", {}),
            iteration=iteration + 1,
        )
    result = agent._execute_tool(
        call["name"], call.get("parameters", {}), report_context=report_context
    )
    if agent.report_logger:
        agent.report_logger.log_tool_result(
            section_title=section.title,
            section_index=section_index,
            tool_name=call["name"],
            result=result,
            iteration=iteration + 1,
        )
    tool_calls_count += 1
    used_tools.add(call["name"])
    unused_tools = all_tools - used_tools
    unused_hint = ""
    if unused_tools and tool_calls_count < agent.MAX_TOOL_CALLS_PER_SECTION:
        unused_hint = agent.REACT_UNUSED_TOOLS_HINT.format(
            unused_list=", ".join(unused_tools)
        )
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
    return tool_calls_count


def _complete_section_output(
    agent: Any,
    section: Any,
    section_index: int,
    final_answer: str,
    tool_calls_count: int,
) -> str:
    if agent.report_logger:
        agent.report_logger.log_section_content(
            section_title=section.title,
            section_index=section_index,
            content=final_answer,
            tool_calls_count=tool_calls_count,
        )
    agent._current_section_index = None
    return final_answer


def _try_accept_section_draft(
    agent: Any,
    section: Any,
    section_index: int,
    response: str,
    messages: List[Dict[str, str]],
    insufficient_template: str,
    tool_calls_count: int,
    unused_tools: set,
    pending_draft: Optional[str],
    has_final_prefix: bool,
) -> tuple[Optional[str], Optional[str]]:
    draft = _draft_content(response)
    if not _section_has_sufficient_evidence(agent, draft):
        next_pending = response if draft else pending_draft
        _request_coverage_retrieval(
            messages,
            response,
            insufficient_template,
            tool_calls_count,
            unused_tools,
        )
        return None, next_pending

    final_answer = _finalize_content(
        response,
        section_title=section.title,
        section_index=section_index,
        agent=agent,
    )
    if has_final_prefix:
        logger.info(
            "Section %s generation completed (tool calls: %s)",
            section.title,
            tool_calls_count,
        )
    else:
        logger.info(
            "Section %s: no 'Final Answer:' prefix detected, using the sanitized LLM "
            "output as final content (tool calls: %s)",
            section.title,
            tool_calls_count,
        )
    return (
        _complete_section_output(
            agent, section, section_index, final_answer, tool_calls_count
        ),
        pending_draft,
    )


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

    messages = _build_initial_section_messages(
        agent, section, outline, previous_sections
    )
    tool_calls_count = 0
    max_iterations = 5
    pending_draft: Optional[str] = None
    conflict_retries = 0
    registry_for(agent).reset()
    used_tools: set = set()
    all_tools = {
        "insight_forge",
        "panorama_search",
        "quick_search",
        "interview_agents",
        "search_simulation_actions",
    }
    report_context = (
        f"Section Title: {section.title}\n"
        f"Simulation Requirement: {agent.simulation_requirement}"
    )

    tool_calls_count += _prefetch_into_prompt(
        agent, section, section_index, report_context, messages, used_tools
    )
    toolcall_mode = _resolve_toolcall_mode()

    for iteration in range(max_iterations):
        if progress_callback:
            progress_callback(
                "generating",
                int((iteration / max_iterations) * 100),
                f"Deep retrieval and writing in progress ({tool_calls_count}/{agent.MAX_TOOL_CALLS_PER_SECTION})",
            )

        response, tool_calls, has_tool_calls, has_final_answer = _call_react_step_llm(
            agent, messages, toolcall_mode
        )

        if response is None:
            logger.warning(f"Section {section.title} round {iteration + 1} iteration: LLM returned None")
            if iteration < max_iterations - 1:
                messages.append({"role": "assistant", "content": "(Response empty)"})
                messages.append({"role": "user", "content": "Please continue generating content."})
                continue
            break

        if has_tool_calls and has_final_answer:
            (
                response,
                tool_calls,
                has_tool_calls,
                has_final_answer,
                conflict_retries,
                should_retry,
            ) = _resolve_tool_final_conflict(
                agent, section, messages, response, tool_calls, iteration, conflict_retries
            )
            if should_retry:
                continue

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
            accepted, pending_draft = _try_accept_section_draft(
                agent,
                section,
                section_index,
                response,
                messages,
                agent.REACT_INSUFFICIENT_TOOLS_MSG,
                tool_calls_count,
                all_tools - used_tools,
                pending_draft,
                True,
            )
            if accepted is not None:
                return accepted
            continue

        if has_tool_calls:
            tool_calls_count = _execute_react_tool_step(
                agent,
                section,
                section_index,
                iteration,
                response,
                tool_calls[0],
                messages,
                tool_calls_count,
                used_tools,
                all_tools,
                report_context,
            )
            continue

        accepted, pending_draft = _try_accept_section_draft(
            agent,
            section,
            section_index,
            response,
            messages,
            agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT,
            tool_calls_count,
            all_tools - used_tools,
            pending_draft,
            False,
        )
        if accepted is not None:
            return accepted

    logger.warning(
        "Section %s reached the maximum iteration count, forcing final generation",
        section.title,
    )
    mark_forced_final(agent, section_index)
    response = _forced_final_response(agent, messages, toolcall_mode, pending_draft)
    final_answer = (
        SECTION_EMPTY_RESPONSE_BODY
        if response is None
        else _finalize_content(
            response,
            section_title=section.title,
            section_index=section_index,
            agent=agent,
        )
    )
    return _complete_section_output(
        agent, section, section_index, final_answer, tool_calls_count
    )
