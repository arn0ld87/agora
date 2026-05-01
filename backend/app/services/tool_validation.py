"""
Tool-Call-Parsing und -Validierung für den Report-Agent.

Issue #47 (EPIC-07-ST-03), Sub-Slice 2/3: Validation aus
``services/report_agent.py`` herausziehen, sodass das Parsing von
LLM-Antworten in Tool-Call-Strukturen unabhängig von der Execution-Logik
unit-getestet werden kann.

Die Funktionen sind bewusst statelos (keine ``self``-Bindung); der
``ReportAgent`` delegiert auf diese reinen Helfer und re-exportiert sie
für Stabilität bestehender Aufrufstellen.
"""

import json
import re
from typing import Any, Dict, FrozenSet, List


VALID_TOOL_NAMES: FrozenSet[str] = frozenset({
    "insight_forge",
    "panorama_search",
    "quick_search",
    "interview_agents",
})


_XML_PATTERN = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_TAIL_JSON_PATTERN = re.compile(r'(\{"(?:name|tool)"\s*:.*?\})\s*$', re.DOTALL)


def is_valid_tool_call(
    data: Dict[str, Any],
    valid_tool_names: FrozenSet[str] = VALID_TOOL_NAMES,
) -> bool:
    """Prüft, ob ``data`` ein gültiger Tool-Call ist, und normalisiert Key-Aliasse.

    Akzeptiert sowohl ``{"name": …, "parameters": …}`` als auch
    ``{"tool": …, "params": …}``. Im Erfolgsfall wird ``data`` *in-place*
    auf die kanonischen Keys umgeschrieben — dieses Verhalten ist Teil
    des Vertrags und wird von Aufrufern erwartet.
    """
    tool_name = data.get("name") or data.get("tool")
    if tool_name and tool_name in valid_tool_names:
        if "tool" in data:
            data["name"] = data.pop("tool")
        if "params" in data and "parameters" not in data:
            data["parameters"] = data.pop("params")
        return True
    return False


def parse_tool_calls(
    response: str,
    valid_tool_names: FrozenSet[str] = VALID_TOOL_NAMES,
) -> List[Dict[str, Any]]:
    """Extrahiert Tool-Calls aus einer LLM-Antwort.

    Unterstützte Formate (in Prioritätsreihenfolge):

    1. ``<tool_call>{"name": "…", "parameters": {…}}</tool_call>`` — Standardform.
       Mehrere Tags pro Antwort werden alle zurückgegeben. Bei Treffern wird
       *nicht* mehr in den Fallbacks gesucht (Body-Text könnte JSON enthalten,
       das wir nicht versehentlich als Tool-Call interpretieren wollen).
    2. Roh-JSON: die gesamte Antwort ist ein einziges JSON-Objekt.
    3. Trailing-JSON: nach Thinking-Text steht am Ende ein
       ``{"name": …, …}``- oder ``{"tool": …, …}``-Objekt.

    Bei Fallback 2 + 3 muss der Tool-Name in ``valid_tool_names`` liegen,
    sonst wird das Objekt verworfen.
    """
    tool_calls: List[Dict[str, Any]] = []

    for match in _XML_PATTERN.finditer(response):
        try:
            tool_calls.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass

    if tool_calls:
        return tool_calls

    stripped = response.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            call_data = json.loads(stripped)
            if is_valid_tool_call(call_data, valid_tool_names):
                tool_calls.append(call_data)
                return tool_calls
        except json.JSONDecodeError:
            pass

    tail_match = _TAIL_JSON_PATTERN.search(stripped)
    if tail_match:
        try:
            call_data = json.loads(tail_match.group(1))
            if is_valid_tool_call(call_data, valid_tool_names):
                tool_calls.append(call_data)
        except json.JSONDecodeError:
            pass

    return tool_calls


__all__ = [
    "VALID_TOOL_NAMES",
    "is_valid_tool_call",
    "parse_tool_calls",
]
