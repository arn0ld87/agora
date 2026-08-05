"""Regression-Tests für Issue #872: Init-Log-Annotation.

Jeder LLMClient-Instanziierungspfad muss ``api_key_source`` und ``provider_id``
explizit aus seiner Bezugsquelle setzen, so dass das Init-Log (client.py:148)
durchgängig aussagekräftig ist und Audit-Traces vollständig sind. Ziel: kein
``api_key_source=unknown`` / ``provider_id=unknown`` in produktiven Init-Logs
außer bei echten Unbekannten (Config-Default ohne ableitbare Quelle).

Die Tests fangen die Init-Log-Zeile via ``caplog`` ab und prüfen die
Annotation-Werte — ohne Live-LLM-Call.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.llm.client import LLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INIT_LOGGER = "agora.llm_client"


@pytest.fixture(autouse=True)
def _enable_log_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    """``setup_logger`` setzt ``propagate=False`` (siehe app/utils/logger.py:226),
    damit pytests ``caplog``-Fixture die Init-Log-Zeile abfangen kann.
    Propagation läuft entlang der Logger-Kette — ``agora.llm_client`` erbt
    zwar standardmäßig ``propagate=True``, aber sein Parent ``agora`` blockiert
    die Records am Root-Logger. Beide müssen wir enablen.
    Monkeypatch restauriert die Originalwerte nach jedem Test automatisch.
    """
    parent = logging.getLogger("agora")
    target = logging.getLogger(_INIT_LOGGER)
    monkeypatch.setattr(parent, "propagate", True)
    monkeypatch.setattr(target, "propagate", True)


def _init_log_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Filter caplog auf die LLMClient-Init-Zeile."""
    return [
        r
        for r in caplog.records
        if r.name == _INIT_LOGGER and "LLMClient initialized" in r.getMessage()
    ]


