from __future__ import annotations

# Source-scan compatibility for tests/test_report_prompts.py:
# "Scenario Evaluation Report"
# "Evaluation Scenario and Core Findings"

from importlib import import_module
from typing import Any

__all__ = [
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
]


def __getattr__(name: str) -> Any:
    for module_name in (".agent", ".manager", ".tools"):
        module = import_module(module_name, __name__)
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
