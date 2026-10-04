"""
Tool-Execution für den Report-Agent.

Issue #47 (EPIC-07-ST-03), Sub-Slice 3/3: Den Tool-Dispatcher aus
``services/report_agent.py`` als reine Funktion mit explizit übergebenen
Abhängigkeiten herauslösen, damit jeder Tool-Pfad isoliert gemockt und
getestet werden kann.

Die Funktion ist statelos — alle bisher aus ``self`` gelesenen Werte
(``graph_tools``, ``web_tools``, ``graph_id``, ``simulation_id``,
``simulation_requirement``) werden als kwargs erwartet. Optional kann ein
``record_evidence``-Callback übergeben werden, der nach erfolgreicher
Tool-Ausführung das Evidence-Logging übernimmt (im ReportAgent ist das
``_record_tool_evidence``).

Backwards-Compat-Redirects (``search_graph`` → ``quick_search``,
``get_simulation_context`` → ``insight_forge``) sind über rekursiven
Selbstaufruf erhalten.
"""

import json
from typing import Any, Callable, Dict, Optional

from ..utils.logger import get_logger

logger = get_logger("agora.tool_execution")


# Sentinel: Tools, die direkt JSON zurückgeben und KEIN Evidence-Recording
# auslösen (Backwards-Compat-Pfade). Spiegelt 1:1 das frühere Verhalten in
# ReportAgent._execute_tool, in dem diese Branches mit ``return ...``
# vorzeitig austraten.
_RAW_JSON_TOOLS = frozenset({
    "get_graph_statistics",
    "get_entity_summary",
    "get_entities_by_type",
})


def _contested_statement(simulation_id: Optional[str]) -> Optional[str]:
    """Liest die Streitfrage des Laufs aus dem persistierten Simulations-Config.

    Derselbe Leseweg wie ``interview_direct._simulation_context``. Fehlt die
    Datei oder die Streitfrage, gilt der Interview-Prompt ohne Streitfrage.
    """
    if not simulation_id:
        return None
    from .artifact_store import resolve_default_store

    try:
        config = (
            resolve_default_store().read_json(
                simulation_id, "simulation_config", default=None
            )
            or {}
        )
    except Exception as exc:  # noqa: BLE001 — Lesefehler heißt: keine Streitfrage bekannt
        logger.warning(f"Simulations-Config nicht lesbar ({simulation_id}): {exc}")
        return None
    question = config.get("contested_question") if isinstance(config, dict) else None
    statement = question.get("statement") if isinstance(question, dict) else None
    return statement if isinstance(statement, str) and statement.strip() else None


def _run_interview_agents(
    *,
    graph_tools: Any,
    parameters: Dict[str, Any],
    simulation_id: Optional[str],
    simulation_requirement: str,
    tool_name: str,
    on_terminal_failure: Optional[Callable[[str, str], None]],
) -> tuple[Any, str]:
    """Führt ``interview_agents`` aus und meldet einen terminalen Ausfall.

    Der Hinweistext im Ergebnis blieb im Referenzlauf folgenlos: das Tool
    wurde nach der Meldung noch sieben Mal aufgerufen. Der Aufrufer bekommt
    die Auskunft deshalb als Signal und kann das Tool tatsächlich abschalten.
    """
    interview_topic = parameters.get(
        "interview_topic",
        parameters.get("query", ""),
    )
    max_agents = parameters.get("max_agents", 5)
    if isinstance(max_agents, str):
        max_agents = int(max_agents)
    max_agents = min(max_agents, 10)
    structured_result = graph_tools.interview_agents(
        simulation_id=simulation_id,
        interview_requirement=interview_topic,
        simulation_requirement=simulation_requirement,
        max_agents=max_agents,
        contested_statement=_contested_statement(simulation_id),
    )
    if on_terminal_failure is not None and getattr(
        structured_result, "terminal_failure", False
    ):
        on_terminal_failure(
            tool_name,
            str(getattr(structured_result, "terminal_reason", "")),
        )
    return structured_result, structured_result.to_text()


