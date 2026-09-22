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


def test_shadow_mode_is_accepted():
    assert validate_decision_layer_mode("shadow") == []


def test_authoritative_is_a_recognized_but_not_yet_usable_value():
    """Review-Befund (Codex, PR #1547): kein verdrahteter Use Case hat einen
    authoritative-Handler. Vorher wurde der Wert klaglos akzeptiert, obwohl
    local_search_shadow.py bei jedem Wert außer 'shadow' sofort zurückkehrt
    — ein Start mit diesem Wert hätte den Betreiber glauben lassen, der
    Decision Layer sei aktiv, während er still inaktiv blieb."""
    errors = validate_decision_layer_mode("authoritative")

    assert len(errors) == 1
    assert "not usable yet" in errors[0]
    # Bleibt im Vokabular, nur (noch) nicht startbar.
    assert "authoritative" in DECISION_LAYER_MODES


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
