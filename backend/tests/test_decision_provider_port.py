"""Tests für app.repositories.decision_provider (f005, Slice `decision-pilot`,
Task `provider-port`)."""

from __future__ import annotations

from app.repositories.decision_provider import decision_layer_mode


def test_defaults_to_disabled(monkeypatch) -> None:
    from app.config import Config

    monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")
    assert decision_layer_mode("persona-eligibility") == "disabled"


def test_reflects_the_configured_mode(monkeypatch) -> None:
    from app.config import Config

    monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
    assert decision_layer_mode("persona-eligibility") == "shadow"
