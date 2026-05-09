from __future__ import annotations

# Source-scan compatibility for tests/test_report_prompts.py:
# "Scenario Evaluation Report"
# "Evaluation Scenario and Core Findings"

from importlib import import_module
from typing import Any

from .contract_constants import MIN_PERSONA_TABLE_ROWS

__all__ = [
    "MIN_PERSONA_TABLE_ROWS",
    "FORBIDDEN_EVIDENCE_TYPES",
    "VALID_TOOL_NAMES",
    "EvidenceItem",
    "Report",
    "ReportAgent",
    "ReportClaim",
    "ReportManager",
    "ReportOutline",
    "ReportSection",
    "ReportStatus",
    "is_valid_tool_call",
    "parse_tool_calls",
    # Prompt templates (re-exported from .prompts)
    "PLAN_SYSTEM_PROMPT_TEMPLATE",
    "PLAN_USER_PROMPT_TEMPLATE",
    "SECTION_SYSTEM_PROMPT_TEMPLATE",
    "SECTION_USER_PROMPT_TEMPLATE",
    "REACT_OBSERVATION_TEMPLATE",
    "REACT_INSUFFICIENT_TOOLS_MSG",
    "REACT_INSUFFICIENT_TOOLS_MSG_ALT",
    "REACT_TOOL_LIMIT_MSG",
    "REACT_UNUSED_TOOLS_HINT",
    "REACT_FORCE_FINAL_MSG",
    "CHAT_SYSTEM_PROMPT_TEMPLATE",
    "CHAT_OBSERVATION_SUFFIX",
]


def __getattr__(name: str) -> Any:
    for module_name in (".agent", ".manager", ".prompts", ".tools"):
        module = import_module(module_name, __name__)
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
