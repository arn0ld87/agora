"""Smoke-Tests für services/tool_schema.py (Issue #47, EPIC-07-ST-03).

Sichern, dass die vier Tool-Beschreibungs-Konstanten existieren, nicht-leer
sind und vom Re-Export in ``services/report_agent`` weiterhin als identische
Objekte erreichbar bleiben (Wire-Identity zum Schutz aller Aufrufstellen).
"""

from app.services import tool_schema
from app.services import report_agent


TOOL_DESC_NAMES = [
    "TOOL_DESC_INSIGHT_FORGE",
    "TOOL_DESC_PANORAMA_SEARCH",
    "TOOL_DESC_QUICK_SEARCH",
    "TOOL_DESC_INTERVIEW_AGENTS",
]


def test_tool_schema_exports_all_four_descriptions():
    assert set(tool_schema.__all__) == set(TOOL_DESC_NAMES)


def test_tool_descriptions_are_non_empty_strings():
    for name in TOOL_DESC_NAMES:
        value = getattr(tool_schema, name)
        assert isinstance(value, str), f"{name} muss str sein"
        assert value.strip(), f"{name} darf nicht leer/whitespace-only sein"


def test_report_agent_re_exports_identity():
    """Re-Export muss DASSELBE Objekt liefern, nicht eine Kopie."""
    for name in TOOL_DESC_NAMES:
        assert getattr(report_agent, name) is getattr(tool_schema, name), (
            f"{name} im report_agent ist nicht identisch mit der Quelle in tool_schema"
        )


def test_descriptions_carry_use_cases_and_return_content_sections():
    """Alle vier Tool-Beschreibungen haben Use-Cases- und Return-Content-Bereiche.

    Pinnt die Schema-Form gegen versehentliche Verkürzung in künftigen Slices.
    """
    for name in TOOL_DESC_NAMES:
        value = getattr(tool_schema, name)
        assert "[Use Cases]" in value, f"{name} fehlt [Use Cases]-Sektion"
        assert "[Return Content]" in value, f"{name} fehlt [Return Content]-Sektion"
