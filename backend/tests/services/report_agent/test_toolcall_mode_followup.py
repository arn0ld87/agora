"""Followup-Tests zu PR #452 (Copilot-Findings).

Adressiert:
- Config.REPORT_TOOLCALL_MODE casing/whitelist robustness.
- workflow.py defense-in-depth: unbekannte Mode-Werte fallen auf den
  Default "native" (siehe changelog.d/toolcall-mode-fallback-native.md).
- LLMClient.chat_with_tools provider=unknown short-circuit (kein 400, leerer
  tool_calls-Return → Caller nutzt XML-Fallback).

Fix (PR #455): importlib.reload(app.config) entfernt. Es erzeugte eine neue
Config-Klasse im Modul-Cache, während andere Module (z.B. app.api.simulation_run)
noch den alten Class-Pin per 'from ..config import Config' hielten. Das führte
dazu, dass monkeypatch-Writes auf die neue Klasse gingen, aber
_evaluate_persona_review_gate die alte Klasse las → gate passierte → 400 statt
409. Fix: monkeypatch.setattr direkt auf dem importierten Config-Objekt;
kein Reload nötig, da REPORT_TOOLCALL_MODE nachträglich überschrieben werden kann.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Config.REPORT_TOOLCALL_MODE — Casing + Whitelist
# ---------------------------------------------------------------------------


def _config_mode_for_env(value: str | None) -> str:
    """Liest Config.REPORT_TOOLCALL_MODE in einem frischen Interpreter aus.

    Config normalisiert beim Modulimport auf Klassenebene. Ein monkeypatch auf
    das bereits importierte Config-Objekt wuerde die Normalisierung ueberspringen
    und damit nur die Testlogik pruefen, nicht den Produktionscode (genau das
    taten die Vorgaengertests hier). Ein Subprozess mit gesetzter Env ist der
    einzige Weg, die Normalisierung echt auszufuehren — ohne importlib.reload,
    dessen Modul-Cache-Fallstricke der Modul-Docstring beschreibt.
    """
    env = dict(os.environ)
    env.pop("REPORT_TOOLCALL_MODE", None)
    if value is not None:
        env["REPORT_TOOLCALL_MODE"] = value
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import Config; print(Config.REPORT_TOOLCALL_MODE)",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(pathlib.Path(__file__).resolve().parents[2]),
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("native", "native"),
        ("xml", "xml"),
        ("NATIVE", "native"),
        ("Xml", "xml"),
        ("  native  ", "native"),
        (" XML\n", "xml"),
    ],
)
def test_report_toolcall_mode_normalizes_casing_and_whitespace(
    raw: str, expected: str
) -> None:
    """Casing/Whitespace-Drift wird von Config selbst normalisiert."""
    assert _config_mode_for_env(raw) == expected


@pytest.mark.parametrize(
    "invalid",
    ["foo", "json", "auto", "true", "1", "Native!", ""],
)
def test_report_toolcall_mode_invalid_falls_back_to_default_native(
    invalid: str,
) -> None:
    """Ungueltige Werte fallen auf den Default 'native', nicht auf 'xml'.

    Ein Tippfehler ist ein Konfigurationsfehler und soll sich verhalten wie
    "nicht konfiguriert". Der fruehere xml-Fallback gab ausgerechnet dem
    Vertipper ein anderes Verhalten als dem Nicht-Konfigurierer.
    """
    assert _config_mode_for_env(invalid) == "native"


def test_invalid_fallback_equals_unset_default() -> None:
    """Invariante: Fallback bei Fehlwert == Verhalten ohne gesetzte Variable.

    Diese Gleichheit ist der eigentliche Vertrag. Faellt einer der beiden Pfade
    kuenftig auseinander, ist das eine bewusste Entscheidung und muss hier
    sichtbar brechen.
    """
    assert _config_mode_for_env("voellig-ungueltig") == _config_mode_for_env(None)


# ---------------------------------------------------------------------------
# workflow.py — defense-in-depth bei Runtime-Patches
# ---------------------------------------------------------------------------


def test_workflow_unknown_mode_uses_default_native_path() -> None:
    """Ein ungueltiger Runtime-Wert faellt in workflow.py auf den Default 'native'.

    Frueher fiel er hier auf 'xml' — damit landete ein Fehlwert in einem anderen
    Modus als der Nicht-gesetzt-Fall, der ueber den Config-Default 'native' laeuft.
    Entscheidend bleibt, dass er nie in den unknown-Pfad rutscht, der gar keinen
    Tool-Call mehr macht.
    """
    from app.services.report_agent import workflow as wf

    # Wir testen die zentrale Normalisierungs-Logik durch direktes Aufrufen.
    # generate_section_react liest Config.REPORT_TOOLCALL_MODE einmal am Anfang.
    # Wir bauen ein minimales Agent-Mock und prüfen, dass bei "FooBar"-Mode der
    # native Pfad (chat_with_tools) statt des XML-Pfads angerufen wird.
    agent = MagicMock()
    agent.simulation_requirement = "test"
    agent.MAX_TOOL_CALLS_PER_SECTION = 3
    agent.REACT_INSUFFICIENT_TOOLS_MSG = "more tools {tool_calls_count}/{min_tool_calls}{unused_hint}"
    agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT = "alt {tool_calls_count}/{min_tool_calls}{unused_hint}"
    agent.REACT_TOOL_LIMIT_MSG = "limit {tool_calls_count}/{max_tool_calls}"
    agent.REACT_OBSERVATION_TEMPLATE = "obs {tool_name}{result}{tool_calls_count}{max_tool_calls}{used_tools_str}{unused_hint}"
    agent.REACT_UNUSED_TOOLS_HINT = " unused: {unused_list}"
    agent.REACT_FORCE_FINAL_MSG = "force final"
    agent._get_react_messages.return_value = [{"role": "system", "content": "sys"}]
    agent._parse_tool_calls.return_value = []
    agent.report_logger = None
    agent._current_section_index = None
    agent._get_openai_tools_schema.return_value = []
    agent.llm.chat_with_tools.return_value = {
        "content": "Final Answer: ok",
        "tool_calls": [],
        "finish_reason": "stop",
        "raw_response": None,
    }

    section = MagicMock()
    section.title = "T"
    outline = MagicMock()
    outline.title = "O"
    outline.summary = "S"

    with patch("app.services.report_agent.workflow.Config") as mock_cfg:
        mock_cfg.REPORT_TOOLCALL_MODE = "FooBar"  # ungültiger Wert
        mock_cfg.REPORT_LANGUAGE = "German"
        wf.generate_section_react(
            agent=agent,
            section=section,
            outline=outline,
            previous_sections=[],
            section_index=0,
        )

    # FooBar → fällt auf "native" → chat_with_tools wird aufgerufen, chat() nicht
    assert agent.llm.chat_with_tools.called, (
        "Invalid mode must fall back to the default native path"
    )
    assert not agent.llm.chat.called, (
        "Legacy XML chat() path must only run when xml is chosen deliberately"
    )


def test_workflow_native_mode_case_insensitive() -> None:
    """'NATIVE' (Casing-Drift) wird wie 'native' behandelt."""
    from app.services.report_agent import workflow as wf

    agent = MagicMock()
    agent.simulation_requirement = "test"
    agent.MAX_TOOL_CALLS_PER_SECTION = 3
    agent.REACT_INSUFFICIENT_TOOLS_MSG = "{tool_calls_count}{min_tool_calls}{unused_hint}"
    agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT = "{tool_calls_count}{min_tool_calls}{unused_hint}"
    agent.REACT_TOOL_LIMIT_MSG = "{tool_calls_count}{max_tool_calls}"
    agent.REACT_OBSERVATION_TEMPLATE = "{tool_name}{result}{tool_calls_count}{max_tool_calls}{used_tools_str}{unused_hint}"
    agent.REACT_UNUSED_TOOLS_HINT = "{unused_list}"
    agent.REACT_FORCE_FINAL_MSG = "force"
    agent._get_react_messages.return_value = [{"role": "system", "content": "sys"}]
    agent._parse_tool_calls.return_value = []
    agent.report_logger = None
    agent._current_section_index = None
    agent._get_openai_tools_schema.return_value = []
    agent.llm.chat_with_tools.return_value = {
        "content": "Final Answer: native ok",
        "tool_calls": [],
        "finish_reason": "stop",
        "raw_response": None,
    }

    section = MagicMock()
    section.title = "T"
    outline = MagicMock()
    outline.title = "O"
    outline.summary = "S"

    with patch("app.services.report_agent.workflow.Config") as mock_cfg:
        mock_cfg.REPORT_TOOLCALL_MODE = "NATIVE"  # uppercase
        mock_cfg.REPORT_LANGUAGE = "German"
        wf.generate_section_react(
            agent=agent,
            section=section,
            outline=outline,
            previous_sections=[],
            section_index=0,
        )

    assert agent.llm.chat_with_tools.called, "NATIVE casing must route to native path"


# ---------------------------------------------------------------------------
# llm_client.chat_with_tools — provider=unknown short-circuit
# ---------------------------------------------------------------------------


def test_chat_with_tools_provider_unknown_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bei unbekanntem Provider wird kein tools=-Request abgesetzt; stattdessen
    fällt der Client auf chat() zurück und liefert tool_calls=[] — der Caller
    soll dann den XML-Parser nutzen können.
    """
    # Stelle sicher, dass der E2E-Stub-Pfad nicht greift
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

    from app.utils.llm_client import LLMClient

    # base_url ohne 11434/openai.com → provider = "unknown"
    client = LLMClient(
        model="weird-private-model",
        api_key="test-key",
        base_url="https://example.invalid/v1",
    )
    # Provider muss als "unknown" detektiert werden
    assert client._detect_provider() == "unknown"

    # chat() wird gemockt, damit kein echter HTTP-Call passiert
    with patch.object(
        client, "chat", return_value="Some textual response without tool calls"
    ) as mocked_chat:
        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "noop", "description": "noop", "parameters": {}},
                }
            ],
            tool_choice="auto",
            temperature=0.5,
            max_tokens=128,
            context="report",
        )

    # chat() muss aufgerufen worden sein, NICHT der eigentliche tools=-Pfad
    assert mocked_chat.called, "chat() fallback must be invoked for unknown provider"
    assert result["tool_calls"] == [], "tool_calls must be empty for unknown provider"
    assert result["content"] == "Some textual response without tool calls"
    assert result["finish_reason"] == "stop"


def test_chat_with_tools_provider_unknown_handles_none_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wenn chat() None liefert, gibt der Short-Circuit content='' zurück
    (kein TypeError, kein crash)."""
    monkeypatch.delenv("AGORA_E2E_LLM_MODE", raising=False)

    from app.utils.llm_client import LLMClient

    client = LLMClient(
        model="weird-private-model",
        api_key="test-key",
        base_url="https://example.invalid/v1",
    )
    assert client._detect_provider() == "unknown"

    with patch.object(client, "chat", return_value=None):
        result = client.chat_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            tool_choice="auto",
            temperature=0.5,
            max_tokens=128,
            context="report",
        )

    assert result["content"] == ""
    assert result["tool_calls"] == []
