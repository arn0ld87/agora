"""Contract tests for the Ollama-activate path (Issue #934).

Sperrt die in Issue #934 vereinbarten Eigenschaften des Activate-Pfads:

* Nach ``activate_ollama_embedding`` ist genau eine globale
  ``EmbeddingConfiguration`` mit ``status='active'``,
  ``provider_kind='ollama'``, ``model_id='embeddinggemma:300m'`` und
  ``dimensions=768`` vorhanden.
* Eine vorher aktive Gemini-Konfiguration wird auf
  ``status='rolled_back'`` gesetzt (Audit-Trail; nicht geloescht).
* Wiederholte Aufrufe sind idempotent — die gleiche Konfiguration
  bleibt aktiv, ohne weitere Knoten anzulegen.

Read/write paths laufen ausschliesslich ueber
``EmbeddingConfigurationStore`` und ``ProviderConnectionStore``. Die
Tests verwenden einen temporaeren ``AGORA_DATA_DIR``, sodass keine
Live-Daten beruehrt werden.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.contracts.embedding_contract import EmbeddingConfiguration
from app.services.embedding_configuration_store import EmbeddingConfigurationStore
from app.services.embedding_configurations.activate_ollama import (
    DEFAULT_OLLAMA_DIMENSIONS,
    DEFAULT_OLLAMA_MODEL,
    activate_ollama_embedding,
)
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
from app.services.provider_connection_store import ProviderConnectionStore


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def isolated_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Isolierter ``AGORA_DATA_DIR`` fuer jeden Test.

    Setzt zusaetzlich ``AGORA_SECRET_KEY`` (per Fernet), damit der
    Secrets-Store voll initialisiert werden kann.
    """
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode("utf-8"))
    return tmp_path


@pytest.fixture
def stores(isolated_data_dir: Path):
    configuration_store = EmbeddingConfigurationStore(data_dir=isolated_data_dir)
    connection_store = ProviderConnectionStore(data_dir=isolated_data_dir)
    secrets_store = LlmProviderSecretsStore(data_dir=isolated_data_dir)
    return configuration_store, connection_store, secrets_store


def _seed_legacy_gemini_active(
    *,
    configuration_store: EmbeddingConfigurationStore,
    connection_store: ProviderConnectionStore,
) -> EmbeddingConfiguration:
    """Seedet eine vorher aktive Gemini-2-Konfiguration (3072-dim)."""
    from app.contracts.ai_provider_contract import ProviderConnectionUpsertRequest

    connection = connection_store.upsert_connection(
        ProviderConnectionUpsertRequest(
            provider_kind="google",
            display_name="Legacy Gemini Embedding",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            enabled=True,
        )
    )
    return configuration_store.upsert_configuration(
        configuration_id="emb-legacy-gemini",
        provider_connection_id=connection.id,
        provider_kind="google",
        model_id="gemini-embedding-2",
        dimensions=3072,
        scope="global",
        project_id=None,
        status="active",
    )


def test_activate_ollama_pins_active_configuration(
    stores, fixed_now: datetime
) -> None:
    configuration_store, connection_store, secrets_store = stores

    active = activate_ollama_embedding(
        configuration_store=configuration_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
        now=lambda: fixed_now,
    )

    assert active.status == "active"
    assert active.provider_kind == "ollama"
    assert active.model_id == DEFAULT_OLLAMA_MODEL
    assert active.dimensions == DEFAULT_OLLAMA_DIMENSIONS
    assert active.scope == "global"
    assert active.project_id is None
    assert active.last_validated_at == fixed_now


