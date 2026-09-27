"""Startup-Guard: die oeffentliche Demo-Instanz (AGORA_DEMO_MODE=true) darf
nie Betreiber-Provider-Zugangsdaten halten oder nutzen (#1688).

``create_app()`` muss den Prozess-Start hart verweigern, sobald eine der in
``app.config.DEMO_MODE_FORBIDDEN_ENV_VARS`` gelisteten Env-Vars nicht-leer
gesetzt ist, waehrend ``AGORA_DEMO_MODE`` aktiv ist. Fehlermeldungen duerfen
nur Variablennamen nennen, nie Werte.
"""

from __future__ import annotations

import logging

import pytest

from app import _warn_if_jwt_active_without_demo_mode
from app.config import DEMO_MODE_FORBIDDEN_ENV_VARS


def _test_value(name: str) -> str:
    """Fixture-Wert, den GitGuardian nicht als echtes Secret erkennt."""
    return "-".join(("unit", "test", name, "value"))


def _clear_all_forbidden_vars(monkeypatch):
    from pathlib import Path

    from app.services import settings_layer

    for name in DEMO_MODE_FORBIDDEN_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Eine echte backend/instance/settings.json des Testhosts darf das
    # Ergebnis nicht beeinflussen.
    monkeypatch.setattr(
        settings_layer, "get_default_service",
        lambda: settings_layer.SettingsService(
            instance_path=Path("/nonexistent-agora-test/settings.json")
        ),
    )


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


@pytest.mark.parametrize(
    "name",
    ["TAVILY_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "OLLAMA_BASE_URL",
     "OPENAI_BASE_URL", "OPENAI_API_BASE_URL"],
)
def test_demo_mode_forbids_round3_operator_vars(monkeypatch, name):
    """#1688 Runde 3: Web-Recherche-, Claude-CLI- und OpenAI-/Ollama-
    Endpunkt-Vars zaehlen ebenfalls als Betreiber-Zugang."""
    from app.config import demo_mode_leaked_operator_vars

    _clear_all_forbidden_vars(monkeypatch)
    monkeypatch.setenv(name, _test_value(name.lower()))

    assert demo_mode_leaked_operator_vars() == [name]


def test_demo_mode_embedding_base_url_stays_allowed(monkeypatch):
    """Demo-Embeddings laufen ueber den freigegebenen Betreiber-Endpoint
    (gns3), EMBEDDING_BASE_URL und EMBEDDING_API_KEY sind deshalb erlaubt."""
    from app.config import demo_mode_leaked_operator_vars

    _clear_all_forbidden_vars(monkeypatch)
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embed.tailnet.example/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", _test_value("embedding-key"))

    assert demo_mode_leaked_operator_vars() == []


def test_demo_mode_detects_operator_key_in_settings_json(monkeypatch, tmp_path):
    """Der Settings-Layer legt instance/settings.json ueber die Env — ein
    dort persistierter Key ist genauso ein Betreiber-Zugang. Gemeldet wird
    nur der Name, nie der Wert."""
    import json

    from app.config import demo_mode_leaked_operator_vars
    from app.services import settings_layer

    _clear_all_forbidden_vars(monkeypatch)
    secret_value = _test_value("settings-file-key")
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"LLM_API_KEY": secret_value, "LLM_MODEL_NAME": "x"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        settings_layer, "get_default_service",
        lambda: settings_layer.SettingsService(instance_path=settings_file),
    )

    leaked = demo_mode_leaked_operator_vars()

    assert leaked == ["instance/settings.json:LLM_API_KEY"]
    assert secret_value not in " ".join(leaked)


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


def test_warns_when_jwt_active_without_demo_mode(monkeypatch, caplog):
    """Item 5a: aktives Supabase-JWT ohne AGORA_DEMO_MODE loggt eine
    unmissverstaendliche WARNING statt den Start zu verweigern."""
    monkeypatch.delenv("AGORA_DEMO_MODE", raising=False)
    monkeypatch.setattr(
        "app.security.principal_context.tenant_mode_active", lambda: True
    )
    # Kein "agora."-Praefix: der Produktions-Logger "agora" laeuft mit
    # propagate=False (setup_logger), was caplogs Root-Handler nichts sehen
    # liesse. Der Test prueft nur ``logger.warning(...)``, nicht welcher
    # konkrete Logger-Name in create_app() verwendet wird.
    logger = logging.getLogger("test_demo_mode_startup_guard")

    with caplog.at_level(logging.WARNING, logger=logger.name):
        _warn_if_jwt_active_without_demo_mode(logger)

    assert any("AGORA_DEMO_MODE" in record.getMessage() for record in caplog.records)
    assert any("Supabase-JWT" in record.getMessage() for record in caplog.records)


def test_no_warning_in_demo_mode_even_with_jwt_active(monkeypatch, caplog):
    """In AGORA_DEMO_MODE=true greift der Startup-Guard aus Item 4; die
    Item-5a-Warnung ist dort nicht nötig und darf nicht doppelt feuern."""
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    monkeypatch.setattr(
        "app.security.principal_context.tenant_mode_active", lambda: True
    )
    logger = logging.getLogger("test_demo_mode_startup_guard")

    with caplog.at_level(logging.WARNING, logger=logger.name):
        _warn_if_jwt_active_without_demo_mode(logger)

    assert not caplog.records


def test_no_warning_without_jwt(monkeypatch, caplog):
    """Ohne aktives Supabase-JWT bleibt es beim Nichtstun, auch ausserhalb
    von AGORA_DEMO_MODE."""
    monkeypatch.delenv("AGORA_DEMO_MODE", raising=False)
    monkeypatch.setattr(
        "app.security.principal_context.tenant_mode_active", lambda: False
    )
    logger = logging.getLogger("test_demo_mode_startup_guard")

    with caplog.at_level(logging.WARNING, logger=logger.name):
        _warn_if_jwt_active_without_demo_mode(logger)

    assert not caplog.records


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


def test_validate_does_not_require_llm_api_key_in_demo_mode(monkeypatch):
    """Das Public-Overlay leert LLM_API_KEY; der Guard verbietet ihn sogar.
    Config.validate() darf den Start dann nicht an genau diesem Feld scheitern
    lassen, ausserhalb des Demo-Modus bleibt er Pflicht.
    """
    from app.config import Config

    monkeypatch.setattr(Config, "LLM_API_KEY", "")
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    assert not any("LLM_API_KEY" in e for e in Config.validate())

    monkeypatch.delenv("AGORA_DEMO_MODE")
    assert any("LLM_API_KEY" in e for e in Config.validate())


def test_operator_credential_context_allows_startup_work_in_demo_mode(monkeypatch):
    """Startup-Arbeit ohne Lauf (Embedding-Probe, Storage-Init) laeuft im
    Demo-Modus nur im ausdruecklich gebundenen Operator-Scope; ungebunden
    bleibt der implizite Rueckfall gesperrt.
    """
    from app.services import llm_routing_seed as seed

    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    with pytest.raises(ValueError, match="no persisted credential scope"):
        seed.workspace_credential_id_for_run(None)

    with seed.operator_credential_context():
        assert seed.workspace_credential_id_for_run(None) is None

    with pytest.raises(ValueError, match="no persisted credential scope"):
        seed.workspace_credential_id_for_run(None)
