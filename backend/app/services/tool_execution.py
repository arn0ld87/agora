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
    record_evidence: Optional[Callable[[str, Dict[str, Any], Any, str, int], None]] = None,
    section_index: int = 0,
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
            entgegennimmt. Bei ``None`` wird nichts geloggt.
        section_index: Index der aktuellen Report-Section, wird an den
            Evidence-Callback weitergereicht.

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
            )
            rendered = structured_result.to_text()

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

        else:
            return (
                f"Unknown tool: {tool_name}. Please use one of the following "
                "tools: insight_forge, panorama_search, quick_search"
            )

        if record_evidence is not None:
            record_evidence(
                tool_name,
                parameters,
                structured_result,
                rendered,
                section_index,
            )
        return rendered

    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
        return f"Tool execution failed: {str(e)}"


__all__ = ["execute_tool"]
