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


def test_authoritative_mode_is_accepted():
    """f005, Task `resolve-fn`: `local_search_relevance.py::resolve_relevance`
    hat inzwischen einen authoritative-Handler (Jev, Rule-Rückfall) für den
    einzigen verdrahteten Use Case — der vormalige Ablehnungsgrund (Codex,
    PR #1547: erkannter, aber unbenutzter Wert) gilt nicht mehr."""
    assert validate_decision_layer_mode("authoritative") == []
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


def test_jev_timeout_defaults_to_two_seconds():
    assert Config.JEV_TIMEOUT_S == 2.0


def test_jev_timeout_accepts_the_valid_range(monkeypatch):
    monkeypatch.setattr(Config, "JEV_TIMEOUT_S", 0.1)
    assert not any("AGORA_JEV_TIMEOUT_S" in error for error in Config.validate())

    monkeypatch.setattr(Config, "JEV_TIMEOUT_S", 30.0)
    assert not any("AGORA_JEV_TIMEOUT_S" in error for error in Config.validate())


def test_jev_timeout_rejects_zero_and_negative(monkeypatch):
    monkeypatch.setattr(Config, "JEV_TIMEOUT_S", 0.0)
    errors = Config.validate()
    assert any("AGORA_JEV_TIMEOUT_S" in error for error in errors)

    monkeypatch.setattr(Config, "JEV_TIMEOUT_S", -1.0)
    errors = Config.validate()
    assert any("AGORA_JEV_TIMEOUT_S" in error for error in errors)


def test_jev_timeout_rejects_values_above_thirty(monkeypatch):
    monkeypatch.setattr(Config, "JEV_TIMEOUT_S", 30.1)
    errors = Config.validate()
    assert any("AGORA_JEV_TIMEOUT_S" in error for error in errors)
