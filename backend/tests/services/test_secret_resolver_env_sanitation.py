"""Tests für die Track-1-Härtung des SecretResolvers.

Hintergrund: Vor diesem Slice ist ein toxischer ``OPENAI_API_KEY=ollama`` im
Container-Env durch den Resolver geschlüpft → ``OpenAI(api_key="ollama")``
→ 401-Loop. Nach der Härtung:

  * ENV-Werte mit falschem Format / Toxic-Literal werden abgelehnt (``None``).
  * Provider-spezifische ENV-Variablen werden korrekt gemappt
    (``OLLAMA_API_KEY`` → ``provider_type="ollama_cloud"`` usw.).
  * ``last_source`` trägt die Herkunft des Keys für Audit-Logging.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.services import llm_provider_secrets_store as store_module
from app.services.llm_provider_secrets_store import reset_singleton_for_tests
from app.services.secret_resolver import SecretResolver, _format_valid, _mask_for_log


@pytest.fixture
def configured_store(monkeypatch, tmp_path: Path):
    """Frischer, leerer Fernet-Store pro Test."""
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    reset_singleton_for_tests()
    yield store_module.get_llm_provider_secrets_store()
    reset_singleton_for_tests()


# ---------------------------------------------------------------------------
# _format_valid — provider-spezifische Format-Checks
# ---------------------------------------------------------------------------


class TestFormatValid:
    @pytest.mark.parametrize(
        "value",
        [
            "sk-proj-abcdefghij1234567890XYZ",
            "sk-test1234567890abcdefghijklmnop",
        ],
    )
    def test_openai_valid_keys(self, value):
        assert _format_valid(value, "openai") is True

    @pytest.mark.parametrize(
        "value",
        [
            "ollama",
            "OLLAMA",
            "Ollama",
            "your-key-here",
            "none",
            "sk-",
            "sk",
            "",
            None,
        ],
    )
    def test_openai_rejects_toxic_or_malformed(self, value):
        assert _format_valid(value, "openai") is False

    def test_google_valid_aizasy(self):
        assert _format_valid("AIzaSyTestValidKey1234567890abcDEF", "google") is True

    @pytest.mark.parametrize(
        "value",
        ["AIza", "google-key", "garbage", "ollama"],
    )
    def test_google_rejects_garbage(self, value):
        assert _format_valid(value, "google") is False

    def test_ollama_cloud_is_liberal_but_rejects_toxic_literals(self):
        # Doku zeigt kein striktes Prefix für OLLAMA_API_KEY → bewusst liberal.
        assert _format_valid("fa6b1234deadbeef5678abcd", "ollama_cloud") is True
        assert _format_valid("ollama", "ollama_cloud") is False
        assert _format_valid("none", "ollama_cloud") is False

    def test_unknown_provider_falls_back_to_toxic_filter(self):
        assert _format_valid("any-value", "custom_xyz") is True
        assert _format_valid("ollama", "custom_xyz") is False


class TestMaskForLog:
    def test_short_value_masked(self):
        assert _mask_for_log("sk") == "<short>"

    def test_long_value_prefix_only(self):
        assert _mask_for_log("sk-proj-supersecretkey") == "sk-p..."

    def test_empty_marker(self):
        assert _mask_for_log("") == "<empty>"
        assert _mask_for_log(None) == "<empty>"


# ---------------------------------------------------------------------------
# Resolver — ENV-Pfad mit Format-Sanity-Check
# ---------------------------------------------------------------------------


class TestEnvSanitation:
    def test_openai_toxic_env_returns_none(self, monkeypatch, configured_store):
        """Der historische Bug: OPENAI_API_KEY=ollama darf nicht durchgehen."""
        monkeypatch.setenv("OPENAI_API_KEY", "ollama")
        # Kein Config-Fallback, der das maskiert
        monkeypatch.setattr("app.services.secret_resolver.Config.LLM_API_KEY", None)

        resolver = SecretResolver()
        assert resolver.get_api_key("openai", "openai") is None
        assert resolver.last_source is None

    def test_openai_valid_env_returns_key(self, monkeypatch, configured_store):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test1234567890abcdefghijklmnop")
        monkeypatch.setattr("app.services.secret_resolver.Config.LLM_API_KEY", None)

        resolver = SecretResolver()
        assert resolver.get_api_key("openai", "openai") == "sk-test1234567890abcdefghijklmnop"
        assert resolver.last_source == "env:OPENAI_API_KEY"

    def test_google_garbage_env_rejected(self, monkeypatch, configured_store):
        monkeypatch.setenv("GOOGLE_API_KEY", "garbage")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr("app.services.secret_resolver.Config.LLM_API_KEY", None)

        resolver = SecretResolver()
        assert resolver.get_api_key("google", "google") is None

    def test_google_falls_through_to_gemini_env(self, monkeypatch, configured_store):
        """Wenn GOOGLE_API_KEY garbage ist, soll GEMINI_API_KEY als Backup ziehen."""
        monkeypatch.setenv("GOOGLE_API_KEY", "garbage")
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyValidGeminiKey1234567890ABC")

        resolver = SecretResolver()
        assert resolver.get_api_key("google", "google") == "AIzaSyValidGeminiKey1234567890ABC"
        assert resolver.last_source == "env:GEMINI_API_KEY"

    def test_config_fallback_rejected_for_openai_with_wrong_format(
        self, monkeypatch, configured_store
    ):
        """Ollama-Cloud-Key (hex) darf NICHT als OpenAI-Fallback dienen."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(
            "app.services.secret_resolver.Config.LLM_API_KEY",
            "fa6b1234deadbeef5678abcd9876543210",  # Ollama-Cloud-Format
        )

        resolver = SecretResolver()
        assert resolver.get_api_key("openai", "openai") is None

    def test_config_fallback_allowed_for_ollama_cloud(
        self, monkeypatch, configured_store
    ):
        """Für ollama_cloud bleibt Config.LLM_API_KEY als Fallback erlaubt."""
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.setattr(
            "app.services.secret_resolver.Config.LLM_API_KEY",
            "fa6b1234deadbeef5678abcd9876543210",
        )

        resolver = SecretResolver()
        result = resolver.get_api_key("ollama_cloud", "ollama_cloud")
        assert result == "fa6b1234deadbeef5678abcd9876543210"
        assert resolver.last_source == "config_fallback"


