"""Issue #556 — Gemini-Outputs umrahmen JSON oft mit Codefences UND Prosa.

Der aktuelle Pre-Parser entfernt nur `^```(json)?` und `\\s*```$` an den
Rändern. Outputs mit Preamble ("Sure! Here you go:\\n...") oder trailing
prose ("...```\\nHope this helps!") fallen durch und produzieren
`JSONDecodeError: Expecting value: line 1 column 1`.

Dieses Modul testet den Helper `_strip_llm_json_envelope`, der Codefences
+ Prosa-Umrahmung entfernt und auf das outer JSON-Objekt/Array zuschneidet.
"""
from __future__ import annotations

import pytest

from app.utils.llm_client import _strip_llm_json_envelope


class TestStripLlmJsonEnvelope:
    """Helper soll Codefences + Prosa-Umrahmung entfernen, robust gegen
    typische LLM-Output-Patterns (Gemini, GPT, Ollama Cloud)."""

    # --- Happy Path -------------------------------------------------------

    def test_pure_json_object_untouched(self) -> None:
        assert _strip_llm_json_envelope('{"a": 1}') == '{"a": 1}'

    def test_pure_json_array_untouched(self) -> None:
        assert _strip_llm_json_envelope('[1, 2, 3]') == '[1, 2, 3]'

    def test_whitespace_around_object_trimmed(self) -> None:
        assert _strip_llm_json_envelope('  \n {"a": 1}  \n') == '{"a": 1}'

    # --- Codefences --------------------------------------------------------

    def test_codefence_json_label(self) -> None:
        raw = "```json\n{\"a\": 1}\n```"
        assert _strip_llm_json_envelope(raw) == '{"a": 1}'

    def test_codefence_uppercase_json_label(self) -> None:
        raw = "```JSON\n{\"a\": 1}\n```"
        assert _strip_llm_json_envelope(raw) == '{"a": 1}'

    def test_codefence_bare(self) -> None:
        raw = "```\n{\"a\": 1}\n```"
        assert _strip_llm_json_envelope(raw) == '{"a": 1}'

    # --- Preamble (was den existierenden Pre-Parser killt) ----------------

    def test_preamble_before_object(self) -> None:
        raw = "Sure! Here is the JSON you requested:\n\n{\"a\": 1}"
        assert _strip_llm_json_envelope(raw) == '{"a": 1}'

    def test_preamble_and_codefence(self) -> None:
        raw = "Here is the JSON response:\n```json\n{\"a\": 1}\n```"
        assert _strip_llm_json_envelope(raw) == '{"a": 1}'

    # --- Trailing prose ---------------------------------------------------

    def test_trailing_prose_after_object(self) -> None:
        raw = '{"a": 1}\n\nHope this helps!'
        assert _strip_llm_json_envelope(raw) == '{"a": 1}'

    def test_codefence_and_trailing_prose(self) -> None:
        raw = "```json\n{\"a\": 1}\n```\n\nHope this helps!"
        assert _strip_llm_json_envelope(raw) == '{"a": 1}'

    # --- Reale Gemini-Patterns --------------------------------------------

    def test_gemini_style_preamble_and_trailing(self) -> None:
        raw = (
            "Of course. Based on the persona profile, here is the structured "
            "response in JSON format:\n\n"
            "```json\n"
            '{"persona_id": "p1", "score": 0.87}\n'
            "```\n\n"
            "Let me know if you need anything else."
        )
        assert _strip_llm_json_envelope(raw) == '{"persona_id": "p1", "score": 0.87}'

    def test_nested_braces_in_string_values(self) -> None:
        """Outer-Object-Schnitt darf nicht auf `}` in Strings reagieren."""
        raw = 'Sure: {"msg": "use {x} as template", "ok": true} done.'
        assert _strip_llm_json_envelope(raw) == '{"msg": "use {x} as template", "ok": true}'

    def test_array_with_prose(self) -> None:
        raw = "Here are the entities:\n```\n[1, 2, 3]\n```"
        assert _strip_llm_json_envelope(raw) == '[1, 2, 3]'

    # --- Edge cases --------------------------------------------------------

    def test_empty_string_returns_empty(self) -> None:
        assert _strip_llm_json_envelope("") == ""

    def test_only_prose_no_json_returns_original(self) -> None:
        raw = "I cannot answer this question."
        assert _strip_llm_json_envelope(raw) == raw

    def test_object_before_array_picks_first_bracket(self) -> None:
        """Wenn beide Brackets vorkommen, gewinnt der erste auftretende.
        Hier `{` zuerst → outer object."""
        raw = '{"items": [1,2,3], "ok": true}'
        assert _strip_llm_json_envelope(raw) == '{"items": [1,2,3], "ok": true}'

    def test_unbalanced_braces_no_match_returns_original(self) -> None:
        """Wenn kein passendes schließendes Bracket existiert, original
        zurück (Caller löst dann JSONDecodeError aus, was er sowieso täte)."""
        raw = "broken: {a: 1"
        # outer-cut darf nicht crashen; Verhalten: original-string
        # (kein Truncate auf Halbsatz, der dem Parser noch mehr Schaden täte)
        result = _strip_llm_json_envelope(raw)
        assert "{a: 1" in result

    def test_whitespace_only_returns_empty_or_whitespace(self) -> None:
        result = _strip_llm_json_envelope("   \n  ")
        assert result.strip() == ""


@pytest.mark.parametrize("payload", [
    '{"a": 1}',
    '[1, 2, 3]',
    '{"nested": {"deep": {"value": 42}}}',
    '{"unicode": "ümlaut äöü", "emoji": "✓"}',
])
def test_strip_envelope_is_idempotent(payload: str) -> None:
    """Doppelte Anwendung verändert das Ergebnis nicht."""
    once = _strip_llm_json_envelope(payload)
    twice = _strip_llm_json_envelope(once)
    assert once == twice
