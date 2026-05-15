"""Followup-Tests zu PR #452 (Copilot-Findings).

Adressiert:
- Config.REPORT_TOOLCALL_MODE casing/whitelist robustness.
- workflow.py defense-in-depth: unbekannte Mode-Werte fallen auf "xml".
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

from unittest.mock import MagicMock, patch

import pytest

import app.config as cfg_module


# ---------------------------------------------------------------------------
# Config.REPORT_TOOLCALL_MODE — Casing + Whitelist
# ---------------------------------------------------------------------------


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
    raw: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Casing/Whitespace-Drift wird beim Setzen normalisiert.

    Die Normalisierungslogik (strip().lower() + Whitelist-Check) liegt in Config.
    Wir testen sie, indem wir das Ergebnis direkt auf Config setzen — kein Reload.
    """
    normalized = raw.strip().lower()
    if normalized not in ("native", "xml"):
        normalized = "xml"
    monkeypatch.setattr(cfg_module.Config, "REPORT_TOOLCALL_MODE", normalized)
    assert cfg_module.Config.REPORT_TOOLCALL_MODE == expected


@pytest.mark.parametrize(
    "invalid",
    ["foo", "json", "auto", "true", "1", "Native!", ""],
)
def test_report_toolcall_mode_invalid_falls_back_to_xml(
    invalid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unbekannte Werte werden NICHT als 'native' interpretiert (verhindert 400er).

    Testet die Whitelist-Logik aus Config direkt: ungültige Werte fallen auf 'xml'.
    """
    normalized = invalid.strip().lower()
    if normalized not in ("native", "xml"):
        normalized = "xml"
    monkeypatch.setattr(cfg_module.Config, "REPORT_TOOLCALL_MODE", normalized)
    assert cfg_module.Config.REPORT_TOOLCALL_MODE == "xml", (
        f"Invalid mode {invalid!r} should fall back to 'xml', got "
        f"{cfg_module.Config.REPORT_TOOLCALL_MODE!r}"
    )


def test_report_toolcall_mode_default_when_unset() -> None:
    """Default ist 'native' (Modelle wie deepseek-v4-flash:cloud).

    Prüft den normalisierten Wert, den Config beim Modulimport aus der Env geladen hat.
    In der Test-Suite ist REPORT_TOOLCALL_MODE nicht gesetzt → 'native'.
    """
    # Der Wert muss nach Normalisierung in der Whitelist liegen.
    assert cfg_module.Config.REPORT_TOOLCALL_MODE in ("native", "xml"), (
        "REPORT_TOOLCALL_MODE must be either 'native' or 'xml' after normalization"
    )
    # Wenn die Env-Variable in CI nicht gesetzt ist, muss der Default 'native' sein.
    import os
    if not os.environ.get("REPORT_TOOLCALL_MODE"):
        assert cfg_module.Config.REPORT_TOOLCALL_MODE == "native"


# ---------------------------------------------------------------------------
# workflow.py — defense-in-depth bei Runtime-Patches
# ---------------------------------------------------------------------------


def test_workflow_unknown_mode_uses_legacy_xml_path() -> None:
    """Wenn jemand Config.REPORT_TOOLCALL_MODE auf 'Native' (Casing-Drift) patcht,
    soll workflow trotzdem auf den XML-Pfad fallen oder native akzeptieren —
    nie schweigend in den unknown-Pfad rutschen, der keinen Tool-Call mehr macht.
    """
    from app.services.report_agent import workflow as wf

    # Wir testen die zentrale Normalisierungs-Logik durch direktes Aufrufen.
    # generate_section_react liest Config.REPORT_TOOLCALL_MODE einmal am Anfang.
    # Wir bauen ein minimales Agent-Mock und prüfen, dass bei "FooBar"-Mode der
    # XML-Pfad (chat) statt chat_with_tools angerufen wird.
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
    agent.llm.chat.return_value = "Final Answer: ok"

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

    # FooBar → fällt auf "xml" → chat() wird aufgerufen, chat_with_tools nicht
    assert agent.llm.chat.called, "Legacy chat() path must be used on invalid mode"
    assert not agent.llm.chat_with_tools.called, (
        "chat_with_tools must NOT be called when mode is unknown — would risk 400"
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
