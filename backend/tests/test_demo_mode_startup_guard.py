"""Startup-Guard: die oeffentliche Demo-Instanz (AGORA_DEMO_MODE=true) darf
nie Betreiber-Provider-Zugangsdaten halten oder nutzen (#1688).

``create_app()`` muss den Prozess-Start hart verweigern, sobald eine der in
``app.config.DEMO_MODE_FORBIDDEN_ENV_VARS`` gelisteten Env-Vars nicht-leer
gesetzt ist, waehrend ``AGORA_DEMO_MODE`` aktiv ist. Fehlermeldungen duerfen
nur Variablennamen nennen, nie Werte.
"""

from __future__ import annotations

import pytest

from app.config import DEMO_MODE_FORBIDDEN_ENV_VARS


def _test_value(name: str) -> str:
    """Fixture-Wert, den GitGuardian nicht als echtes Secret erkennt."""
    return "-".join(("unit", "test", name, "value"))


def _clear_all_forbidden_vars(monkeypatch):
    for name in DEMO_MODE_FORBIDDEN_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_demo_mode_refuses_startup_with_operator_key_set(monkeypatch):
    """create_app() wirft RuntimeError, sobald in AGORA_DEMO_MODE=true eine
    verbotene Betreiber-Env-Var gesetzt ist. Die Meldung nennt nur den Namen.
    """
    _clear_all_forbidden_vars(monkeypatch)
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    secret_value = _test_value("openai-operator-secret")
    monkeypatch.setenv("OPENAI_API_KEY", secret_value)

    from app import create_app

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY") as excinfo:
        create_app()

    assert "AGORA_DEMO_MODE" in str(excinfo.value)
    assert secret_value not in str(excinfo.value)


def test_demo_mode_succeeds_without_operator_keys(monkeypatch):
    """AGORA_DEMO_MODE=true ohne gesetzte Betreiber-Vars darf nicht am
    Demo-Guard scheitern (andere Startfehler, z. B. fehlende Neo4j-
    Verbindung, sind hier nicht Gegenstand des Tests).
    """
    _clear_all_forbidden_vars(monkeypatch)
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    monkeypatch.setenv("AGORA_SKIP_EMBEDDING_PROBE", "true")

    from app import create_app

    try:
        create_app()
    except RuntimeError as exc:
        assert "AGORA_DEMO_MODE=true verbietet" not in str(exc), (
            f"Demo-Guard darf ohne gesetzte Betreiber-Vars nicht feuern: {exc}"
        )


def test_non_demo_mode_ignores_operator_keys(monkeypatch):
    """Ohne AGORA_DEMO_MODE bleibt der Guard inaktiv — Betreiberinstanzen
    duerfen ihre eigenen Provider-Keys weiter aus der .env lesen.
    """
    monkeypatch.delenv("AGORA_DEMO_MODE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", _test_value("operator-key"))
    monkeypatch.setenv("AGORA_SKIP_EMBEDDING_PROBE", "true")

    from app import create_app

    try:
        create_app()
    except RuntimeError as exc:
        assert "AGORA_DEMO_MODE=true verbietet" not in str(exc), (
            f"Demo-Guard darf ohne AGORA_DEMO_MODE nicht feuern: {exc}"
        )
