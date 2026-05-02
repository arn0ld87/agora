"""Glossar-Verteidigungs-Tests (Wording-Glossar v1, Issue #175).

Pinnt die Wording-Bereinigung in `backend/app/services/report_prompts.py`
und `backend/app/services/graph_tools.py`. Verstösse machen die ganze
Slice rückgängig — daher rote Tests, sobald jemand „prediction"-/
„rehearsal"-/„god's eye"-Vokabular ins Prompt-Layer wieder einbaut.

Geltungsbereich (siehe `docu/glossary-wording.md`):
- alles im Modul `report_prompts` (System-/User-/ReACT-/Chat-Prompts)
- die in den Report exportierten Header in `graph_tools.InsightForgeResult.to_text`
"""

from __future__ import annotations

import re

import pytest

from app.services import graph_tools, report_prompts

# Verbotene Token gemäss Glossar v1. Case-insensitive geprüft.
# „simulation_requirement" und „prediction" als Substring-Match wären zu
# scharf (Variablennamen sind erlaubt) — wir prüfen Wortgrenzen.
FORBIDDEN_PATTERNS = [
    r"\bfuture prediction\b",
    r"\bprediction scenario\b",
    r"\bprediction results?\b",
    r"\bprediction findings?\b",
    r"\bprediction data\b",
    r"\bprediction facts?\b",
    r"\bprediction condition\b",
    r"\bprediction assistant\b",
    r"\bsimulation predictions?\b",
    r"\bpredictions of future\b",
    r"\brehears(?:al|e|ing)\b",
    r"\bgod['’]s eye\b",
    r"\bhigh[- ]fidelity digital world\b",
    r"\bpublic opinion prediction\b",
    r"\bagentic[- ]prediction[- ]engine\b",
]

PROMPT_CONSTANTS = [
    name for name in report_prompts.__all__
    if isinstance(getattr(report_prompts, name), str)
]


@pytest.mark.parametrize("name", PROMPT_CONSTANTS)
@pytest.mark.parametrize("pattern", FORBIDDEN_PATTERNS)
def test_prompt_constant_avoids_forbidden_wording(name: str, pattern: str) -> None:
    value = getattr(report_prompts, name)
    matches = re.findall(pattern, value, flags=re.IGNORECASE)
    assert not matches, (
        f"{name} enthält verbotenes Wording {pattern!r} "
        f"(siehe docu/glossary-wording.md, Issue #175): {matches}"
    )


@pytest.mark.parametrize("pattern", FORBIDDEN_PATTERNS)
def test_insight_forge_result_text_avoids_forbidden_wording(pattern: str) -> None:
    result = graph_tools.InsightForgeResult(
        query="Q",
        simulation_requirement="R",
        sub_queries=[],
        semantic_facts=["fact-1"],
        entity_insights=[],
        relationship_chains=[],
        total_facts=1,
        total_entities=0,
        total_relationships=0,
    )
    text = result.to_text()
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    assert not matches, (
        f"InsightForgeResult.to_text() enthält verbotenes Wording {pattern!r} "
        f"(siehe docu/glossary-wording.md, Issue #175): {matches}"
    )


# Service-Module mit Report-Strings, die in den Output bzw. in Reports
# wandern. Dateien werden als Text gelesen — die Tests pinnen also auch
# String-Literale ausserhalb von Modul-Konstanten.
SERVICE_FILES = [
    "backend/app/services/report_agent.py",
    "backend/app/services/ontology_generator.py",
]


@pytest.mark.parametrize("rel_path", SERVICE_FILES)
@pytest.mark.parametrize("pattern", FORBIDDEN_PATTERNS)
def test_service_file_source_avoids_forbidden_wording(
    rel_path: str, pattern: str
) -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / rel_path).read_text(encoding="utf-8")
    matches = re.findall(pattern, source, flags=re.IGNORECASE)
    assert not matches, (
        f"{rel_path} enthält verbotenes Wording {pattern!r} "
        f"(siehe docu/glossary-wording.md, Issue #175): {matches}"
    )