def _optional_int(value: Any) -> Optional[int]:
    """Liest eine optionale Ganzzahl aus einem Tool-Parameter.

    Modelle liefern Zahlen auch als String. Fehlend, leer oder nicht lesbar
    heißt: der Filter ist nicht gesetzt.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _run_search_simulation_actions(
    *, parameters: Dict[str, Any], simulation_id: Optional[str]
) -> tuple[Any, str]:
    """Führt ``search_simulation_actions`` aus (Issue #1778, Schritt 1.7)."""
    from .report_agent import action_search

    limit = _optional_int(parameters.get("limit"))
    structured_result = action_search.search_simulation_actions(
        simulation_id=simulation_id or "",
        query=str(parameters.get("query") or ""),
        agent_name=str(parameters.get("agent_name") or ""),
        round_from=_optional_int(parameters.get("round_from")),
        round_to=_optional_int(parameters.get("round_to")),
        limit=limit if limit is not None else 12,
    )
    return structured_result, structured_result.to_text()


def _record_and_annotate(
    *,
    tool_name: str,
    parameters: Dict[str, Any],
    structured_result: Any,
    rendered: str,
    section_index: int,
    record_evidence: Optional[Callable[[str, Dict[str, Any], Any, str, int], Optional[Dict[int, str]]]],
    annotate_rendered: Optional[Callable[[Any, str], str]],
) -> str:
    """Evidence registrieren, dann den gerenderten Text nachbearbeiten."""
    if record_evidence is not None:
        recorded_evidence_ids = record_evidence(
            tool_name,
            parameters,
            structured_result,
            rendered,
            section_index,
        )
        # Issue #1300 (Review-Finding Codex, P1): die ``ev_``-ID einer
        # Interviewantwort entsteht erst beim Registrieren oben — der
        # ReACT-Loop sieht sonst nur den zuvor gerenderten Text ohne ID
        # und kann ein Zitat daraus nie gueltig verankern. Der zweite
        # ``to_text()``-Aufruf reichert das bereits Registrierte nur mit
        # der jetzt bekannten ID an, ohne erneut zu registrieren.
        if tool_name in ("interview_agents", "search_simulation_actions") and recorded_evidence_ids:
            rendered = structured_result.to_text(evidence_ids=recorded_evidence_ids)
    if annotate_rendered is not None:
        rendered = annotate_rendered(structured_result, rendered)
    return rendered


def execute_tool(
    *,
    tool_name: str,
    parameters: Dict[str, Any],
    report_context: str,
    graph_tools: Any,
    web_tools: Any,
    graph_id: str,
    simulation_id: Optional[str],
    simulation_requirement: str,
    record_evidence: Optional[Callable[[str, Dict[str, Any], Any, str, int], Optional[Dict[int, str]]]] = None,
    section_index: int = 0,
    on_terminal_failure: Optional[Callable[[str, str], None]] = None,
    annotate_rendered: Optional[Callable[[Any, str], str]] = None,
) -> str:
    """Dispatcht einen Tool-Aufruf und liefert das gerenderte Resultat als String.

    Args:
        tool_name: Tool-Bezeichner (z. B. ``"insight_forge"``).
        parameters: Tool-Parameter aus dem LLM-Call.
        report_context: Kontextstring, den InsightForge zur Sub-Frage-Generierung
            nutzt. Falls ``parameters["report_context"]`` gesetzt ist, gewinnt
            der parameter-Wert.
        graph_tools: ``GraphToolsService``-Instanz.
        web_tools: ``WebToolsService``-Instanz (für ``web_search``/``fetch_url``).
        graph_id, simulation_id, simulation_requirement: aktive Run-Identifier.
        record_evidence: optionaler Callback, der nach erfolgreicher Ausführung
            ``(tool_name, parameters, structured_result, rendered_text, section_index)``
            entgegennimmt. Bei ``None`` wird nichts geloggt. Für
            ``interview_agents`` liefert der Callback optional eine
            ``{0-basierter Interview-Index: evidence_id}``-Zuordnung zurück
            (Issue #1300) — die IDs entstehen erst beim Registrieren, danach
            wird der Interview-Text damit angereichert neu gerendert.
        section_index: Index der aktuellen Report-Section, wird an den
            Evidence-Callback weitergereicht.
        annotate_rendered: optionaler Callback ``(structured_result, rendered)``
            → ``rendered``, der das Ergebnis nach dem Registrieren kennzeichnet
            (Issue #1240: Szenario-/Erwartungstext des Eingabedokuments).

    Returns:
        Gerendertes Ergebnis als String. Bei unbekanntem Tool oder Exception
        ein Fehlertext (kein Raise nach außen — historisches Verhalten).
    """
    logger.info(f"Executing tool: {tool_name}, parameters: {parameters}")

    try:
        structured_result: Any = None
        rendered: Optional[str] = None

        if tool_name == "insight_forge":
            query = parameters.get("query", "")
            ctx = parameters.get("report_context", "") or report_context
            structured_result = graph_tools.insight_forge(
                graph_id=graph_id,
                query=query,
                simulation_requirement=simulation_requirement,
                report_context=ctx,
            )
            rendered = structured_result.to_text()

        elif tool_name == "panorama_search":
            query = parameters.get("query", "")
            include_expired = parameters.get("include_expired", True)
            if isinstance(include_expired, str):
                include_expired = include_expired.lower() in ["true", "1", "yes"]
            structured_result = graph_tools.panorama_search(
                graph_id=graph_id,
                query=query,
                include_expired=include_expired,
            )
            rendered = structured_result.to_text()

        elif tool_name == "quick_search":
            query = parameters.get("query", "")
            limit = parameters.get("limit", 10)
            if isinstance(limit, str):
                limit = int(limit)
            structured_result = graph_tools.quick_search(
                graph_id=graph_id,
                query=query,
                limit=limit,
            )
            rendered = structured_result.to_text()

        elif tool_name == "interview_agents":
            structured_result, rendered = _run_interview_agents(
                graph_tools=graph_tools,
                parameters=parameters,
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                tool_name=tool_name,
                on_terminal_failure=on_terminal_failure,
            )

        elif tool_name == "web_search":
            query = parameters.get("query", "")
            max_results = parameters.get("max_results", 5)
            if isinstance(max_results, str):
                try:
                    max_results = int(max_results)
                except ValueError:
                    max_results = 5
            structured_result = web_tools.web_search(query=query, max_results=max_results)
            rendered = web_tools.format_search_result(structured_result)

        elif tool_name == "fetch_url":
            url = parameters.get("url", "")
            structured_result = web_tools.fetch_url(url=url)
            rendered = web_tools.format_extract_result(structured_result)

        # ── Backwards-Compat-Redirects ──

        elif tool_name == "search_graph":
            logger.info("search_graph has been redirected to quick_search")
            return execute_tool(
                tool_name="quick_search",
                parameters=parameters,
                report_context=report_context,
                graph_tools=graph_tools,
                web_tools=web_tools,
                graph_id=graph_id,
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                record_evidence=record_evidence,
                section_index=section_index,
            )

        elif tool_name == "get_simulation_context":
            logger.info("get_simulation_context has been redirected to insight_forge")
            query = parameters.get("query", simulation_requirement)
            return execute_tool(
                tool_name="insight_forge",
                parameters={"query": query},
                report_context=report_context,
                graph_tools=graph_tools,
                web_tools=web_tools,
                graph_id=graph_id,
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                record_evidence=record_evidence,
                section_index=section_index,
            )

        elif tool_name == "get_graph_statistics":
            result = graph_tools.get_graph_statistics(graph_id)
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "get_entity_summary":
            entity_name = parameters.get("entity_name", "")
            result = graph_tools.get_entity_summary(
                graph_id=graph_id,
                entity_name=entity_name,
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        elif tool_name == "get_entities_by_type":
            entity_type = parameters.get("entity_type", "")
            nodes = graph_tools.get_entities_by_type(
                graph_id=graph_id,
                entity_type=entity_type,
            )
            return json.dumps([n.to_dict() for n in nodes], ensure_ascii=False, indent=2)

        elif tool_name == "search_simulation_actions":
            structured_result, rendered = _run_search_simulation_actions(
                parameters=parameters,
                simulation_id=simulation_id,
            )

        else:
            return (
                f"Unknown tool: {tool_name}. Please use one of the following "
                "tools: insight_forge, panorama_search, quick_search, "
                "search_simulation_actions"
            )

        return _record_and_annotate(
            tool_name=tool_name,
            parameters=parameters,
            structured_result=structured_result,
            rendered=rendered,
            section_index=section_index,
            record_evidence=record_evidence,
            annotate_rendered=annotate_rendered,
        )

    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        # Issue #978: Budgetabbruch (#764) ist kein Tool-Fehler — hart
        # durchreichen, sonst liest der ReACT-Loop einen harmlosen
        # "Tool execution failed"-Observation-Text statt den Run mit
        # termination_reason=budget_* zu beenden.
        from .run_budget import BudgetExceededError

        if isinstance(e, BudgetExceededError):
            raise
        logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
        return f"Tool execution failed: {str(e)}"


__all__ = ["execute_tool"]
