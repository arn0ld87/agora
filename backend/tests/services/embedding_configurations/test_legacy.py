"""Tests für ``embedding_configurations.legacy`` (Onboarding Slice 4.2)."""

from __future__ import annotations

import pytest

from app.config import Config
from app.services.embedding_configurations.legacy import (
    build_legacy_view,
    legacy_view_to_configuration,
    legacy_view_to_provider_connection,
)


@pytest.fixture(autouse=True)
def _reset_config_cache() -> None:
    """``Config`` cached Werte; zwischen Tests muessen wir nichts erzwingen,
    aber wir stellen sicher, dass die relevanten Felder einen frischen
    Default-Status haben.
    """


def test_build_legacy_view_uses_ollama_for_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", None)
    monkeypatch.setattr(Config, "VECTOR_DIM", 768)

    view = build_legacy_view()

    assert view is not None
    assert view.provider_kind == "ollama"
    assert view.model_id == "nomic-embed-text"
    assert view.dimensions == 768
    assert view.base_url == "http://localhost:11434"


def test_build_legacy_view_uses_ollama_cloud_for_ollama_com(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "https://ollama.com/v1")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "key-abc")
    monkeypatch.setattr(Config, "VECTOR_DIM", 768)

    view = build_legacy_view()
    assert view is not None
    assert view.provider_kind == "ollama_cloud"


def test_build_legacy_view_uses_openai_with_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "sk-abc")
    monkeypatch.setattr(Config, "VECTOR_DIM", 1536)

    view = build_legacy_view()
    assert view is not None
    assert view.provider_kind == "openai"
    assert view.dimensions == 1536


def test_build_legacy_view_returns_none_when_model_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://localhost:11434")
    assert build_legacy_view() is None


def test_legacy_view_to_configuration_uses_proposed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", None)
    monkeypatch.setattr(Config, "VECTOR_DIM", 768)
    view = build_legacy_view()
    assert view is not None

    config = legacy_view_to_configuration(view)

    assert config.status == "proposed"
    assert "Config.EMBEDDING" in (config.status_message or "")
    assert config.scope == "global"
    assert config.project_id is None


def test_legacy_view_to_provider_connection_for_local_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", None)
    view = build_legacy_view()
    assert view is not None

    connection = legacy_view_to_provider_connection(view)

    assert connection.provider_kind == "ollama"
    assert connection.transport == "local"
    assert connection.auth_mode == "none"
    assert connection.secret_ref is None
    assert connection.status == "unknown"


def test_legacy_view_to_provider_connection_with_api_key_uses_secret_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "sk-abc")
    view = build_legacy_view()
    assert view is not None

    connection = legacy_view_to_provider_connection(view)

    assert connection.auth_mode == "api_key"
    assert connection.secret_ref == "legacy-embedding"
    assert connection.transport == "http"


# ----------------------------------------------------------------------
# Security: CodeQL HIGH — "Incomplete URL substring sanitization" (legacy.py:69)
# ----------------------------------------------------------------------


def test_classify_legacy_provider_rejects_ollama_com_substring_in_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substring-Match auf 'ollama.com' waere ein SSRF-Vektor. Der
    Fix nutzt urlparse + Suffix-Match auf dem Host-Namen.
    """
    from app.services.embedding_configurations.legacy import (
        _classify_legacy_provider,
    )

    # Bösartige URL mit ollama.com im Query/Pfad, aber echter Host ist evil.com
    kind = _classify_legacy_provider(
        "https://evil.com/?ref=ollama.com", has_api_key=True
    )
    assert kind == "openai", (
        f"evil.com darf nicht als ollama_cloud klassifiziert werden, "
        f"aber war: {kind}"
    )


def test_classify_legacy_provider_accepts_ollama_cloud_subdomain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.embedding_configurations.legacy import (
        _classify_legacy_provider,
    )

    assert (
        _classify_legacy_provider("https://api.ollama.com/v1", has_api_key=True)
        == "ollama_cloud"
    )


def test_classify_legacy_provider_accepts_exact_ollama_com(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.embedding_configurations.legacy import (
        _classify_legacy_provider,
    )

    assert (
        _classify_legacy_provider("https://ollama.com", has_api_key=True)
        == "ollama_cloud"
    )
