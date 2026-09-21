"""Config-Vertrag für AGORA_DECISION_LAYER_MODE (f005, ADR-0016).

Der Kern ist derselbe wie bei den Backend-Schaltern: der Default
('disabled') darf am bestehenden Verhalten nichts ändern, und ein
Tippfehler darf nicht still auf den Default zurückfallen.
"""

from __future__ import annotations

from app.config import DECISION_LAYER_MODES, Config, validate_decision_layer_mode


def test_decision_layer_modes_are_exactly_three():
    assert DECISION_LAYER_MODES == frozenset({"disabled", "shadow", "authoritative"})


def test_default_mode_is_disabled():
    assert Config.DECISION_LAYER_MODE == "disabled"


def test_disabled_mode_is_accepted():
    assert validate_decision_layer_mode("disabled") == []


def test_shadow_and_authoritative_modes_are_accepted():
    assert validate_decision_layer_mode("shadow") == []
    assert validate_decision_layer_mode("authoritative") == []


def test_unknown_mode_is_rejected():
    """Ein Tippfehler darf nicht still auf 'disabled' zurückfallen — sonst
    glaubt der Betreiber, den Piloten aktiviert zu haben, während nichts
    passiert."""
    errors = validate_decision_layer_mode("shaddow")

    assert len(errors) == 1
    assert "unknown value" in errors[0]
    for mode in DECISION_LAYER_MODES:
        assert mode in errors[0]


def test_case_and_whitespace_are_normalized():
    assert validate_decision_layer_mode("  SHADOW  ") == []
