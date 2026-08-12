"""Regression fuer Gemini-3-Tool-Turns ueber CAMELs Compat-Historie."""

import sys
from pathlib import Path
from types import SimpleNamespace


_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def test_echoes_captured_signature_into_reconstructed_tool_call() -> None:
    from gemini_thought_signatures import echo_thought_signatures

    messages = [
        {"role": "user", "content": "Erstelle einen Beitrag"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "create_post", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "ok"},
    ]

    processed = echo_thought_signatures(
        messages,
        {"call-1": {"google": {"thought_signature": "signature-1"}}},
    )

    assert processed[1]["tool_calls"][0]["extra_content"] == {
        "google": {"thought_signature": "signature-1"}
    }
    assert "extra_content" not in messages[1]["tool_calls"][0]


def test_extracts_google_signature_from_openai_compat_response() -> None:
    from gemini_thought_signatures import extract_thought_signatures

    tool_call = SimpleNamespace(
        id="call-1",
        extra_content={"google": {"thought_signature": "signature-1"}},
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call]))]
    )

    assert extract_thought_signatures(response) == {
        "call-1": {"google": {"thought_signature": "signature-1"}}
    }


def test_uses_documented_validator_escape_only_without_captured_signature() -> None:
    from gemini_thought_signatures import (
        THOUGHT_SIGNATURE_VALIDATOR_ESCAPE,
        echo_thought_signatures,
    )

    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "synthetic-call",
                    "type": "function",
                    "function": {"name": "do_nothing", "arguments": "{}"},
                }
            ],
        }
    ]

    processed = echo_thought_signatures(messages, {})

    assert processed[0]["tool_calls"][0]["extra_content"] == {
        "google": {"thought_signature": THOUGHT_SIGNATURE_VALIDATOR_ESCAPE}
    }