def test_activate_ollama_moves_previous_gemini_to_rolled_back(
    stores, fixed_now: datetime
) -> None:
    """Issue #934 Akzeptanzkriterium: vorherige Konfiguration wird auf
    ``status='rolled_back'`` (Audit-Trail) gesetzt, nicht geloescht."""
    configuration_store, connection_store, secrets_store = stores
    legacy = _seed_legacy_gemini_active(
        configuration_store=configuration_store,
        connection_store=connection_store,
    )

    active = activate_ollama_embedding(
        configuration_store=configuration_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
        now=lambda: fixed_now,
    )

    assert active.status == "active"
    assert active.model_id == DEFAULT_OLLAMA_MODEL
    assert active.dimensions == DEFAULT_OLLAMA_DIMENSIONS

    previous = configuration_store.get_configuration(legacy.id)
    assert previous is not None, "Legacy-Knoten darf nicht geloescht werden"
    assert previous.status == "rolled_back"
    assert previous.id == legacy.id
    assert previous.model_id == legacy.model_id
    assert previous.dimensions == legacy.dimensions


def test_activate_ollama_is_idempotent(stores, fixed_now: datetime) -> None:
    """Wiederholte Aufrufe fuehren zur gleichen Endzustand-Konfiguration.

    Konkret: die Konfigurations-ID bleibt stabil, es entsteht genau
    ein ``status='active'``-Knoten, und die uebrigen Konfigurationen
    behalten ihren vorherigen Status.
    """
    configuration_store, connection_store, secrets_store = stores

    first = activate_ollama_embedding(
        configuration_store=configuration_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
        now=lambda: fixed_now,
    )
    second = activate_ollama_embedding(
        configuration_store=configuration_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
        now=lambda: fixed_now,
    )
    third = activate_ollama_embedding(
        configuration_store=configuration_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
        now=lambda: fixed_now,
    )

    assert first.id == second.id == third.id
    actives = [
        c
        for c in configuration_store.list_configurations(scope="global")
        if c.status == "active"
    ]
    assert len(actives) == 1, (
        f"Nach Idempotenz-Aktivierung darf es nur einen Active-Knoten geben, "
        f"gefunden: {len(actives)}"
    )
    assert actives[0].id == first.id
    assert actives[0].provider_kind == "ollama"
    assert actives[0].model_id == DEFAULT_OLLAMA_MODEL
    assert actives[0].dimensions == DEFAULT_OLLAMA_DIMENSIONS


def test_activate_ollama_converges_after_gemini_then_ollama(
    stores, fixed_now: datetime
) -> None:
    """Erst Gemini aktiv, dann lokales Ollama: Endzustand nach Idempotenz
    ist genau ein ``active``-Knoten (Ollama), Gemini ist ``rolled_back``.
    """
    configuration_store, connection_store, secrets_store = stores
    _seed_legacy_gemini_active(
        configuration_store=configuration_store,
        connection_store=connection_store,
    )

    for _ in range(2):
        activate_ollama_embedding(
            configuration_store=configuration_store,
            connection_store=connection_store,
            secrets_store=secrets_store,
            now=lambda: fixed_now,
        )

    actives = [
        c
        for c in configuration_store.list_configurations(scope="global")
        if c.status == "active"
    ]
    rolled_back = [
        c
        for c in configuration_store.list_configurations(scope="global")
        if c.status == "rolled_back"
    ]
    assert len(actives) == 1
    assert actives[0].model_id == DEFAULT_OLLAMA_MODEL
    assert len(rolled_back) == 1
    assert rolled_back[0].model_id == "gemini-embedding-2"


def test_activate_ollama_rejects_non_loopback_base_url(
    stores, fixed_now: datetime
) -> None:
    """Issue #934 Akzeptanzkriterium (Negativ-Test): ein nicht-Loopback
    ``base_url`` wird fuer ``provider_kind='ollama'`` als ValidationError
    abgelehnt — Loopback-Pflicht aus ``LocalOllamaBaseUrl`` und
    ``ProviderConnectionUpsertRequest.model_validator``.
    """
    configuration_store, connection_store, secrets_store = stores
    with pytest.raises(ValidationError):
        activate_ollama_embedding(
            base_url="http://example.com:11434",
            configuration_store=configuration_store,
            connection_store=connection_store,
            secrets_store=secrets_store,
            now=lambda: fixed_now,
        )
