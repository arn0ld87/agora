"""Regression: ``_fix_truncated_json`` schliesst verschachtelte Container korrekt.

Root Cause: offene ``{}``/``[]`` wurden lediglich *gezaehlt* — inklusive der
Vorkommen innerhalb von String-Literalen — und danach pauschal erst alle ``]``
und dann alle ``}`` angehaengt. Container muessen aber in umgekehrter
Oeffnungsreihenfolge geschlossen werden: ``{"initial_posts":[{"content":"x``
braucht ``"`` ``}`` ``]`` ``}``, nicht ``"`` ``]`` ``}``.
"""

from __future__ import annotations

import json

import pytest

from app.services.simulation_config_llm import _fix_truncated_json


def _repair(raw: str) -> str:
    # ``self`` wird von der Funktion nicht benutzt (reine Textreparatur).
    return _fix_truncated_json(None, raw)


def _repair_and_parse(raw: str):
    return json.loads(_repair(raw))


class TestNestingOrder:
    def test_nested_object_inside_array(self) -> None:
        parsed = _repair_and_parse('{"initial_posts":[{"content":"x')

        assert parsed == {"initial_posts": [{"content": "x"}]}

    def test_array_inside_object(self) -> None:
        parsed = _repair_and_parse('{"topics":["a","b"')

        assert parsed == {"topics": ["a", "b"]}

    def test_object_inside_array_inside_object_inside_array(self) -> None:
        parsed = _repair_and_parse('[{"a":[{"b":[1,2')

        assert parsed == [{"a": [{"b": [1, 2]}]}]

    def test_deeply_mixed_nesting(self) -> None:
        parsed = _repair_and_parse('{"a":{"b":[{"c":["d"')

        assert parsed == {"a": {"b": [{"c": ["d"]}]}}


class TestStringAwareness:
    def test_braces_inside_strings_are_not_counted(self) -> None:
        parsed = _repair_and_parse('{"note":"ein } und ein ] im Text"')

        assert parsed == {"note": "ein } und ein ] im Text"}

    def test_escaped_quote_does_not_end_the_string(self) -> None:
        parsed = _repair_and_parse('{"quote":"sie sagte \\"nein\\" dazu')

        assert parsed == {"quote": 'sie sagte "nein" dazu'}

    def test_escaped_backslash_before_closing_quote(self) -> None:
        parsed = _repair_and_parse('{"path":"C:\\\\temp\\\\"}')

        assert parsed == {"path": "C:\\temp\\"}

    def test_dangling_escape_is_dropped_instead_of_escaping_the_repair(self) -> None:
        parsed = _repair_and_parse('{"text":"abc\\')

        assert parsed == {"text": "abc"}

    def test_truncated_string_is_closed(self) -> None:
        parsed = _repair_and_parse('{"content":"Die Elternschaft reagiert')

        assert parsed == {"content": "Die Elternschaft reagiert"}


class TestNonStringValues:
    def test_truncated_number_is_not_turned_into_a_string(self) -> None:
        parsed = _repair_and_parse('{"agents": 12')

        assert parsed == {"agents": 12}

    def test_trailing_comma_before_the_repair_is_removed(self) -> None:
        parsed = _repair_and_parse('{"topics":["a","b",')

        assert parsed == {"topics": ["a", "b"]}


class TestIdempotenceOnValidInput:
    @pytest.mark.parametrize(
        "payload",
        [
            '{"a": 1}',
            '{"a": [1, 2, 3], "b": {"c": "d"}}',
            '[]',
            '{}',
            '{"s": "he said \\"hi\\""}',
            '{"s": "braces { } and brackets [ ]"}',
        ],
    )
    def test_valid_json_is_returned_unchanged(self, payload: str) -> None:
        assert _repair(payload) == payload
        assert json.loads(_repair(payload)) == json.loads(payload)

    def test_empty_input_stays_empty(self) -> None:
        assert _repair("") == ""
        assert _repair("   ") == ""