def _patch_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vermeide echtes OpenAI-Client-Init (kein Netzwerk)."""
    monkeypatch.setattr("app.llm.client.OpenAI", lambda **_kw: MagicMock())


# ---------------------------------------------------------------------------
# __init__ direkt: api_key übergeben ohne api_key_source → "passed_in"
# ---------------------------------------------------------------------------


class TestInitDirectPassedIn:
    """Ein Caller, der api_key direkt übergibt, ohne api_key_source zu setzen,
    soll als "passed_in" annotiert werden — nicht als "unknown" durchfallen."""

    def test_direct_api_key_without_source_is_passed_in(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient(
                api_key="sk-direct",
                base_url="https://api.openai.com/v1",
                model="gpt-4o",
                use_active_config=False,
            )
        records = _init_log_records(caplog)
        assert len(records) == 1
        assert "api_key_source=passed_in" in records[0].getMessage()

    def test_explicit_api_key_source_overrides_default(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient(
                api_key="sk-direct",
                base_url="https://api.openai.com/v1",
                model="gpt-4o",
                use_active_config=False,
                api_key_source="custom_caller",
            )
        records = _init_log_records(caplog)
        assert len(records) == 1
        assert "api_key_source=custom_caller" in records[0].getMessage()


# ---------------------------------------------------------------------------
# __init__ config_fallback: Config.LLM_API_KEY → "config_fallback", provider unknown
# (echter Unbekannter — legitim)
# ---------------------------------------------------------------------------


class TestInitConfigFallback:
    def test_config_fallback_annotates_source(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        monkeypatch.setattr("app.llm.client.Config.LLM_API_KEY", "cfg-key")
        monkeypatch.setattr("app.llm.client.Config.LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setattr("app.llm.client.Config.LLM_MODEL_NAME", "gpt-4o")
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient(use_active_config=False)
        records = _init_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "api_key_source=config_fallback" in msg


# ---------------------------------------------------------------------------
# __init__ active_config + SecretResolver: provider_id aus active config,
# api_key_source aus resolver.last_source. End-User-Pfad: User wählt Provider
# in der UI, LLMClient resolved den Key beim Init.
# ---------------------------------------------------------------------------


class TestInitActiveConfigResolver:
    def test_active_config_resolver_annotates_provider_and_source(
        self, caplog, monkeypatch
    ):
        _patch_openai(monkeypatch)
        # Kein Config-Fallback, damit nur der active_config-Pfad greift.
        monkeypatch.setattr("app.llm.client.Config.LLM_API_KEY", None)
        # Active config in Storage: provider_id + model.
        active_config = {
            "provider_id": "openai",
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
        }
        # ``from .json_mode import _read_active_config_safely`` legt eine lokale
        # Binding in app.llm.client an — monkeypatch muss dort ansetzen.
        monkeypatch.setattr(
            "app.llm.client._read_active_config_safely",
            lambda: active_config,
        )
        # Provider-Registry stub: descriptor mit passender id.
        descriptor = MagicMock()
        descriptor.id = "openai"
        descriptor.type = "openai"
        descriptor.base_url = "https://api.openai.com/v1"
        registry = MagicMock()
        registry.get_providers.return_value = [descriptor]
        monkeypatch.setattr(
            "app.services.llm_provider_registry.LlmProviderRegistry",
            lambda: registry,
        )
        # SecretResolver stub: liefert Key + annotiert last_source.
        resolver = MagicMock()
        resolver.get_api_key.return_value = "sk-active"
        resolver.last_source = "session"
        monkeypatch.setattr(
            "app.services.secret_resolver.SecretResolver",
            lambda: resolver,
        )
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient()  # use_active_config=True ist Default
        records = _init_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "api_key_source=session" in msg
        assert "provider_id=openai" in msg


# ---------------------------------------------------------------------------
# Issue #1101: Active-Config-``base_url`` muss auch bei explizitem ``model``
# übernommen werden. Zuvor war der gesamte Active-Config-Lookup an
# ``model is None`` gekoppelt — wurde das Modell vom Caller übergeben (Normalfall
# im Prepare/Run-Pfad), übersprang der Client die Active-Config, ``base_url``
# fiel auf ``Config.LLM_BASE_URL`` (.env-Ollama-Gateway) zurück. Modell aus der
# UI-Auswahl (OpenAI) ging an den .env-Endpoint → HTTP 404 → stiller
# regelbasierter Persona-Fallback.
# ---------------------------------------------------------------------------


class TestInitActiveConfigBaseUrlWithExplicitModel:
    _OLLAMA_ENV_URL = "http://100.71.152.44:11435/v1"
    _OPENAI_ACTIVE_URL = "https://api.openai.com/v1"

    def _stub_active_config(self, monkeypatch) -> None:
        # CodeRabbit #1102: active["model"] bewusst abweichend vom
        # caller-Modell, damit ``assert client.model == "gpt-5.6-luna"``
        # wirklich prueft, dass die Active-Config das uebergebene Modell
        # nicht ueberschreibt (sonst wuerden gleiche Werte den Guard verdecken).
        monkeypatch.setattr(
            "app.llm.client._read_active_config_safely",
            lambda: {
                "provider_id": "openai",
                "model": "active-config-model",
                "base_url": self._OPENAI_ACTIVE_URL,
            },
        )

    def test_active_config_base_url_used_when_model_explicit(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        # .env-Default (Ollama-Gateway) — darf NICHT gewinnen.
        monkeypatch.setattr(
            "app.llm.client.Config.LLM_BASE_URL", self._OLLAMA_ENV_URL
        )
        self._stub_active_config(monkeypatch)
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            client = LLMClient(model="gpt-5.6-luna", api_key="sk-test")
        # base_url aus Active-Config, nicht aus .env.
        assert client.base_url == self._OPENAI_ACTIVE_URL
        # übergebenes Modell wird nicht überschrieben.
        assert client.model == "gpt-5.6-luna"
        records = _init_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "provider_id=openai" in msg
        # Vollständige URL prüfen statt bloßem Substring (CodeQL
        # py/cs-3260: unvollständige Substring-Sanitization). Die
        # Active-Config-URL muss im Init-Log stehen, die .env-Ollama-URL
        # darf gar nicht auftauchen — nicht nur als Substring fehlen.
        assert self._OPENAI_ACTIVE_URL in msg
        assert self._OLLAMA_ENV_URL not in msg

    def test_explicit_base_url_not_overridden_by_active_config(self, monkeypatch):
        _patch_openai(monkeypatch)
        monkeypatch.setattr(
            "app.llm.client.Config.LLM_BASE_URL", self._OLLAMA_ENV_URL
        )
        self._stub_active_config(monkeypatch)
        # Caller übergibt eigene base_url (z. B. aus aufgelöster ResolvedRoute).
        client = LLMClient(
            model="gpt-5.6-luna",
            base_url="https://explicit.example.com/v1",
            api_key="sk-test",
        )
        assert client.base_url == "https://explicit.example.com/v1"
        assert client.model == "gpt-5.6-luna"


# ---------------------------------------------------------------------------
# from_route: connection_only → "store"
# ---------------------------------------------------------------------------


def _strict_route() -> ResolvedRoute:
    return ResolvedRoute(
        stage="graph_build",
        provider_id="connection-openai",
        model="gpt-4.1-mini",
        routing_version=1,
        provider_options={
            "secret_ref": "connection-secret",
            "connection_only": True,
        },
    )


class TestFromRouteStore:
    def test_connection_only_route_annotates_store(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        store = MagicMock()
        store.get_plaintext.return_value = "connection-key"
        monkeypatch.setattr(
            "app.llm.client.get_llm_provider_secrets_store",
            lambda: store,
        )
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient.from_route(_strict_route())
        records = _init_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "api_key_source=store" in msg
        assert "provider_id=connection-openai" in msg


# ---------------------------------------------------------------------------
# from_route: api_key_override → "passed_in"
# ---------------------------------------------------------------------------


class TestFromRouteOverride:
    def test_api_key_override_annotates_passed_in(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        # Issue #1101: Active-Config-Lookup läuft jetzt auch bei gesetztem
        # Modell. Dieser Test prüft api_key_override-Annotation, nicht
        # Active-Config-Interaktion — deshalb Active-Config auf None setzen,
        # damit die Route (provider_id=openai) unangetastet bleibt.
        monkeypatch.setattr("app.llm.client._read_active_config_safely", lambda: None)
        route = ResolvedRoute(
            stage="graph_build",
            provider_id="openai",
            model="gpt-4o",
            routing_version=1,
            provider_options={},
        )
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient.from_route(route, api_key_override="sk-override")
        records = _init_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "api_key_source=passed_in" in msg
        assert "provider_id=openai" in msg


# ---------------------------------------------------------------------------
# from_route: secret_resolver → last_source
# ---------------------------------------------------------------------------


class TestFromRouteResolver:
    def test_resolver_annotates_last_source(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        route = ResolvedRoute(
            stage="graph_build",
            provider_id="openai",
            model="gpt-4o",
            routing_version=1,
            provider_options={},
        )
        resolver = MagicMock()
        resolver.get_api_key.return_value = "sk-resolved"
        resolver.last_source = "session"
        # Provider-Registry stub: descriptor mit passender id
        descriptor = MagicMock()
        descriptor.id = "openai"
        descriptor.type = "openai"
        descriptor.base_url = "https://api.openai.com/v1"
        registry = MagicMock()
        registry.get_providers.return_value = [descriptor]
        monkeypatch.setattr(
            "app.services.llm_provider_registry.LlmProviderRegistry",
            lambda: registry,
        )
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient.from_route(route, secret_resolver=resolver)
        records = _init_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        assert "api_key_source=session" in msg
        assert "provider_id=openai" in msg


# ---------------------------------------------------------------------------
# from_route: kein Key, kein Resolver → fällt zu __init__, dort config_fallback
# oder unknown — aber niemals "unknown" bei vorhandenem api_key
# ---------------------------------------------------------------------------


class TestFromRouteNoKey:
    def test_route_without_key_falls_to_init_fallback(self, caplog, monkeypatch):
        _patch_openai(monkeypatch)
        monkeypatch.setattr("app.llm.client.Config.LLM_API_KEY", "cfg-key")
        monkeypatch.setattr("app.llm.client.Config.LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setattr("app.llm.client.Config.LLM_MODEL_NAME", "gpt-4o")
        # Issue #1101: Active-Config-Lookup läuft jetzt auch bei gesetztem
        # Modell. Test prüft den Config-Fallback-Pfad, nicht Active-Config —
        # deshalb Active-Config auf None setzen.
        monkeypatch.setattr("app.llm.client._read_active_config_safely", lambda: None)
        route = ResolvedRoute(
            stage="graph_build",
            provider_id="openai",
            model="gpt-4o",
            routing_version=1,
            provider_options={},
        )
        with caplog.at_level(logging.INFO, logger=_INIT_LOGGER):
            LLMClient.from_route(route)
        records = _init_log_records(caplog)
        assert len(records) == 1
        msg = records[0].getMessage()
        # config_fallback ist die legitime Annotation, wenn Config.LLM_API_KEY greift
        assert "api_key_source=config_fallback" in msg
        assert "provider_id=openai" in msg
