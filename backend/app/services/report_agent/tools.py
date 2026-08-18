from __future__ import annotations

from typing import Any, Dict, List

from ..tool_execution import execute_tool
from ..tool_schema import (
    TOOL_DESC_INSIGHT_FORGE,
    TOOL_DESC_INTERVIEW_AGENTS,
    TOOL_DESC_PANORAMA_SEARCH,
    TOOL_DESC_QUICK_SEARCH,
)
from ..tool_validation import (
    is_valid_tool_call as _is_valid_tool_call,
    parse_tool_calls as _parse_tool_calls,
)


from .tool_circuit_breaker import breaker_for


def define_tools(agent: Any) -> Dict[str, Dict[str, Any]]:
    tools: Dict[str, Dict[str, Any]] = {
        "insight_forge": {
            "name": "insight_forge",
            "description": TOOL_DESC_INSIGHT_FORGE,
            "parameters": {
                "query": "The question or topic you want to deeply analyze",
                "report_context": "Context of current report section (optional, helps generate more accurate sub-questions)",
            },
        },
        "panorama_search": {
            "name": "panorama_search",
            "description": TOOL_DESC_PANORAMA_SEARCH,
            "parameters": {
                "query": "Search query, used for relevance sorting",
                "include_expired": "Whether to include expired/historical content (default True)",
            },
        },
        "quick_search": {
            "name": "quick_search",
            "description": TOOL_DESC_QUICK_SEARCH,
            "parameters": {
                "query": "Search query string",
                "limit": "Number of results to return (optional, default 10)",
            },
        },
        "interview_agents": {
            "name": "interview_agents",
            "description": TOOL_DESC_INTERVIEW_AGENTS,
            "parameters": {
                "interview_topic": "Interview topic or requirement description (e.g. 'understand students' views on the dorm formaldehyde incident')",
                "max_agents": "Maximum number of agents to interview (optional, default 5, max 10)",
            },
        },
    }

    # Ein terminal ausgefallenes Tool verschwindet aus dem Angebot. Der
    # Hinweistext im Tool-Ergebnis reichte nicht: er stand im Verlauf *einer*
    # Section und war beim nächsten Abschnitt aus dem Kontext gefallen,
    # während das Tool im Schema unverändert bereitstand (Referenzlauf
    # report_cc2ef45da5e9: acht Aufrufe, null Interviews).
    breaker = breaker_for(agent)
    for disabled in breaker.disabled_tools:
        tools.pop(disabled, None)

    if agent.web_tools.is_available():
        tools["web_search"] = {
            "name": "web_search",
            "description": (
                "Live web search via Tavily. Use for CURRENT, POST-SIMULATION facts "
                "(news, recent developments, statistics, official sources) that are NOT in the knowledge graph. "
                "Prefer this over guessing whenever the topic is time-sensitive or external."
            ),
            "parameters": {
                "query": "Search query in natural language (German or English)",
                "max_results": "Number of results (optional, default 5, max 10)",
            },
        }
        tools["fetch_url"] = {
            "name": "fetch_url",
            "description": (
                "Fetch the main text of a specific URL found via web_search (or one you already know). "
                "Returns cleaned article content. Use when a search snippet is insufficient."
            ),
            "parameters": {
                "url": "Absolute URL starting with http(s)://",
            },
        }
    return tools


def execute_tool_call(agent: Any, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
    breaker = breaker_for(agent)
    # Gezählt wird die Anforderung, nicht der Durchlauf: ein abgewiesener
    # Aufruf bezeugt genauso, dass der Bericht das Werkzeug vorsah.
    breaker.record_request(tool_name)
    if breaker.is_disabled(tool_name):
        # Zweite Verteidigungslinie hinter dem Schema-Filter. Das Modell kann
        # einen Tool-Namen auch dann nennen, wenn er nicht angeboten wurde —
        # im XML-Modus ist der Name freier Text.
        return (
            f"Tool '{tool_name}' ist für diesen Report-Lauf nicht verfügbar "
            f"({breaker.reason_for(tool_name)}). Der Aufruf wurde nicht "
            "ausgeführt. Nutze die verbleibenden Werkzeuge."
        )
    return execute_tool(
        tool_name=tool_name,
        parameters=parameters,
        report_context=report_context,
        graph_tools=agent.graph_tools,
        web_tools=agent.web_tools,
        graph_id=agent.graph_id,
        simulation_id=agent.simulation_id,
        simulation_requirement=agent.simulation_requirement,
        record_evidence=agent._record_tool_evidence,
        section_index=agent._current_section_index or 0,
        on_terminal_failure=breaker.trip,
    )


def parse_tool_calls_response(response: str) -> List[Dict[str, Any]]:
    return _parse_tool_calls(response)


def validate_tool_call(data: dict) -> bool:
    return _is_valid_tool_call(data)


# Exact-name re-exports for backwards compatibility and identity-sensitive tests.
parse_tool_calls = _parse_tool_calls
is_valid_tool_call = _is_valid_tool_call


def get_openai_tools_schema(agent: Any) -> List[Dict[str, Any]]:
    """Liefert die Tool-Definitionen im OpenAI function-calling Format.

    Wandelt die internen ``define_tools(agent)``-Einträge
    ``{name, description, parameters: {param_name: description, ...}}``
    in das OpenAI-Schema-Format um:
    ``[{"type": "function", "function": {"name", "description", "parameters": {...}}}]``.

    ``parameters`` wird als valides JSON-Schema aufgebaut. Typ- und
    Required-Heuristik basiert auf Parameter-Name und -Beschreibung:
    ``limit``/``max_*`` → ``integer``, ``include_expired`` → ``boolean``,
    Rest ``string``. Parameter mit ``optional`` in der Beschreibung sind
    nicht required.
    """
    tools = define_tools(agent)
    result: List[Dict[str, Any]] = []
    for tool_name, tool_def in tools.items():
        properties: Dict[str, Any] = {}
        required_params: List[str] = []
        for param_name, param_desc in tool_def.get("parameters", {}).items():
            desc_str = str(param_desc)
            p_type = "string"
            if param_name == "limit" or param_name.startswith("max_"):
                p_type = "integer"
            elif param_name == "include_expired":
                p_type = "boolean"
            properties[param_name] = {
                "type": p_type,
                "description": desc_str,
            }
            if "optional" not in desc_str.lower():
                required_params.append(param_name)
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_def.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_params,
                    },
                },
            }
        )
    return result


def describe_tools(tools: Dict[str, Dict[str, Any]]) -> str:
    desc_parts = ["Available Tools:"]
    for name, tool in tools.items():
        params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
        desc_parts.append(f"- {name}: {tool['description']}")
        if params_desc:
            desc_parts.append(f"  Parameters: {params_desc}")
    return "\n".join(desc_parts)


__all__ = [
    "define_tools",
    "describe_tools",
    "execute_tool_call",
    "get_openai_tools_schema",
    "parse_tool_calls",
    "parse_tool_calls_response",
    "is_valid_tool_call",
    "validate_tool_call",
]
