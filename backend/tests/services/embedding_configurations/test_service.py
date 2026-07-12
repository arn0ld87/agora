"""Tests für ``EmbeddingConfigurationService`` (Onboarding Slice 4.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
from cryptography.fernet import Fernet

from app.contracts.ai_provider_contract import (
    LocalOllamaBaseUrl,
    ProviderConnection,
    ProviderStatus,
)
from app.contracts.embedding_contract import (
    EmbeddingConfigurationStatus,
    EmbeddingProviderKind,
)
from app.services.embedding_configuration_store import EmbeddingConfigurationStore
from app.services.embedding_configurations.adapters import EmbeddingProbeResult
from app.services.embedding_configurations.service import (
    EmbeddingConfigurationService,
)
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
from app.services.provider_connection_store import ProviderConnectionStore


@pytest.fixture
def fixed_now():
    return datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EmbeddingConfigurationStore:
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    return EmbeddingConfigurationStore(data_dir=tmp_path)


def _make_connection(
    *, kind: EmbeddingProviderKind = "ollama", secret_ref: Optional[str] = None
) -> ProviderConnection:
    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    is_ollama = kind == "ollama"
    base_url: str | None = "http://localhost:11434" if is_ollama else None
    if is_ollama and base_url is not None:
        base_url = LocalOllamaBaseUrl(base_url)
    return ProviderConnection(
        id=f"conn-{kind}",
        provider_kind=kind,
        display_name=kind,
        transport="local" if is_ollama else "http",
        auth_mode="api_key" if secret_ref else "none",
        base_url=base_url,
        enabled=True,
        status="unknown",
        secret_ref=secret_ref,
        capabilities={},
        created_at=now,
        updated_at=now,
    )


def _stub_adapter(
    result: EmbeddingProbeResult,
) -> "object":  # simple namespace to mimic the protocol
    class _Adapter:
        def probe(
            self,
            connection: ProviderConnection,
            model_id: str,
            api_key: str | None,
        ) -> EmbeddingProbeResult:
            return result

    return _Adapter()


# ----------------------------------------------------------------------
# Probe
# ----------------------------------------------------------------------


def test_probe_updates_status_to_probed_on_available(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    config = store.upsert_configuration(
        configuration_id=None,
        provider_connection_id="conn-ollama",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    connection = _make_connection(kind="ollama")
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([connection]),
        secrets_store=_NoopSecretsStore(),
        adapter_factory=lambda kind: _stub_adapter(
            EmbeddingProbeResult(
                status="available",
                status_message=None,
                actual_dimensions=768,
            )
        ),
        now=lambda: fixed_now,
    )

    updated, result = service.probe(config.id)

    assert updated.status == "probed"
    assert updated.last_validated_at == fixed_now
    assert result.status == "available"
    assert result.actual_dimensions == 768


def test_probe_marks_configuration_failed_on_dimension_mismatch(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    config = store.upsert_configuration(
        configuration_id=None,
        provider_connection_id="conn-ollama",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([_make_connection(kind="ollama")]),
        secrets_store=_NoopSecretsStore(),
        adapter_factory=lambda kind: _stub_adapter(
            EmbeddingProbeResult(
                status="available",
                status_message=None,
                actual_dimensions=1024,
            )
        ),
        now=lambda: fixed_now,
    )
    updated, _ = service.probe(config.id)

    assert updated.status == "failed"
    assert "768" in (updated.status_message or "")
    assert "1024" in (updated.status_message or "")


def test_probe_with_unknown_configuration_raises(
    store: EmbeddingConfigurationStore,
) -> None:
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([]),
        secrets_store=_NoopSecretsStore(),
    )
    with pytest.raises(KeyError):
        service.probe("emb-bogus")


def test_probe_with_missing_connection_raises(
    store: EmbeddingConfigurationStore,
) -> None:
    config = store.upsert_configuration(
        configuration_id=None,
        provider_connection_id="conn-missing",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([]),
        secrets_store=_NoopSecretsStore(),
    )
    with pytest.raises(KeyError):
        service.probe(config.id)


# ----------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------


def test_activate_marks_previous_active_as_rolled_back(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    old = store.upsert_configuration(
        configuration_id="emb-old",
        provider_connection_id="conn-ollama",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="active",
    )
    new = store.upsert_configuration(
        configuration_id="emb-new",
        provider_connection_id="conn-ollama",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([_make_connection(kind="ollama")]),
        secrets_store=_NoopSecretsStore(),
        now=lambda: fixed_now,
    )
    active = service.activate(new.id)

    assert active.status == "active"
    rolled_back = store.get_configuration(old.id)
    assert rolled_back is not None
    assert rolled_back.status == "rolled_back"


def test_activate_rejects_failed_configuration(
    store: EmbeddingConfigurationStore,
) -> None:
    config = store.upsert_configuration(
        configuration_id="emb-failed",
        provider_connection_id="conn-ollama",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="failed",
    )
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([_make_connection(kind="ollama")]),
        secrets_store=_NoopSecretsStore(),
    )
    with pytest.raises(ValueError):
        service.activate(config.id)


def test_rollback_marks_configuration(
    store: EmbeddingConfigurationStore, fixed_now: datetime
) -> None:
    config = store.upsert_configuration(
        configuration_id=None,
        provider_connection_id="conn-ollama",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="active",
    )
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([_make_connection(kind="ollama")]),
        secrets_store=_NoopSecretsStore(),
        now=lambda: fixed_now,
    )
    rolled_back = service.rollback(config.id)
    assert rolled_back.status == "rolled_back"
    assert "Operator-Rollback" in (rolled_back.status_message or "")


# ----------------------------------------------------------------------
# Legacy-Sync
# ----------------------------------------------------------------------


def test_sync_legacy_creates_proposed_configuration(
    store: EmbeddingConfigurationStore,
) -> None:
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([]),
        secrets_store=_NoopSecretsStore(),
    )
    config = service.sync_legacy(
        provider_connection_id="legacy",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
    )
    assert config is not None
    assert config.status == "proposed"
    assert "Config.EMBEDDING" in (config.status_message or "")


def test_sync_legacy_is_noop_when_active_configuration_exists(
    store: EmbeddingConfigurationStore,
) -> None:
    store.upsert_configuration(
        configuration_id="emb-active",
        provider_connection_id="conn-ollama",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="active",
    )
    service = EmbeddingConfigurationService(
        store=store,
        connection_store=_FakeConnectionStore([_make_connection(kind="ollama")]),
        secrets_store=_NoopSecretsStore(),
    )
    config = service.sync_legacy(
        provider_connection_id="legacy",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
    )
    assert config is None


# ----------------------------------------------------------------------
# Mocks
# ----------------------------------------------------------------------


class _FakeConnectionStore:
    def __init__(self, connections: list[ProviderConnection]) -> None:
        self._connections = connections

    def list_connections(self) -> list[ProviderConnection]:
        return list(self._connections)


class _NoopSecretsStore(LlmProviderSecretsStore):
    """Secrets-Store-Stub, der niemals einen echten Schluessel zurueckgibt."""

    def get_plaintext(self, secret_ref: str) -> str | None:  # type: ignore[override]
        return None