# ---------------------------------------------------------------------------
# Resolver — Provider-spezifische ENV-Mapping
# ---------------------------------------------------------------------------


class TestProviderEnvMapping:
    def test_ollama_cloud_reads_ollama_api_key(self, monkeypatch, configured_store):
        monkeypatch.setenv("OLLAMA_API_KEY", "fa6b1234deadbeef5678abcd9876543210")
        # LLM_API_KEY existiert evtl. global — wir wollen sicher die ENV-Quelle treffen
        monkeypatch.setattr("app.services.secret_resolver.Config.LLM_API_KEY", None)

        resolver = SecretResolver()
        assert (
            resolver.get_api_key("ollama_cloud", "ollama_cloud")
            == "fa6b1234deadbeef5678abcd9876543210"
        )
        assert resolver.last_source == "env:OLLAMA_API_KEY"

    def test_openai_compatible_reads_llm_api_key_env(self, monkeypatch, configured_store):
        monkeypatch.setenv("LLM_API_KEY", "custom-endpoint-token-abc123")
        # Config.LLM_API_KEY wird beim Modul-Import gesnapshotted; expliziter Patch.
        monkeypatch.setattr(
            "app.services.secret_resolver.Config.LLM_API_KEY",
            "custom-endpoint-token-abc123",
        )

        resolver = SecretResolver()
        result = resolver.get_api_key("openai_compatible", "openai_compatible")
        assert result == "custom-endpoint-token-abc123"
        assert resolver.last_source in ("env:LLM_API_KEY", "config_fallback")

    def test_toxic_ollama_api_key_returns_none(self, monkeypatch, configured_store):
        monkeypatch.setenv("OLLAMA_API_KEY", "ollama")
        monkeypatch.setattr("app.services.secret_resolver.Config.LLM_API_KEY", None)

        resolver = SecretResolver()
        assert resolver.get_api_key("ollama_cloud", "ollama_cloud") is None


# ---------------------------------------------------------------------------
# last_source — Audit-Side-Channel für LLMClient-Init-Log
# ---------------------------------------------------------------------------


class TestLastSource:
    def test_session_source(self, configured_store):
        resolver = SecretResolver(session_api_keys={"openai": "session-key-xyz"})
        resolver.get_api_key("openai", "openai")
        assert resolver.last_source == "session"

    def test_store_source(self, configured_store):
        configured_store.upsert("openai", api_key="sk-storedkey1234567890abcdefghij")
        resolver = SecretResolver()
        resolver.get_api_key("openai", "openai")
        assert resolver.last_source == "store"

    def test_none_source_when_nothing_available(self, monkeypatch, configured_store):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr("app.services.secret_resolver.Config.LLM_API_KEY", None)

        resolver = SecretResolver()
        assert resolver.get_api_key("openai", "openai") is None
        assert resolver.last_source is None

    def test_last_source_resets_per_call(self, monkeypatch, configured_store):
        configured_store.upsert("google", api_key="AIzaSyStoreKey1234567890abcDEF")
        resolver = SecretResolver()
        resolver.get_api_key("google", "google")
        assert resolver.last_source == "store"

        # Zweiter Aufruf für anderen Provider ohne Match → None
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr("app.services.secret_resolver.Config.LLM_API_KEY", None)
        resolver.get_api_key("openai", "openai")
        assert resolver.last_source is None
